import streamlit as st
import os
import asyncio
import uuid
import tempfile
from pathlib import Path
from typing import List, Optional
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
from kafka import KafkaProducer
from kafka.errors import KafkaError, NoBrokersAvailable
import time
import asyncpg

load_dotenv()

@dataclass
class CandidateResult:
    candidate_id: str  # Уникальный ID кандидата для базы данных
    name: str
    filename: str
    score: int
    reasoning: str
    key_strengths: List[str]
    concerns: List[str]
    cv_summary: str
    interview_questions: List[str]
    email: str
    preferred_contact: str  # Новое поле для способа связи
    cv_text: str

class HRDatabaseClient:
    """Клиент для работы с PostgreSQL базой данных HR системы"""
    
    def __init__(self):
        self.db_url = os.getenv("DATABASE_URL", "postgresql://hr_user:hr_secure_password_2024@postgres_hr:5432/hr_system")
        self.enabled = os.getenv("DATABASE_ENABLED", "true").lower() == "true"
    
    async def save_cv_analysis_results(
        self, 
        request_id: str,
        vacancy_title: str, 
        vacancy_description: str,
        candidates_data: List[dict]
    ) -> bool:
        """Сохранение результатов анализа CV в БД"""
        if not self.enabled:
            return False
            
        try:
            conn = await asyncpg.connect(self.db_url)
            try:
                # Используем функцию insert_cv_analysis_data из БД
                result = await conn.fetchval(
                    """
                    SELECT insert_cv_analysis_data($1::UUID, $2, $3, $4::JSONB)
                    """,
                    uuid.UUID(request_id) if isinstance(request_id, str) else request_id,
                    vacancy_title,
                    vacancy_description,
                    json.dumps(candidates_data)
                )
                st.success(f"✅ Данные сохранены в БД: {len(candidates_data)} кандидатов")
                return True
            finally:
                await conn.close()
        except Exception as e:
            st.warning(f"⚠️ Ошибка сохранения в БД: {str(e)}")
            return False
    
    async def get_request_statistics(self, request_id: str) -> Optional[dict]:
        """Получение статистики по запросу"""
        if not self.enabled:
            return None
            
        try:
            conn = await asyncpg.connect(self.db_url)
            try:
                row = await conn.fetchrow(
                    """
                    SELECT * FROM requests_statistics 
                    WHERE request_id = $1::UUID
                    """,
                    uuid.UUID(request_id)
                )
                if row:
                    return {
                        'vacancy_title': row['vacancy_title'],
                        'total_candidates': row['total_candidates'],
                        'analyzed_candidates': row['analyzed_candidates'],
                        'avg_cv_score': float(row['avg_cv_score']) if row['avg_cv_score'] else 0,
                        'high_suitability': row['high_suitability'],
                        'medium_suitability': row['medium_suitability'],
                        'low_suitability': row['low_suitability']
                    }
                return None
            finally:
                await conn.close()
        except Exception:
            return None

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
            "meta-llama/llama-3.2-11b-vision-instruct:free",
        )
        # Автопереключение на OpenRouter, если есть валидный ключ
        if self.ocr_provider != "openrouter" and self.openrouter_key:
            self.ocr_provider = "openrouter"

        self.cv_analyzer = CVAnalyzer(
            model_name=os.getenv("OPENROUTER_LLM_MODEL", "google/gemma-3-27b-it:free"),
            model_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        )
        
        # Клиент для работы с БД
        self.db_client = HRDatabaseClient()

        # Kafka config
        self.kafka_bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "").strip()
        self.kafka_topic = os.getenv("KAFKA_TOPIC", "").strip()
        self.kafka_connect_max_retries = int(os.getenv("KAFKA_CONNECT_MAX_RETRIES", "8") or 8)
        self.kafka_connect_backoff_seconds = float(os.getenv("KAFKA_CONNECT_BACKOFF_SECONDS", "2") or 2)
        self.kafka_producer = None
        if self.kafka_bootstrap and self.kafka_topic:
            # Первая попытка создать продьюсер (без долгой блокировки UI)
            try:
                self.kafka_producer = self._create_kafka_producer()
            except Exception as e:
                st.warning(f"Kafka недоступна при старте: {e}")

    def _build_kafka_config(self) -> dict:
        servers = [s.strip() for s in self.kafka_bootstrap.split(",") if s.strip()]
        cfg = {
            "bootstrap_servers": servers,
            "value_serializer": lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
            "acks": "all",
            "linger_ms": 50,
            "retries": 3,
            "max_in_flight_requests_per_connection": 1,
            "request_timeout_ms": 10000,
            "retry_backoff_ms": 500,
            "metadata_max_age_ms": 30000,
        }
        security_protocol = (os.getenv("KAFKA_SECURITY_PROTOCOL", "") or "").strip()
        if security_protocol:
            cfg["security_protocol"] = security_protocol
        sasl_mechanism = (os.getenv("KAFKA_SASL_MECHANISM", "") or "").strip()
        if sasl_mechanism:
            cfg["sasl_mechanism"] = sasl_mechanism
        sasl_username = os.getenv("KAFKA_SASL_USERNAME")
        sasl_password = os.getenv("KAFKA_SASL_PASSWORD")
        if sasl_username and sasl_password:
            cfg["sasl_plain_username"] = sasl_username
            cfg["sasl_plain_password"] = sasl_password
        ssl_cafile = os.getenv("KAFKA_SSL_CAFILE")
        if ssl_cafile:
            cfg["ssl_cafile"] = ssl_cafile
        return cfg

    def _create_kafka_producer(self) -> KafkaProducer:
        cfg = self._build_kafka_config()
        producer = KafkaProducer(**cfg)
        return producer

    def _ensure_kafka_connected_with_retries(self) -> bool:
        if not (self.kafka_bootstrap and self.kafka_topic):
            return False
        # Быстрый успешный путь
        if self.kafka_producer is not None:
            try:
                if self.kafka_producer.bootstrap_connected():
                    return True
            except Exception:
                self.kafka_producer = None

        attempts = 0
        backoff = max(self.kafka_connect_backoff_seconds, 0.5)
        last_error: Exception | None = None
        while attempts < self.kafka_connect_max_retries:
            attempts += 1
            try:
                self.kafka_producer = self._create_kafka_producer()
                # Проверяем доступность метаданных/брокера
                try:
                    _ = self.kafka_producer.partitions_for(self.kafka_topic)
                except Exception:
                    pass
                if self.kafka_producer.bootstrap_connected():
                    return True
            except (NoBrokersAvailable, KafkaError, Exception) as e:
                last_error = e
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)

        if last_error:
            st.warning(f"Kafka недоступна: {last_error}")
        return False

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

            # Всегда читаем актуальную модель из окружения на момент вызова
            current_ocr_model = os.getenv("OCR_OPENROUTER_MODEL", self.ocr_openrouter_model)
            if not current_ocr_model:
                current_ocr_model = self.ocr_openrouter_model

            payload = {
                "model": current_ocr_model,
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
                    # Извлечение контактной информации с приоритетом email
                    candidate_email, preferred_contact = self.extract_contact_info(cv_text)
                    # Генерация уникального ID для кандидата
                    candidate_id = f"cv_{uuid.uuid4().hex[:12]}"
                    result = CandidateResult(
                        candidate_id=candidate_id,
                        name=analysis.candidate_name,
                        filename=filename,
                        score=analysis.score,
                        reasoning=analysis.reasoning,
                        key_strengths=analysis.key_strengths,
                        concerns=analysis.concerns,
                        cv_summary=analysis.cv_summary,
                        interview_questions=analysis.interview_questions,
                        email=candidate_email,
                        preferred_contact=preferred_contact,
                        cv_text=cv_text,
                    )
                    results.append(result)
                except Exception as e:
                    st.error(f"Ошибка при анализе {filename}: {str(e)}")
                    continue
            
            progress_bar.progress(1.0)
            status_text.text("Анализ завершен!")
        return results

    def extract_contact_info(self, cv_text: str) -> tuple[str, str]:
        """
        Извлекает контактную информацию из резюме с приоритетом email.
        Возвращает (email, preferred_contact_method)
        """
        import re as _re
        
        # 1. Поиск email (приоритет)
        email_pattern = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
        email_match = _re.search(email_pattern, cv_text)
        email = email_match.group(0) if email_match else ""
        
        if email:
            return email, f"📧 {email}"
        
        # 2. Поиск телефона (если нет email)
        phone_patterns = [
            r"\+7[\s\-\(\)]?[\d\s\-\(\)]{10,}",  # +7 формат
            r"8[\s\-\(\)]?[\d\s\-\(\)]{10,}",    # 8 формат
            r"\+\d{1,3}[\s\-\(\)]?[\d\s\-\(\)]{7,}",  # международный
            r"\b\d{3}[\s\-]?\d{3}[\s\-]?\d{4}\b",  # стандартный
        ]
        
        for pattern in phone_patterns:
            phone_match = _re.search(pattern, cv_text)
            if phone_match:
                phone = _re.sub(r"[\s\-\(\)]", "", phone_match.group(0))
                return "", f"📞 {phone}"
        
        # 3. Поиск Telegram
        telegram_patterns = [
            r"@[\w\d_]+",  # @username
            r"t\.me/[\w\d_]+",  # t.me/username
            r"telegram\.me/[\w\d_]+",  # telegram.me/username
        ]
        
        for pattern in telegram_patterns:
            tg_match = _re.search(pattern, cv_text, _re.IGNORECASE)
            if tg_match:
                tg = tg_match.group(0)
                return "", f"💬 Telegram: {tg}"
        
        # 4. Поиск LinkedIn
        linkedin_patterns = [
            r"linkedin\.com/in/[\w\d\-_]+",
            r"linkedin\.com/profile/[\w\d\-_]+",
        ]
        
        for pattern in linkedin_patterns:
            li_match = _re.search(pattern, cv_text, _re.IGNORECASE)
            if li_match:
                li = li_match.group(0)
                return "", f"💼 LinkedIn: {li}"
        
        # 5. Fallback - поиск любого контакта в тексте
        contact_keywords = ["контакт", "связаться", "телефон", "почта", "email"]
        lines = cv_text.split('\n')
        
        for line in lines:
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in contact_keywords):
                # Извлекаем строку с контактной информацией
                clean_line = line.strip()
                if len(clean_line) > 5 and len(clean_line) < 100:
                    return "", f"📝 {clean_line}"
        
        # 6. Если вообще ничего не найдено
        return "", "❌ Контактная информация не найдена"

    async def save_results_to_database(
        self, 
        results: List[CandidateResult], 
        job_description: str, 
        vacancy_title: str,
        request_id: str
    ) -> bool:
        """Сохранение результатов анализа в PostgreSQL БД"""
        try:
            # Подготовка данных для БД
            candidates_data = []
            
            for result in results:
                # Функция для определения заключения по оценке
                def _conclusion(score: int) -> str:
                    if score >= 8:
                        return "Высокая пригодность"
                    if score >= 5:
                        return "Средняя пригодность"
                    return "Низкая пригодность"
                
                candidates_data.append({
                    "candidateId": result.candidate_id,
                    "candidateName": result.name,
                    "email": result.email,
                    "preferredContact": result.preferred_contact,
                    "cvText": result.cv_text,
                    "score": result.score,
                    "reasoning": result.reasoning,
                    "suitabilityConclusion": _conclusion(result.score),
                    "questionsForApplicant": result.interview_questions,
                    "keyStrengths": result.key_strengths,
                    "concerns": result.concerns,
                    "cvSummary": result.cv_summary
                })
            
            # Сохранение в БД
            success = await self.db_client.save_cv_analysis_results(
                request_id, vacancy_title, job_description, candidates_data
            )
            
            if success:
                # Показ статистики
                stats = await self.db_client.get_request_statistics(request_id)
                if stats:
                    st.info(f"""
                    📊 **Статистика сохранена в БД:**
                    - Кандидатов проанализировано: {stats['analyzed_candidates']}
                    - Средняя оценка: {stats['avg_cv_score']:.1f}/10
                    - Высокая пригодность: {stats['high_suitability']}
                    - Средняя пригодность: {stats['medium_suitability']}  
                    - Низкая пригодность: {stats['low_suitability']}
                    """)
            
            return success
            
        except Exception as e:
            st.error(f"❌ Ошибка при сохранении в БД: {str(e)}")
            return False

    def publish_to_kafka(self, items_json: list) -> None:
        if not self.kafka_producer or not self.kafka_topic:
            # Пытаемся подключиться лениво при первой отправке
            if not self._ensure_kafka_connected_with_retries():
                return
        try:
            self.kafka_producer.send(self.kafka_topic, items_json)
            self.kafka_producer.flush(timeout=5)
        except (KafkaError, Exception) as e:
            # Пытаемся разово пересоздать продьюсер и повторить
            self.kafka_producer = None
            if self._ensure_kafka_connected_with_retries():
                try:
                    self.kafka_producer.send(self.kafka_topic, items_json)
                    self.kafka_producer.flush(timeout=5)
                    return
                except Exception:
                    pass
            st.warning(f"Ошибка отправки в Kafka: {e}")

