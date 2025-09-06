import streamlit as st
import os
import asyncio
import uuid
import tempfile
from pathlib import Path
from typing import List
import json
from dataclasses import dataclass
from datetime import datetime
import httpx
import base64
import io
import fitz  # PyMuPDF
from PIL import Image
from cv_analyzer import CVAnalyzer
from dotenv import load_dotenv

load_dotenv()

@dataclass
class CandidateResult:
    name: str
    filename: str
    score: int
    reasoning: str
    key_strengths: List[str]
    concerns: List[str]
    cv_summary: str
    interview_questions: List[str]

class StreamlitCVAnalyzer:
    def __init__(self):
        self.api_url = os.getenv("OCR_API_URL", "http://api:9001/v1/ocr/process")
        # Нормализуем провайдера: убираем кавычки/пробелы и понижаем регистр
        self.ocr_provider = (os.getenv("OCR_PROVIDER", "api") or "").strip().strip('"').strip("'").lower()  # api | openrouter
        self.openrouter_base = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        raw_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY", "")
        # Убираем лишние кавычки/пробелы из ключа
        self.openrouter_key = (raw_key or "").strip().strip('"').strip("'")
        self.ocr_openrouter_model = os.getenv(
            "OCR_OPENROUTER_MODEL",
            "google/gemini-2.5-flash-image-preview:free",
        )
        # Автопереключение на OpenRouter, если есть валидный ключ
        if self.ocr_provider != "openrouter" and self.openrouter_key:
            self.ocr_provider = "openrouter"

        self.cv_analyzer = CVAnalyzer(
            model_name=os.getenv("OPENROUTER_LLM_MODEL", "google/gemma-3-27b-it:free"),
            model_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        )

    async def process_pdf_with_api(self, file_path: str) -> str:
        try:
            async with httpx.AsyncClient() as client:
                with open(file_path, "rb") as f:
                    files = {"files": (Path(file_path).name, f.read(), "application/pdf")}
                    response = await client.post(
                        self.api_url,
                        files=files,
                        data={"output_format": "text"},
                        timeout=60.0
                    )
                
                if response.status_code != 200:
                    st.error(f"API error: {response.text}")
                    return ""
                
                result = response.json()
                return result.get("text", "")
        except Exception as e:
            st.error(f"Error processing PDF with API: {str(e)}")
            return ""

    async def process_pdf_with_openrouter(self, file_path: str) -> str:
        if not self.openrouter_key:
            st.error("Ключ для OpenRouter не задан. Укажите OPENROUTER_API_KEY или OPENAI_API_KEY.")
            return ""

        def render_pdf_to_images(pdf_path: str) -> List[Image.Image]:
            images: List[Image.Image] = []
            doc = fitz.open(pdf_path)
            try:
                zoom = 300.0 / 72.0
                mat = fitz.Matrix(zoom, zoom)
                for page in doc:
                    pix = page.get_pixmap(matrix=mat, alpha=False)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    images.append(img)
            finally:
                doc.close()
            return images

        async def ocr_image(img: Image.Image) -> str:
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            img_bytes = buf.getvalue()
            img_b64 = base64.b64encode(img_bytes).decode("utf-8")

            payload = {
                "model": self.ocr_openrouter_model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Transcribe this page to plain UTF-8 text in Russian if content is Russian. "
                                    "Preserve reading order. Do not add explanations or formatting. Output only the text."
                                ),
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{img_b64}"
                                },
                            },
                        ],
                    }
                ],
                "temperature": 0,
                "max_tokens": 8000,
            }

            headers = {
                "Authorization": f"Bearer {self.openrouter_key}",
                "Content-Type": "application/json",
                # Рекомендуемые OpenRouter заголовки для маршрутизации и аналитики
                "HTTP-Referer": os.getenv("OPENROUTER_APP_URL", "http://localhost:8503"),
                "Referer": os.getenv("OPENROUTER_APP_URL", "http://localhost:8503"),
                "X-Title": os.getenv("OPENROUTER_APP_TITLE", "CV Agent"),
            }

            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self.openrouter_base}/chat/completions", json=payload, headers=headers
                )
                if resp.status_code != 200:
                    raise RuntimeError(f"OpenRouter OCR error: {resp.status_code} {resp.text}")
                data = resp.json()
                return (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )

        try:
            images = render_pdf_to_images(file_path)
            text_parts: List[str] = []
            for idx, img in enumerate(images):
                st.write(f"Обработка страницы {idx + 1}/{len(images)} через OpenRouter…")
                page_text = await ocr_image(img)
                text_parts.append(page_text)
            return "\n\n".join(text_parts)
        except Exception as e:
            st.error(f"Ошибка OCR через OpenRouter: {e}")
            return ""

    async def process_uploaded_files(self, uploaded_files, job_description: str) -> List[CandidateResult]:
        results = []
        with tempfile.TemporaryDirectory() as temp_dir:
            file_paths = []
            for uploaded_file in uploaded_files:
                unique_suffix = uuid.uuid4().hex[:8]
                safe_name = f"{unique_suffix}_{uploaded_file.name}"
                file_path = os.path.join(temp_dir, safe_name)
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getvalue())
                file_paths.append((safe_name, file_path))
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            cv_texts = {}
            
            for i, (save_filename, file_path) in enumerate(file_paths):
                status_text.text(f"Извлекаем текст из {Path(file_path).name}...")
                progress_bar.progress((i) / len(file_paths) * 0.6)
                try:
                    if file_path.lower().endswith('.pdf'):
                        if self.ocr_provider == "openrouter":
                            cv_text = await self.process_pdf_with_openrouter(file_path)
                        else:
                            cv_text = await self.process_pdf_with_api(file_path)
                        cv_texts[save_filename] = cv_text
                    else:
                        st.warning(f"Неподдерживаемый формат файла: {Path(file_path).name}")
                        continue
                except Exception as e:
                    st.error(f"Ошибка при обработке {Path(file_path).name}: {str(e)}")
                    continue
            
            for i, (filename, cv_text) in enumerate(cv_texts.items()):
                if not cv_text.strip():
                    continue
                status_text.text(f"Анализируем кандидата из {filename}...")
                progress_bar.progress(0.6 + (i) / len(cv_texts) * 0.4)
                try:
                    analysis = await self.cv_analyzer.analyze_cv(cv_text, job_description)
                    result = CandidateResult(
                        name=analysis.candidate_name,
                        filename=filename,
                        score=analysis.score,
                        reasoning=analysis.reasoning,
                        key_strengths=analysis.key_strengths,
                        concerns=analysis.concerns,
                        cv_summary=analysis.cv_summary,
                        interview_questions=analysis.interview_questions
                    )
                    results.append(result)
                except Exception as e:
                    st.error(f"Ошибка при анализе {filename}: {str(e)}")
                    continue
            
            progress_bar.progress(1.0)
            status_text.text("Анализ завершен!")
        return results

def main():
    st.set_page_config(
        page_title="HR Auto System - Этап 1 из 4: Анализ CV",
        page_icon="📄",
        layout="wide"
    )
    st.title("🎯 HR Auto System - Этап 1: Анализ CV")
    st.caption("📋 Этап 1 из 4: Анализ резюме → 📅 Планирование встреч → 🎤 Собеседование → ✅ Принятие решения")
    st.markdown("---")
    
    with st.sidebar:
        st.header("⚙️ Настройки")
        st.subheader("🤖 Используемые модели")
        ocr_label = "OpenRouter Gemini 2.5 Flash (free)" if os.getenv("OCR_PROVIDER", "api").lower() == "openrouter" else "OCR API"
        st.text(f"👁️ OCR: {ocr_label}")
        st.text(f"🧠 Анализ: {os.getenv('OPENROUTER_LLM_MODEL', 'google/gemma-3-27b-it:free')}")
        st.markdown("---")
        
        if 'results' in st.session_state and st.session_state.results:
            st.subheader("📊 Экспорт результатов")
            if st.button("Скачать результаты (JSON)"):
                results_json = json.dumps([
                    {
                        'name': r.name,
                        'filename': r.filename,
                        'score': r.score,
                        'reasoning': r.reasoning,
                        'key_strengths': r.key_strengths,
                        'concerns': r.concerns,
                        'cv_summary': r.cv_summary,
                        'interview_questions': r.interview_questions
                    } for r in st.session_state.results
                ], ensure_ascii=False, indent=2)
                st.download_button(
                    label="📥 Скачать JSON",
                    data=results_json,
                    file_name=f"cv_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json"
                )
    
    if 'analyzer' not in st.session_state:
        try:
            st.session_state.analyzer = StreamlitCVAnalyzer()
        except Exception as e:
            st.error(f"Ошибка инициализации анализатора: {e}")
            return
    
    col1, col2 = st.columns([1, 1])
    with col1:
        st.header("📋 Описание вакансии")
        job_description = st.text_area(
            "Введите требования к кандидату:",
            height=300,
            placeholder="""Пример:
Требуется Senior Python Developer для разработки торговых систем.
Обязательные требования:
- Опыт работы с Python 5+ лет
- Знание Django/FastAPI
- Опыт работы с базами данных (PostgreSQL, Redis)
- Знание алгоритмов и структур данных
Желательно:
- Опыт в финтех
- Знание Kubernetes и Docker
- Опыт с высоконагруженными системами
Условия:
- Зарплата от 300,000 руб
- Удаленная работа
- Офис в центре Москвы""",
            help="Опишите требования к кандидату, обязательные и желательные навыки, условия работы"
        )
    
    with col2:
        st.header("📄 Загрузка CV")
        uploaded_files = st.file_uploader(
            "Выберите файлы CV (PDF):",
            type=['pdf'],
            accept_multiple_files=True,
            help="Можете загрузить несколько файлов одновременно",
            key="file_uploader"
        )
        
        if uploaded_files:
            current_file_names = [f.name for f in uploaded_files]
            if 'previous_files' not in st.session_state:
                st.session_state.previous_files = []
            if set(current_file_names) != set(st.session_state.previous_files):
                st.session_state.previous_files = current_file_names
                if 'results' in st.session_state:
                    del st.session_state.results
                if 'job_description' in st.session_state:
                    del st.session_state.job_description
            
            st.success(f"Загружено файлов: {len(uploaded_files)}")
            for file in uploaded_files:
                st.text(f"📎 {file.name} ({file.size / 1024:.1f} KB)")
        else:
            if 'previous_files' in st.session_state:
                st.session_state.previous_files = []
            if 'results' in st.session_state:
                del st.session_state.results
            if 'job_description' in st.session_state:
                del st.session_state.job_description
    
    st.markdown("---")
    can_analyze = job_description and uploaded_files
    analysis_needed = True
    
    if ('results' in st.session_state and 
        'job_description' in st.session_state and
        st.session_state.job_description == job_description and
        uploaded_files and
        set([f.name for f in uploaded_files]) == set(st.session_state.previous_files)):
        analysis_needed = False
    
    if analysis_needed:
        button_text = "🚀 Запустить анализ"
        button_help = "Анализировать загруженные CV"
    else:
        button_text = "🔄 Повторить анализ"
        button_help = "Повторно анализировать те же файлы"
    
    if st.button(button_text, type="primary", disabled=not can_analyze, help=button_help):
        if not job_description.strip():
            st.error("Пожалуйста, введите описание вакансии")
        elif not uploaded_files:
            st.error("Пожалуйста, загрузите файлы CV")
        else:
            with st.spinner("Анализируем CV..."):
                try:
                    results = asyncio.run(
                        st.session_state.analyzer.process_uploaded_files(uploaded_files, job_description)
                    )
                    st.session_state.results = results
                    st.session_state.job_description = job_description
                    st.success(f"Анализ завершен! Обработано кандидатов: {len(results)}")
                except Exception as e:
                    st.error(f"Ошибка при анализе: {str(e)}")
    
    if ('results' in st.session_state and st.session_state.results and
        'previous_files' in st.session_state and uploaded_files and
        set([f.name for f in uploaded_files]) == set(st.session_state.previous_files)):
        st.markdown("---")
        st.header("📊 Результаты анализа")
        results = sorted(st.session_state.results, key=lambda x: x.score, reverse=True)
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Всего кандидатов", len(results))
        with col2:
            high_score = len([r for r in results if r.score >= 8])
            st.metric("Отличные (8-10)", high_score)
        with col3:
            medium_score = len([r for r in results if 5 <= r.score < 8])
            st.metric("Хорошие (5-7)", medium_score)
        with col4:
            low_score = len([r for r in results if r.score < 5])
            st.metric("Слабые (1-4)", low_score)
        
        for i, result in enumerate(results):
            with st.expander(f"🏅 {result.name} - Оценка: {result.score}/10", expanded=i < 3):
                col1, col2 = st.columns([2, 1])
                with col1:
                    st.subheader("📝 Обоснование оценки")
                    st.write(result.reasoning)
                    st.subheader("💪 Ключевые преимущества")
                    for strength in result.key_strengths:
                        st.write(f"✅ {strength}")
                    if result.concerns:
                        st.subheader("⚠️ Замечания")
                        for concern in result.concerns:
                            st.write(f"❌ {concern}")
                with col2:
                    score_color = "green" if result.score >= 8 else "orange" if result.score >= 5 else "red"
                    st.metric("Оценка", f"{result.score}/10")
                    st.info(f"📁 Файл: {result.filename}")
                    if result.cv_summary:
                        st.subheader("📋 Краткое резюме")
                        st.write(result.cv_summary)
                
                # Новая секция: Вопросы для собеседования
                if result.interview_questions:
                    st.markdown("---")
                    st.subheader("❓ Вопросы для первичного собеседования")
                    st.caption("Персонализированные вопросы на основе анализа резюме:")
                    for idx, question in enumerate(result.interview_questions, 1):
                        st.write(f"**{idx}.** {question}")
                    
                    # Кнопка для копирования вопросов
                    questions_text = "\n".join([f"{idx}. {q}" for idx, q in enumerate(result.interview_questions, 1)])
                    if st.button(f"📋 Копировать вопросы для {result.name}", key=f"copy_questions_{result.filename}"):
                        st.code(questions_text, language="text")
                        st.success("Вопросы готовы для копирования!")

if __name__ == "__main__":
    main()