def main():
    st.set_page_config(
        page_title="HR Auto System - Этап 1 из 4: Анализ CV",
        page_icon="",
        layout="wide"
    )
    st.title("HR Auto System - Этап 1: Анализ CV")
    st.caption("Этап 1 из 4: Анализ резюме → Планирование встреч → Собеседование → Принятие решения")
    st.markdown("---")

    # Инициализируем/пересоздаём анализатор ДО отрисовки сайдбара,
    # чтобы метки моделей соответствовали актуальным переменным окружения
    if 'analyzer' not in st.session_state:
        try:
            st.session_state.analyzer = StreamlitCVAnalyzer()
        except Exception as e:
            st.error(f"Ошибка инициализации анализатора: {e}")
            return
    else:
        # Пересоздаём анализатор, если модель в окружении изменилась
        try:
            env_model = os.getenv("OCR_OPENROUTER_MODEL", "meta-llama/llama-3.2-11b-vision-instruct:free")
            if getattr(st.session_state.analyzer, 'ocr_openrouter_model', None) != env_model:
                st.session_state.analyzer = StreamlitCVAnalyzer()
        except Exception:
            st.session_state.analyzer = StreamlitCVAnalyzer()

    with st.sidebar:
        st.header("Настройки")
        st.subheader("Используемые модели")
        ocr_is_or = os.getenv("OCR_PROVIDER", "api").lower() == "openrouter"
        # Приоритет у значения из окружения, чтобы сразу отображалась актуальная модель
        env_ocr_model = os.getenv("OCR_OPENROUTER_MODEL", "meta-llama/llama-3.2-11b-vision-instruct:free")
        try:
            analyzer_model = getattr(st.session_state.get('analyzer', None), 'ocr_openrouter_model', None)
        except Exception:
            analyzer_model = None
        current_ocr_model = env_ocr_model or analyzer_model or "meta-llama/llama-3.2-11b-vision-instruct:free"
        ocr_label = f"OpenRouter {current_ocr_model}" if ocr_is_or else "OCR API"
        st.text(f"OCR: {ocr_label}")
        st.text(f"Анализ: {os.getenv('OPENROUTER_LLM_MODEL', 'google/gemma-3-27b-it:free')}")
        st.markdown("---")

        if 'results' in st.session_state and st.session_state.results:
            st.subheader("Экспорт результатов")
            if st.button("Скачать результаты (JSON)"):
                results_json = json.dumps([
                    {
                        'candidate_id': r.candidate_id,  # Уникальный ID для БД
                        'vacancy_title': st.session_state.get('vacancy_title', ''),  # Название вакансии
                        'name': r.name,
                        'filename': r.filename,
                        'score': r.score,
                        'reasoning': r.reasoning,
                        'key_strengths': r.key_strengths,
                        'concerns': r.concerns,
                        'cv_summary': r.cv_summary,
                        'interview_questions': r.interview_questions,
                        'email': r.email,
                        'preferred_contact': r.preferred_contact
                    } for r in st.session_state.results
                ], ensure_ascii=False, indent=2)
                st.download_button(
                    label="Скачать JSON",
                    data=results_json,
                    file_name=f"cv_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json"
                )
    
    
    col1, col2 = st.columns([1, 1])
    with col1:
        st.header("Описание вакансии")
        
        # Поле для названия вакансии (для второго блока)
        vacancy_title = st.text_input(
            "Название вакансии:",
            placeholder="Senior Python Developer",
            help="Укажите точное название позиции для собеседования"
        )
        
        job_description = st.text_area(
            "Введите требования к кандидату:",
            height=260,
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
        st.header("Загрузка CV")
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
                if 'vacancy_title' in st.session_state:
                    del st.session_state.vacancy_title
            
            st.success(f"Загружено файлов: {len(uploaded_files)}")
            for file in uploaded_files:
                st.text(f"{file.name} ({file.size / 1024:.1f} KB)")
        else:
            if 'previous_files' in st.session_state:
                st.session_state.previous_files = []
            if 'results' in st.session_state:
                del st.session_state.results
            if 'job_description' in st.session_state:
                del st.session_state.job_description
            if 'vacancy_title' in st.session_state:
                del st.session_state.vacancy_title
    
    st.markdown("---")
    can_analyze = vacancy_title.strip() and job_description and uploaded_files
    analysis_needed = True
    
    if ('results' in st.session_state and 
        'job_description' in st.session_state and
        'vacancy_title' in st.session_state and
        st.session_state.job_description == job_description and
        st.session_state.vacancy_title == vacancy_title and
        uploaded_files and
        set([f.name for f in uploaded_files]) == set(st.session_state.previous_files)):
        analysis_needed = False
    
    if analysis_needed:
        button_text = "Запустить анализ"
        button_help = "Анализировать загруженные CV"
    else:
        button_text = "Повторить анализ"
        button_help = "Повторно анализировать те же файлы"
    
    if st.button(button_text, type="primary", disabled=not can_analyze, help=button_help):
        if not vacancy_title.strip():
            st.error("Пожалуйста, введите название вакансии")
        elif not job_description.strip():
            st.error("Пожалуйста, введите описание вакансии")
        elif not uploaded_files:
            st.error("Пожалуйста, загрузите файлы CV")
        else:
            with st.spinner("Анализируем CV..."):
                try:
                    # Уникальный идентификатор запроса анализа
                    st.session_state.request_id = uuid.uuid4().hex
                    results = asyncio.run(
                        st.session_state.analyzer.process_uploaded_files(uploaded_files, job_description)
                    )
                    st.session_state.results = results
                    st.session_state.job_description = job_description
                    st.session_state.vacancy_title = vacancy_title
                    
                    # Сохранение результатов в БД
                    try:
                        db_saved = asyncio.run(
                            st.session_state.analyzer.save_results_to_database(
                                results, job_description, vacancy_title, st.session_state.request_id
                            )
                        )
                        if db_saved:
                            st.success(f"✅ Анализ завершен! Обработано кандидатов: {len(results)}. Данные сохранены в БД.")
                        else:
                            st.success(f"⚠️ Анализ завершен! Обработано кандидатов: {len(results)}. БД недоступна.")
                    except Exception as e:
                        st.warning(f"Анализ завершен! Обработано кандидатов: {len(results)}. Ошибка БД: {e}")
                        st.success(f"Анализ завершен! Обработано кандидатов: {len(results)}")
                except Exception as e:
                    st.error(f"Ошибка при анализе: {str(e)}")
    
    if ('results' in st.session_state and st.session_state.results and
        'previous_files' in st.session_state and uploaded_files and
        set([f.name for f in uploaded_files]) == set(st.session_state.previous_files)):
        st.markdown("---")
        st.header("Результаты анализа")
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
            with st.expander(f"{result.name} - Оценка: {result.score}/10", expanded=i < 3):
                col1, col2 = st.columns([2, 1])
                with col1:
                    st.subheader("Обоснование оценки")
                    st.write(result.reasoning)
                    st.subheader("Ключевые преимущества")
                    for strength in result.key_strengths:
                        st.write(f"{strength}")
                    if result.concerns:
                        st.subheader("Замечания")
                        for concern in result.concerns:
                            st.write(f"{concern}")
                with col2:
                    score_color = "green" if result.score >= 8 else "orange" if result.score >= 5 else "red"
                    st.metric("Оценка", f"{result.score}/10")
                    st.info(f"Файл: {result.filename}")
                    
                    # ID кандидата для базы данных
                    st.caption(f"🆔 ID: {result.candidate_id}")
                    
                    # Новое поле: Способ связи
                    st.subheader("Способ связи")
                    st.write(result.preferred_contact)
                    
                    if result.cv_summary:
                        st.subheader("Краткое резюме")
                        st.write(result.cv_summary)
                
                # Новая секция: Вопросы для собеседования
                if result.interview_questions:
                    st.markdown("---")
                    st.subheader("Вопросы для первичного собеседования")
                    st.caption("Персонализированные вопросы на основе анализа резюме:")
                    for idx, question in enumerate(result.interview_questions, 1):
                        st.write(f"**{idx}.** {question}")
                    
                    # Кнопка для копирования вопросов
                    questions_text = "\n".join([f"{idx}. {q}" for idx, q in enumerate(result.interview_questions, 1)])
                    if st.button(f"Копировать вопросы для {result.name}", key=f"copy_questions_{result.filename}"):
                        st.code(questions_text, language="text")
                        st.success("Вопросы готовы для копирования!")

        # Строгий JSON для n8n
        try:
            vacancy_text = st.session_state.get("job_description", "")
            vacancy_title_text = st.session_state.get("vacancy_title", "")
            request_id = st.session_state.get("request_id") or uuid.uuid4().hex
            def _conclusion(score: int) -> str:
                if score >= 8:
                    return "Высокая пригодность"
                if score >= 5:
                    return "Средняя пригодность"
                return "Низкая пригодность"

            n8n_items = [
                {
                    "candidateId": r.candidate_id,  # Уникальный ID для БД
                    "requestId": request_id,        # ID сессии анализа
                    "vacancyTitle": vacancy_title_text,  # 🆕 Название вакансии для второго блока
                    "vacancy": vacancy_text,
                    "candidateName": r.name,
                    "cvText": r.cv_text,
                    "suitabilityConclusion": _conclusion(r.score),
                    "score": r.score,
                    "email": r.email,
                    "preferredContact": r.preferred_contact,
                    "questionsForApplicant": r.interview_questions,
                }
                for r in results
            ]
            st.markdown("---")
            st.subheader("JSON для n8n")
            st.code(json.dumps(n8n_items, ensure_ascii=False, indent=2), language="json")

            # Публикация в Kafka (если настроена)
            st.session_state.analyzer.publish_to_kafka(n8n_items)
        except Exception as _e:
            st.error(f"Ошибка формирования JSON для n8n: {_e}")

if __name__ == "__main__":
    main()