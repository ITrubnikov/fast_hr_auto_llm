#!/usr/bin/env python3
"""LangGraph-based adaptive technical interview system."""

import json
import asyncio
import numpy as np
from typing import Dict, List, Any, Optional, TypedDict
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

# Добавляем путь к модулю interview_system
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "interview_system"))

from interview_system import (
    DriverFactory,
    create_drivers_from_config
)

# Kafka imports
from kafka_producer import publish_report_to_kafka
from interview_system.emotion_analyzer import EmotionAnalyzer


@dataclass
class Question:
    """Структура вопроса."""
    id: str
    text: str
    topic: str
    difficulty: int  # 1-5, где 5 - самый сложный
    follow_up_questions: List[str] = None  # Список ID следующих вопросов по теме


@dataclass
class Answer:
    """Структура ответа."""
    question_id: str
    answer_text: str
    score: int  # 1-10
    evaluation: str  # Комментарий оценки
    timestamp: str
    emotion_analysis: Optional[Dict[str, Any]] = None  # Анализ эмоций


class InterviewState(TypedDict):
    """Состояние интервью для LangGraph."""
    current_question: Optional[Question]
    answers: List[Answer]
    asked_questions: List[str]  # ID заданных вопросов
    current_topic: Optional[str]
    topic_depth: int  # Глубина погружения в тему
    max_depth: int  # Максимальная глубина
    min_score_threshold: int  # Минимальный порог для продолжения темы
    is_complete: bool
    interview_report: Optional[Dict[str, Any]]
    websocket: Optional[Any]  # WebSocket соединение


class TechnicalInterviewSystem:
    """Система технического интервью с адаптивными вопросами."""
    
    def __init__(
        self,
        questions: Dict[str, Any],
        config_file: str = "interview_config.json",
        candidate_name: str = "Алексей"
    ):
        self.questions = questions
        self.config_file = config_file
        self.candidate_name = candidate_name
        
        # Загрузка конфигурации
        self.config = self._load_config()
        
        # Инициализация компонентов
        self.llm = ChatOpenAI(
            api_key=self.config['openai_api_key'],
            model="gpt-4o",
            temperature=0.1
        )
        
        # Создаем драйверы из конфигурации
        driver_config = self.config.get('drivers', {})
        self.drivers = create_drivers_from_config(driver_config)
        
        # Инициализируем все драйверы
        for driver in self.drivers.values():
            driver.initialize()
        
        # Получаем ссылки на драйверы
        self.audio_input_driver = self.drivers.get('audio_input')
        self.audio_output_driver = self.drivers.get('audio_output')
        self.tts_driver = self.drivers.get('tts')
        self.asr_driver = self.drivers.get('asr')
        
        # Детектор окончания речи с параметрами из конфигурации
        speech_config = self.config.get('speech_detection', {})
        audio_input_config = self.config.get('drivers', {}).get('audio_input', {}).get('config', {})
        
        # Валидация конфигурации
        required_speech_params = ['silence_duration', 'min_speech_duration', 'threshold']
        required_audio_params = ['sample_rate', 'chunk_size']
        
        for param in required_speech_params:
            if param not in speech_config:
                raise ValueError(f"Отсутствует обязательный параметр speech_detection.{param} в конфигурации")
        
        for param in required_audio_params:
            if param not in audio_input_config:
                raise ValueError(f"Отсутствует обязательный параметр drivers.audio_input.config.{param} в конфигурации")
        
        # Используем современный детектор речи - SpeechBrain + Wav2Vec2
        from modern_speech_detector import ModernSpeechDetector
        self.speech_detector = ModernSpeechDetector(
            config=speech_config,
            sample_rate=audio_input_config['sample_rate'],
            chunk_size=audio_input_config['chunk_size']
        )
        
        # Инициализация анализатора эмоций
        self.emotion_analyzer = EmotionAnalyzer()
        self.emotion_analyzer.initialize()
        
        # Сохраняем исходные данные вопросов
        self.raw_questions = questions
        # Преобразуем вопросы в нужный формат
        self.questions = self._process_questions()
        
        # Создание графа
        self.graph = self._create_graph()
    
    def _process_questions(self) -> Dict[str, Question]:
        """Обработать вопросы из переданных данных."""
        questions = {}
        for topic, q_data in self.raw_questions.items():
            question = Question(
                id=q_data['id'],
                text=q_data['text'],
                topic=topic,
                difficulty=1,  # Все стартовые вопросы имеют сложность 1
                follow_up_questions=[]
            )
            questions[topic] = question
        
        return questions
    
    def _load_config(self) -> Dict[str, Any]:
        """Загрузить конфигурацию."""
        default_config = {
            "max_depth": 3,
            "min_score_threshold": 7,
            "max_questions_per_topic": 5,
            "evaluation_prompt": "Оцените ответ разработчика по шкале 1-10, где 10 - отличный ответ. Учтите техническую глубину, практический опыт и понимание концепций.",
            "topics": ["Java Backend", "Spring Framework", "Database Design", "System Architecture"]
        }
        
        if Path(self.config_file).exists():
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                default_config.update(config)
        
        return default_config
    
    def _create_graph(self) -> StateGraph:
        """Создать граф LangGraph."""
        workflow = StateGraph(InterviewState)
        
        # Добавить узлы
        workflow.add_node("select_question", self._select_question)
        workflow.add_node("ask_question", self._ask_question)
        workflow.add_node("get_answer", self._get_answer)
        workflow.add_node("evaluate_answer", self._evaluate_answer)
        workflow.add_node("update_state", self._update_state)
        workflow.add_node("generate_report", self._generate_report)
        
        # Добавить рёбра
        workflow.set_entry_point("select_question")
        
        workflow.add_edge("select_question", "ask_question")
        workflow.add_edge("ask_question", "get_answer")
        workflow.add_edge("get_answer", "evaluate_answer")
        workflow.add_edge("evaluate_answer", "update_state")
        
        # Условные переходы после обновления состояния
        workflow.add_conditional_edges(
            "update_state",
            self._should_continue,
            {
                "continue_topic": "select_question",
                "next_topic": "select_question", 
                "complete": "generate_report"
            }
        )
        
        workflow.add_edge("generate_report", END)
        
        return workflow.compile()
    
    async def _select_question(self, state: InterviewState) -> InterviewState:
        """Выбрать или сгенерировать следующий вопрос."""
        print(f"\n🔍 Выбор вопроса...")
        print(f"Текущая тема: {state.get('current_topic', 'Не выбрана')}")
        print(f"Глубина темы: {state.get('topic_depth', 0)}")
        print(f"Заданные вопросы: {state.get('asked_questions', [])}")
        
        # Проверяем, не завершено ли интервью
        if state.get('is_complete', False):
            print("🏁 Интервью уже завершено - пропускаем выбор вопроса")
            return state
        
        # Логика выбора вопроса
        if not state.get('current_topic'):
            # Выбираем первую тему
            topics = list(self.questions.keys())
            state['current_topic'] = topics[0]
            state['topic_depth'] = 0
            print(f"🔧 Инициализация: тема={topics[0]}, глубина=0")
        
        topic = state['current_topic']
        asked_questions = state.get('asked_questions', [])
        topic_depth = state.get('topic_depth', 0)
        
        if topic_depth == 0:
            # Первый вопрос по теме - берем из файла
            if topic in self.questions and self.questions[topic].id not in asked_questions:
                question = self.questions[topic]
                # Добавляем вопрос в список заданных
                if 'asked_questions' not in state:
                    state['asked_questions'] = []
                state['asked_questions'].append(question.id)
            else:
                # Эта тема уже пройдена, переходим к следующей
                self._move_to_next_topic(state)
                # Если интервью завершено, возвращаем состояние
                if state.get('is_complete', False):
                    return state
                # Рекурсивно вызываем для новой темы
                return await self._select_question(state)
        else:
            # Генерируем следующий вопрос через ChatGPT
            question = await self._generate_next_question(state)
            if not question:
                # Не удалось сгенерировать вопрос, переходим к следующей теме
                self._move_to_next_topic(state)
                # Если интервью завершено, возвращаем состояние
                if state.get('is_complete', False):
                    return state
                # Рекурсивно вызываем для новой темы
                return await self._select_question(state)
            
        # Сохраняем сгенерированный вопрос в self.questions для отчета
        self.questions[question.id] = question
        
        # Добавляем сгенерированный вопрос в список заданных
        if 'asked_questions' not in state:
            state['asked_questions'] = []
        state['asked_questions'].append(question.id)
        
        state['current_question'] = question
        print(f"✅ Выбран вопрос: {question.text[:50]}...")
        
        return state
    
    async def _generate_next_question(self, state: InterviewState) -> Optional[Question]:
        """Сгенерировать следующий вопрос через ChatGPT."""
        print("🤖 Генерация следующего вопроса через ChatGPT...")
        
        topic = state['current_topic']
        topic_depth = state.get('topic_depth', 0)
        answers = state.get('answers', [])
        
        # Создаем контекст для генерации вопроса
        context = self._create_question_generation_context(state)
        
        # Логируем context для отладки
        print(f"🔍 CONTEXT для ChatGPT:")
        print(f"📋 {context}")
        print(f"👤 Имя кандидата: {self.candidate_name}")
        
        # Промпт для генерации вопроса
        generation_prompt = f"""
        Вы - HR-специалист, который ведет техническое интервью. Ваша задача - создать естественный диалог, углубляясь в тему "{topic}" на основе ответов кандидата.
        
        Контекст диалога:
        {context}
        
        Стиль общения:
        - Обращайтесь к кандидату по имени (используйте "{self.candidate_name}" или "вы")
        - Начинайте с положительной реакции на предыдущий ответ
        - Задавайте уточняющие вопросы, которые раскрывают опыт кандидата
        - Используйте фразы типа "Интересно!", "Отлично!", "Расскажите подробнее..."
        - Создавайте ощущение живого диалога, а не формального опроса
        
        Требования к вопросу:
        1. Углубляйтесь в тему на основе предыдущих ответов (глубина {topic_depth + 1})
        2. Задавайте конкретные технические вопросы, которые раскрывают опыт
        3. Используйте информацию из предыдущих ответов для персонализации
        4. Не повторяйте уже заданные вопросы
        5. Вопрос должен быть на русском языке
        6. Создавайте ощущение естественного диалога
        
        Примеры стиля:
        - "Отлично, {self.candidate_name}! Расскажите подробнее про ваш опыт с Django - какого масштаба проекты вы делали?"
        - "Интересный опыт! А как вы решали вопросы производительности при большом количестве заказов?"
        - "Хороший подход к тестированию! Расскажите, как вы организуете тестовые данные?"
        
        Ответ в формате JSON: {{"text": "текст вопроса", "difficulty": число_от_1_до_5}}
        """
        
        try:
            messages = [
                SystemMessage(content="Вы - опытный HR-специалист, который ведет технические интервью. Создавайте естественные диалоги, углубляясь в технические темы на основе ответов кандидата. Используйте дружелюбный, профессиональный тон."),
                HumanMessage(content=generation_prompt)
            ]
            
            response = await self.llm.ainvoke(messages)
            
            # Пытаемся распарсить JSON
            try:
                # Убираем markdown блоки если есть
                content = response.content.strip()
                if content.startswith('```json'):
                    content = content[7:]  # Убираем ```json
                if content.endswith('```'):
                    content = content[:-3]  # Убираем ```
                content = content.strip()
                
                question_data = json.loads(content)
                
                # Создаем объект Question из JSON
                question = Question(
                    id=f"{topic.lower().replace(' ', '_')}_generated_{topic_depth}",
                    text=question_data['text'],
                    topic=topic,
                    difficulty=question_data.get('difficulty', topic_depth + 1)
                )
            except json.JSONDecodeError:
                # Если JSON не парсится, создаем вопрос из текста
                print(f"⚠️ Не удалось распарсить JSON, используем текст как есть")
                question_text = response.content.strip()
                if question_text.startswith('"') and question_text.endswith('"'):
                    question_text = question_text[1:-1]  # Убираем кавычки
                
                question = Question(
                    id=f"{topic.lower().replace(' ', '_')}_generated_{topic_depth}",
                    text=question_text,
                    topic=topic,
                    difficulty=topic_depth + 1
                )
            
            print(f"✅ Сгенерирован вопрос: {question.text[:50]}...")
            return question
            
        except Exception as e:
            print(f"❌ Ошибка генерации вопроса: {e}")
            return None
    
    def _create_question_generation_context(self, state: InterviewState) -> str:
        """Создать контекст для генерации вопроса."""
        context_parts = []
        
        # Добавляем информацию о теме
        topic = state.get('current_topic', '')
        topic_depth = state.get('topic_depth', 0)
        context_parts.append(f"ТЕМА ДИАЛОГА: {topic}")
        context_parts.append(f"Глубина погружения в тему: {topic_depth + 1}")
        context_parts.append("")
        
        # Добавляем предыдущие вопросы и ответы по этой теме
        topic_answers = [
            answer for answer in state.get('answers', [])
            if any(q.topic == topic for q in self.questions.values() for q in [q] if q.id == answer.question_id)
        ]
        
        if topic_answers:
            context_parts.append("ИСТОРИЯ ДИАЛОГА:")
            for i, answer in enumerate(topic_answers[-3:], 1):  # Последние 3 ответа
                # Найти вопрос
                question = None
                for q in self.questions.values():
                    if q.id == answer.question_id:
                        question = q
                        break
                
                if question:
                    context_parts.append(f"🤖 Вопрос {i}: {question.text}")
                    context_parts.append(f"👤 Ответ кандидата: {answer.answer_text}")
                    context_parts.append(f"📊 Оценка ответа: {answer.score}/10")
                    context_parts.append("")
        else:
            context_parts.append("Это первый вопрос по теме - начинаем диалог.")
        
        context_parts.append("ЗАДАЧА: Создать следующий вопрос, который:")
        context_parts.append("- Углубляется в тему на основе предыдущих ответов")
        context_parts.append("- Раскрывает технический опыт кандидата")
        context_parts.append("- Создает ощущение живого диалога с HR-специалистом")
        
        return "\n".join(context_parts)
    
    async def _ask_question(self, question: Question, websocket) -> None:
        """Задать вопрос пользователю."""
        print(f"\n📝 Вопрос: {question.text}")
        print(f"🎤 Воспроизведение вопроса...")
        
        # Отправляем вопрос через WebSocket если есть
        if websocket and hasattr(websocket, 'client_state'):
            try:
                if websocket.client_state.name == "CONNECTED":
                    await websocket.send_text(json.dumps({
                        "type": "question",
                        "question": question.text,
                        "topic": question.topic,
                        "difficulty": question.difficulty
                    }))
            except Exception as e:
                print(f"⚠️ Ошибка отправки вопроса через WebSocket: {e}")
        
        # Отправляем вопрос в браузер для TTS
        try:
            print("🔊 Отправка вопроса в браузер для TTS...")
            print(f"🔊 Текст: {question.text}")
            
            # Устанавливаем WebSocket для браузерного TTS
            self.tts_driver.set_websocket(websocket)
            # Отправляем команду TTS в браузер
            await self.tts_driver.synthesize_to_browser(question.text)
            print("✅ Команда TTS отправлена в браузер")
            
            print("🎤 Готовы слушать ответ...")
            
        except Exception as e:
            print(f"⚠️ Ошибка отправки TTS команды: {e}")
            import traceback
            traceback.print_exc()
            print("📝 Продолжаем без озвучивания...")
        
    async def process_audio_response(self, room, websocket, audio_file_path: str):
        """Обработать аудио ответ от пользователя."""
        try:
            import tempfile
            import os
            import subprocess
            import numpy as np
            
            print(f"🎤 Обработка аудио ответа: {audio_file_path}")
            
            # Конвертируем WebM в WAV для обработки
            wav_file_path = audio_file_path.replace('.webm', '.wav')
            
            try:
                # Используем ffmpeg для конвертации
                subprocess.run([
                    'ffmpeg', '-i', audio_file_path, 
                    '-ar', '16000',  # 16kHz sample rate
                    '-ac', '1',      # mono
                    '-y',            # overwrite output file
                    wav_file_path
                ], check=True, capture_output=True)
                
                # Загружаем аудио файл
                import soundfile as sf
                audio_data, sample_rate = sf.read(wav_file_path)
                
                print(f"✅ Аудио загружено: {len(audio_data)} samples, {sample_rate} Hz")
                
                # Распознавание речи через OpenAI API
                print("🔄 Распознавание речи через OpenAI API...")
                answer_text = ""
                try:
                    # Используем OpenAI Whisper API
                    from openai import OpenAI
                    client = OpenAI(api_key=self.config.get('openai_api_key'))
                    
                    with open(wav_file_path, 'rb') as audio_file:
                        transcript = client.audio.transcriptions.create(
                            model="whisper-1",
                            file=audio_file,
                            language="ru"
                        )
                    answer_text = transcript.text.strip()
                    print(f"✅ Распознанный текст: {answer_text}")
                except Exception as e:
                    print(f"⚠️ Ошибка распознавания речи: {e}")
                    answer_text = "Не удалось распознать речь"
                
                # Анализ эмоций
                emotion_analysis = None
                try:
                    print("🎭 Анализ эмоций...")
                    emotion_analysis = self.emotion_analyzer.analyze_emotion(audio_data, sample_rate)
                    print(f"🎭 Эмоция: {emotion_analysis['primary_emotion']} (уверенность: {emotion_analysis['confidence']:.3f})")
                except Exception as e:
                    print(f"⚠️ Ошибка анализа эмоций: {e}")
                    emotion_analysis = {
                        'primary_emotion': 'error',
                        'confidence': 0.0,
                        'emotions': {},
                        'error': str(e)
                    }
        
                # Отправляем ответ в браузер
                if websocket.client_state.name == "CONNECTED":
                    await websocket.send_text(json.dumps({
                        "type": "answer",
                        "answer": answer_text,
                        "emotion": emotion_analysis['primary_emotion'] if emotion_analysis else 'unknown'
                    }))
                
                # Обрабатываем ответ через систему интервью
                await self._process_answer(answer_text, emotion_analysis, room, websocket)
                
            finally:
                # Удаляем временный WAV файл
                if os.path.exists(wav_file_path):
                    os.unlink(wav_file_path)
                    print(f"🗑️ Временный WAV файл удален: {wav_file_path}")
                else:
                    print(f"⚠️ WAV файл уже не существует: {wav_file_path}")
                    
        except Exception as e:
            print(f"❌ Ошибка обработки аудио ответа: {e}")
            if websocket.client_state.name == "CONNECTED":
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": f"Ошибка обработки ответа: {str(e)}"
                }))
    
    async def _process_answer(self, answer_text: str, emotion_analysis: dict, room, websocket):
        """Обработать распознанный ответ."""
        try:
            # Получаем текущий вопрос из состояния системы
            current_question = getattr(room.interview_system, 'current_question', None)
            if not current_question:
                print("⚠️ Нет текущего вопроса")
                return
            
            # Создаем объект ответа
            import asyncio
        
            answer = Answer(
                question_id=current_question.id,
                answer_text=answer_text,
                score=0,  # Будет заполнено при оценке
                evaluation="",
                timestamp=str(asyncio.get_event_loop().time()),
                emotion_analysis=emotion_analysis
            )
            
            # Оцениваем ответ
            print("📊 Оценка ответа...")
            evaluation_result = await self._evaluate_single_answer(current_question, answer)
            answer.score = evaluation_result['score']
            answer.evaluation = evaluation_result['evaluation']
            
            print(f"📊 Оценка: {answer.score}/10")
            print(f"📝 Комментарий: {answer.evaluation}")
            
            # Оценка не отправляется клиенту - это внутренняя информация системы
            
            # Сохраняем ответ
            if not hasattr(room.interview_system, 'answers'):
                room.interview_system.answers = []
            room.interview_system.answers.append(answer)
            
            # Обновляем состояние системы
            if not hasattr(room.interview_system, 'asked_questions'):
                room.interview_system.asked_questions = []
            if not hasattr(room.interview_system, 'current_topic'):
                room.interview_system.current_topic = None
            if not hasattr(room.interview_system, 'topic_depth'):
                room.interview_system.topic_depth = 0
            
            # Обновляем состояние системы с текущим вопросом
            room.interview_system.current_question = current_question
            
            # Отправляем результат оценки пользователю
            if websocket and hasattr(websocket, 'client_state'):
                try:
                    if websocket.client_state.name == "CONNECTED":
                        await websocket.send_text(json.dumps({
                            "type": "answer_evaluated",
                            "message": f"Ответ оценен: {answer.score}/10",
                            "score": answer.score,
                            "evaluation": answer.evaluation
                        }))
                except Exception as e:
                    print(f"⚠️ Ошибка отправки результата оценки: {e}")
            
            # Продолжаем интервью
            print("🔄 Продолжение интервью...")
            await self._continue_interview(room, websocket)
            
        except Exception as e:
            print(f"❌ Ошибка обработки ответа: {e}")
            if websocket.client_state.name == "CONNECTED":
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": f"Ошибка обработки ответа: {str(e)}"
                }))
    
    async def _evaluate_single_answer(self, question, answer):
        """Оценить один ответ через ChatGPT."""
        try:
            # Создаем контекст для оценки
            context = f"""
Вопрос: {question.text}
Ответ кандидата: {answer.answer_text}
Эмоция: {answer.emotion_analysis.get('primary_emotion', 'unknown') if answer.emotion_analysis else 'unknown'}
"""
            
            # Промпт для оценки
            evaluation_prompt = f"""
Вы - опытный HR-специалист, проводящий техническое интервью. Оцените ответ кандидата по шкале от 0 до 10.

Контекст:
{context}

Критерии оценки:
- 0-3: Ответ неполный, не по теме, показывает незнание
- 4-6: Ответ частично правильный, но поверхностный
- 7-8: Хороший ответ, показывает понимание темы
- 9-10: Отличный ответ, глубокое понимание, практический опыт

Верните ответ в формате JSON:
{{
    "score": <число от 0 до 10>,
    "evaluation": "<подробный комментарий на русском языке>"
}}
"""
            
            # Отправляем запрос к ChatGPT
            response = await self.llm.ainvoke(evaluation_prompt)
            evaluation_text = response.content.strip()
            
            # Парсим JSON ответ
            import json
            try:
                # Извлекаем JSON из ответа
                if "```json" in evaluation_text:
                    json_start = evaluation_text.find("```json") + 7
                    json_end = evaluation_text.find("```", json_start)
                    json_text = evaluation_text[json_start:json_end].strip()
                elif "{" in evaluation_text and "}" in evaluation_text:
                    json_start = evaluation_text.find("{")
                    json_end = evaluation_text.rfind("}") + 1
                    json_text = evaluation_text[json_start:json_end]
                else:
                    json_text = evaluation_text
                
                result = json.loads(json_text)
                return {
                    'score': int(result.get('score', 0)),
                    'evaluation': result.get('evaluation', 'Оценка не получена')
                }
            except json.JSONDecodeError:
                # Fallback если JSON не парсится
                return {
                    'score': 5,
                    'evaluation': f"Ошибка парсинга оценки. Ответ ChatGPT: {evaluation_text}"
                }
                
        except Exception as e:
            print(f"⚠️ Ошибка оценки ответа: {e}")
            return {
                'score': 0,
                'evaluation': f"Ошибка оценки: {str(e)}"
            }
    
    async def _continue_interview(self, room, websocket):
        """Продолжить интервью после получения ответа."""
        try:
            # Получаем текущее состояние
            current_topic = getattr(room.interview_system, 'current_topic', None)
            topic_depth = getattr(room.interview_system, 'topic_depth', 0)
            max_depth = getattr(room.interview_system, 'max_depth', 5)
            min_threshold = getattr(room.interview_system, 'min_score_threshold', 2)
            
            # Оцениваем последний ответ
            if room.interview_system.answers:
                last_answer = room.interview_system.answers[-1]
                score = last_answer.score
                
                print(f"\n🔍 Анализ результата:")
                print(f"Оценка: {score}/10")
                print(f"Порог: {min_threshold}/10")
                print(f"Глубина темы: {topic_depth}/{max_depth}")
                
                if score >= min_threshold and topic_depth < max_depth:
                    # Хороший ответ, генерируем уточняющий вопрос
                    print(f"✅ Ответ хороший - генерируем уточняющий вопрос (глубина: {topic_depth} -> {topic_depth + 1})")
                    room.interview_system.topic_depth = topic_depth + 1
                    await self._generate_follow_up_question(room, websocket)
                else:
                    # Плохой ответ или достигли максимальной глубины - переходим к следующему изначальному вопросу
                    print("❌ Переходим к следующему изначальному вопросу")
                    await self._move_to_next_initial_question(room, websocket)
            else:
                # Нет ответов - переходим к следующему вопросу
                await self._move_to_next_initial_question(room, websocket)
            
        except Exception as e:
            print(f"❌ Ошибка продолжения интервью: {e}")
            if websocket.client_state.name == "CONNECTED":
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": f"Ошибка продолжения интервью: {str(e)}"
                }))
    
    async def _generate_question_with_chatgpt(self, question_text: str, answer_text: str, emotion: str, score: int, answers: list, asked_questions: list) -> str:
        """Генерировать уточняющий вопрос через ChatGPT."""
        try:
            # Создаем контекст для ChatGPT
            context_parts = []
            context_parts.append(f"Предыдущий вопрос: {question_text}")
            context_parts.append(f"Ответ кандидата: {answer_text}")
            context_parts.append(f"Эмоция: {emotion}")
            context_parts.append(f"Оценка: {score}/10")
            
            if answers:
                context_parts.append("\nИстория ответов:")
                for i, ans in enumerate(answers[-3:], 1):  # Последние 3 ответа
                    context_parts.append(f"{i}. {ans.answer_text} (оценка: {ans.score}/10)")
            
            if asked_questions:
                context_parts.append("\nЗаданные вопросы:")
                for i, q in enumerate(asked_questions[-3:], 1):  # Последние 3 вопроса
                    context_parts.append(f"{i}. {q.text}")
            
            context = "\n".join(context_parts)
            
            # Создаем промпт для генерации уточняющего вопроса
            prompt = f"""
На основе следующего контекста сгенерируй уточняющий вопрос для технического интервью:

{context}

Требования к уточняющему вопросу:
1. Должен углубляться в тему предыдущего вопроса
2. Должен быть более сложным и детальным
3. Должен требовать развернутого ответа
4. Должен быть на русском языке
5. Должен быть профессиональным и релевантным

Сгенерируй только текст вопроса, без дополнительных комментариев.
"""
            
            # Используем ChatGPT для генерации вопроса
            messages = [
                SystemMessage(content="Ты - опытный HR-специалист, проводящий техническое интервью. Генерируешь уточняющие вопросы на основе ответов кандидата."),
                HumanMessage(content=prompt)
            ]
            
            response = await self.llm.ainvoke(messages)
            generated_question = response.content.strip()
            
            print(f"🤖 Сгенерирован уточняющий вопрос: {generated_question}")
            return generated_question
            
        except Exception as e:
            print(f"❌ Ошибка генерации вопроса через ChatGPT: {e}")
            return None
    
    async def _generate_follow_up_question(self, room, websocket):
        """Генерировать уточняющий вопрос на основе предыдущего ответа."""
        try:
            # Получаем последний ответ и вопрос
            last_answer = room.interview_system.answers[-1]
            current_question = getattr(room.interview_system, 'current_question', None)
            
            if not current_question:
                print("⚠️ Нет текущего вопроса для генерации уточняющего")
                await self._move_to_next_initial_question(room, websocket)
                return
            
            # Генерируем уточняющий вопрос через ChatGPT
            follow_up_question = await self._generate_question_with_chatgpt(
                current_question.text,
                last_answer.answer_text,
                last_answer.emotion_analysis['primary_emotion'] if last_answer.emotion_analysis else 'unknown',
                last_answer.score,
                room.interview_system.answers,
                room.interview_system.asked_questions
            )
            
            if follow_up_question:
                # Создаем новый объект Question для уточняющего вопроса
                follow_up = Question(
                    id=f"{current_question.id}_followup_{room.interview_system.topic_depth}",
                    text=follow_up_question,
                    topic=current_question.topic,
                    difficulty=min(current_question.difficulty + 1, 5),
                    follow_up_questions=[]
                )
                
                # Устанавливаем как текущий вопрос
                room.interview_system.current_question = follow_up
                room.interview_system.asked_questions.append(follow_up)
                
                # Задаем вопрос
                await self._ask_question(follow_up, websocket)
            else:
                print("❌ Не удалось сгенерировать уточняющий вопрос")
                await self._move_to_next_initial_question(room, websocket)
                
        except Exception as e:
            print(f"❌ Ошибка генерации уточняющего вопроса: {e}")
            await self._move_to_next_initial_question(room, websocket)
    
    async def _move_to_next_initial_question(self, room, websocket):
        """Перейти к следующему изначальному вопросу."""
        try:
            # Получаем список изначальных тем
            initial_topics = list(room.interview_system.raw_questions.keys())
            current_topic = getattr(room.interview_system, 'current_topic', None)
            asked_questions = getattr(room.interview_system, 'asked_questions', [])
            
            # Находим следующий не заданный изначальный вопрос
            next_topic = None
            for topic in initial_topics:
                # Проверяем, был ли уже задан изначальный вопрос по этой теме
                topic_asked = any(q.topic == topic and q.difficulty == 1 for q in asked_questions)
                if not topic_asked:
                    next_topic = topic
                    break
            
            if next_topic:
                # Переходим к следующей теме
                room.interview_system.current_topic = next_topic
                room.interview_system.topic_depth = 0  # Сбрасываем глубину
                
                # Получаем изначальный вопрос по теме
                initial_question = room.interview_system.questions[next_topic]
                room.interview_system.current_question = initial_question
                room.interview_system.asked_questions.append(initial_question)
                
                print(f"➡️ Переходим к следующей теме: {next_topic}")
                
                # Задаем изначальный вопрос
                await self._ask_question(initial_question, websocket)
            else:
                # Все изначальные вопросы заданы - завершаем интервью
                print("✅ Все изначальные вопросы заданы - завершаем интервью")
                await self._complete_interview(room, websocket)
                
        except Exception as e:
            print(f"❌ Ошибка перехода к следующему вопросу: {e}")
            await self._complete_interview(room, websocket)
    
    async def _complete_interview(self, room, websocket):
        """Завершить интервью и создать отчет."""
        try:
            # Создаем отчет
            report = {
                'candidate_name': getattr(room.interview_system, 'candidate_name', 'Кандидат'),
                'total_questions': len(room.interview_system.asked_questions),
                'total_answers': len(room.interview_system.answers),
                'average_score': sum(a.score for a in room.interview_system.answers) / len(room.interview_system.answers) if room.interview_system.answers else 0,
                'questions_asked': [
                    {
                        'id': q.id,
                        'text': q.text,
                        'topic': q.topic,
                        'difficulty': q.difficulty
                    } for q in room.interview_system.asked_questions
                ],
                'answers': [
                    {
                        'question_id': a.question_id,
                        'text': a.answer_text,
                        'score': a.score,
                        'emotion': a.emotion_analysis['primary_emotion'] if a.emotion_analysis else 'unknown',
                        'evaluation': a.evaluation
                    } for a in room.interview_system.answers
                ],
                'completion_time': str(datetime.now())
            }
            
            # Отправляем отчет в Kafka
            try:
                success = publish_report_to_kafka(report)
                if success:
                    print(f"📊 Отчет отправлен в Kafka топик step3")
                else:
                    print(f"⚠️ Не удалось отправить отчет в Kafka, сохраняем в файл")
                    # Fallback: сохраняем в файл если Kafka недоступна
                    report_file = f"interview_report_{room.room_id}.json"
                    with open(report_file, 'w', encoding='utf-8') as f:
                        json.dump(report, f, ensure_ascii=False, indent=2)
                    print(f"📊 Отчет сохранен в файл: {report_file}")
            except Exception as kafka_error:
                print(f"❌ Ошибка отправки в Kafka: {kafka_error}")
                # Fallback: сохраняем в файл
                report_file = f"interview_report_{room.room_id}.json"
                with open(report_file, 'w', encoding='utf-8') as f:
                    json.dump(report, f, ensure_ascii=False, indent=2)
                print(f"📊 Отчет сохранен в файл: {report_file}")
            
            # Отправляем сообщение о завершении (без оценок)
            if websocket.client_state.name == "CONNECTED":
                await websocket.send_text(json.dumps({
                    "type": "interview_complete",
                    "message": "Интервью завершено! Спасибо за участие.",
                    "total_questions": report['total_questions']
                }))
                
        except Exception as e:
            print(f"❌ Ошибка завершения интервью: {e}")
    
    async def run_interview_step(self, state):
        """Выполнить один шаг интервью."""
        try:
            # Выбираем следующий вопрос
            updated_state = await self._select_question(state)
            if updated_state.get('is_complete', False):
                # Интервью завершено
                await self._complete_interview(updated_state)
                return
            
            next_question = updated_state.get('current_question')
            if not next_question:
                # Интервью завершено
                await self._complete_interview(updated_state)
                return
            
            # Сохраняем текущий вопрос в системе интервью
            self.current_question = next_question
            
            # Задаем вопрос
            await self._ask_question(updated_state)
            
        except Exception as e:
            print(f"❌ Ошибка выполнения шага интервью: {e}")
    
    async def _get_answer(self, state: InterviewState) -> InterviewState:
        """Получить ответ пользователя из браузера."""
        print("🎤 Ожидание аудио от браузера...")
        
        # Отправляем сигнал о готовности к получению ответа
        if state.get('websocket') and hasattr(state['websocket'], 'client_state'):
            try:
                if state['websocket'].client_state.name == "CONNECTED":
                    await state['websocket'].send_text(json.dumps({
                        "type": "waiting_for_answer",
                        "question": state['current_question'].text
                    }))
            except Exception as e:
                print(f"⚠️ Ошибка отправки сигнала ожидания: {e}")
        
        # В браузерном режиме мы ждем ответа от пользователя
        # Устанавливаем флаг ожидания ответа
        state['waiting_for_answer'] = True
        state['answer_received'] = False
        
        # Возвращаем состояние без перехода к следующему шагу
        # Переход произойдет только после получения ответа через WebSocket
        return state
    
    async def _evaluate_answer(self, state: InterviewState) -> InterviewState:
        """Оценить ответ пользователя."""
        print("🤖 Оценка ответа...")
        
        current_answer = state['answers'][-1]
        question = state['current_question']
        
        # Создаем контекст для оценки
        context = self._create_evaluation_context(state)
        
        # Промпт для оценки
        evaluation_prompt = f"""
        {self.config['evaluation_prompt']}
        
        Вопрос: {question.text}
        Ответ: {current_answer.answer_text}
        
        Контекст предыдущих вопросов:
        {context}
        
        Оцените ответ по шкале 1-10 и дайте краткий комментарий.
        Ответ в формате JSON: {{"score": число, "evaluation": "комментарий"}}
        """
        
        # Отправляем запрос в OpenAI
        messages = [
            SystemMessage(content="Вы - эксперт по техническим интервью. Оценивайте ответы объективно и конструктивно."),
            HumanMessage(content=evaluation_prompt)
        ]
        
        response = await self.llm.ainvoke(messages)
        
        try:
            # Убираем markdown блоки если есть
            content = response.content.strip()
            if content.startswith('```json'):
                content = content[7:]  # Убираем ```json
            if content.endswith('```'):
                content = content[:-3]  # Убираем ```
            content = content.strip()
            
            evaluation = json.loads(content)
            current_answer.score = evaluation['score']
            current_answer.evaluation = evaluation['evaluation']
        except json.JSONDecodeError:
            # Fallback если JSON не парсится
            print(f"⚠️ Не удалось распарсить JSON оценки, используем fallback")
            current_answer.score = 5
            current_answer.evaluation = "Ошибка при оценке ответа"
        except KeyError as e:
            print(f"⚠️ Отсутствует ключ в JSON: {e}")
            current_answer.score = 5
            current_answer.evaluation = "Ошибка при оценке ответа"
        
        print(f"📊 Оценка: {current_answer.score}/10")
        print(f"💬 Комментарий: {current_answer.evaluation}")
        
        return state
    
    def _create_evaluation_context(self, state: InterviewState) -> str:
        """Создать контекст для оценки ответа."""
        context_parts = []
        
        for answer in state.get('answers', []):
            # Найти вопрос по ID
            question = None
            for q in self.questions.values():
                if q.id == answer.question_id:
                    question = q
                    break
            
            if question:
                context_parts.append(f"Вопрос: {question.text}")
                context_parts.append(f"Ответ: {answer.answer_text}")
                context_parts.append(f"Оценка: {answer.score}/10")
                context_parts.append("---")
        
        return "\n".join(context_parts)
    
    async def _update_state(self, state: InterviewState) -> InterviewState:
        """Обновить состояние на основе оценки ответа."""
        current_answer = state['answers'][-1]
        score = current_answer.score
        topic_depth = state.get('topic_depth', 0)
        max_depth = self.config['max_depth']
        min_threshold = self.config['min_score_threshold']
        
        print(f"\n🔍 Анализ результата:")
        print(f"Оценка: {score}/10")
        print(f"Порог: {min_threshold}/10")
        print(f"Глубина темы: {topic_depth}/{max_depth}")
        
        # Проверяем, не завершено ли интервью
        if state.get('is_complete', False):
            print("🏁 Интервью завершено")
            return state
        
        if score >= min_threshold and topic_depth < max_depth:
            # Хороший ответ, продолжаем тему
            new_depth = topic_depth + 1
            state['topic_depth'] = new_depth
            print(f"✅ Продолжаем тему - ответ хороший (глубина: {topic_depth} -> {new_depth})")
        elif topic_depth >= max_depth:
            # Достигли максимальной глубины
            print("📈 Достигли максимальной глубины темы")
            # Переходим к следующей теме
            self._move_to_next_topic(state)
        else:
            # Плохой ответ, переходим к следующей теме
            print("➡️ Переходим к следующей теме - ответ недостаточно хороший")
            self._move_to_next_topic(state)
        
        return state
    
    def _move_to_next_topic(self, state: InterviewState):
        """Перейти к следующей теме."""
        topics = list(self.questions.keys())
        current_topic = state.get('current_topic')
        
        if current_topic in topics:
            current_index = topics.index(current_topic)
            if current_index + 1 < len(topics):
                state['current_topic'] = topics[current_index + 1]
                state['topic_depth'] = 0
                print(f"➡️ Переходим к теме: {state['current_topic']}")
            else:
                # Все темы пройдены
                state['is_complete'] = True
                print("🏁 Все темы пройдены")
        else:
            state['is_complete'] = True
            print("🏁 Все темы пройдены")
    
    def _should_continue(self, state: InterviewState) -> str:
        """Определить, что делать дальше после обновления состояния."""
        # Проверяем, не завершено ли интервью
        if state.get('is_complete', False):
            return "complete"
        
        # Проверяем, нужно ли перейти к следующей теме
        current_topic = state.get('current_topic')
        topics = list(self.questions.keys())
        
        if current_topic in topics:
            current_index = topics.index(current_topic)
            # Если это последняя тема, завершаем
            if current_index >= len(topics) - 1:
                state['is_complete'] = True
                return "complete"
        
        # Продолжаем с текущей темой (может быть новой после перехода)
        return "continue_topic"
    
    async def _generate_report(self, state: InterviewState) -> InterviewState:
        """Сгенерировать итоговый отчет."""
        print("\n📋 Генерация отчета...")
        
        # Анализ эмоций для всех ответов
        emotion_analyses = [answer.emotion_analysis for answer in state['answers'] if answer.emotion_analysis]
        emotion_summary = self.emotion_analyzer.get_emotion_summary(emotion_analyses)
        
        report = {
            "candidate_name": getattr(self, 'candidate_name', 'Кандидат'),
            "interview_id": f"interview_{int(datetime.now().timestamp())}",
            "completion_time": str(datetime.now()),
            "total_questions": len(state['answers']),
            "topics_covered": list(set(q.topic for q in self.questions.values() if q.id in state.get('asked_questions', []))),
            "average_score": sum(a.score for a in state['answers']) / len(state['answers']) if state['answers'] else 0,
            "emotion_analysis": {
                "most_common_emotion": emotion_summary['most_common_emotion'],
                "emotion_distribution": emotion_summary['emotion_distribution'],
                "average_confidence": emotion_summary['average_confidence'],
                "total_analyses": emotion_summary['total_analyses']
            },
            "answers": []
        }
        
        for answer in state['answers']:
            # Найти вопрос
            question = None
            for q in self.questions.values():
                if q.id == answer.question_id:
                    question = q
                    break
            
            answer_data = {
                "question_id": answer.question_id,
                "question_text": question.text if question else "Неизвестный вопрос",
                "topic": question.topic if question else "Неизвестная тема",
                "difficulty": question.difficulty if question else 0,
                "answer_text": answer.answer_text,
                "score": answer.score,
                "evaluation": answer.evaluation,
                "timestamp": answer.timestamp
            }
            
            # Добавляем анализ эмоций если есть
            if answer.emotion_analysis:
                answer_data["emotion_analysis"] = {
                    "primary_emotion": answer.emotion_analysis['primary_emotion'],
                    "confidence": answer.emotion_analysis['confidence'],
                    "emotions": answer.emotion_analysis['emotions']
                }
            
            report['answers'].append(answer_data)
        
        state['interview_report'] = report
        
        # Отправляем отчет в Kafka
        try:
            success = publish_report_to_kafka(report)
            if success:
                print("✅ Отчет отправлен в Kafka топик step3")
            else:
                print("⚠️ Не удалось отправить отчет в Kafka, сохраняем в файл")
                # Fallback: сохраняем в файл если Kafka недоступна
                with open('technical_interview_report.json', 'w', encoding='utf-8') as f:
                    json.dump(report, f, ensure_ascii=False, indent=2)
                print("✅ Отчет сохранен в technical_interview_report.json")
        except Exception as kafka_error:
            print(f"❌ Ошибка отправки в Kafka: {kafka_error}")
            # Fallback: сохраняем в файл
            with open('technical_interview_report.json', 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            print("✅ Отчет сохранен в technical_interview_report.json")
        
        return state
    
    async def run_interview(self, websocket=None):
        """Запустить интервью."""
        print("🚀 ЗАПУСК ТЕХНИЧЕСКОГО ИНТЕРВЬЮ")
        print("=" * 50)
        
        # Инициализация состояния
        initial_state = InterviewState(
            current_question=None,
            answers=[],
            asked_questions=[],
            current_topic=None,
            topic_depth=0,
            max_depth=self.config['max_depth'],
            min_score_threshold=self.config['min_score_threshold'],
            is_complete=False,
            interview_report=None,
            websocket=websocket  # Добавляем WebSocket в состояние
        )
        
        # Инициализируем состояние системы интервью
        self.answers = []
        self.asked_questions = []
        self.current_topic = None
        self.topic_depth = 0
        self.current_question = None
        
        # Начинаем с первого изначального вопроса
        try:
            # Получаем первую тему
            first_topic = list(self.raw_questions.keys())[0]
            self.current_topic = first_topic
            self.topic_depth = 0
            
            # Получаем первый изначальный вопрос
            first_question = self.questions[first_topic]
            self.current_question = first_question
            self.asked_questions.append(first_question)
            
            print(f"🎯 Начинаем с темы: {first_topic}")
            
            # Задаем первый вопрос и ждем ответа пользователя
            await self._ask_question(first_question, websocket)
            
            # НЕ запускаем автоматический цикл - ждем реального ответа пользователя
            print("🎤 Готовы слушать ответ пользователя...")
            
            # НЕ завершаем метод - ждем дальнейших взаимодействий
            # Интервью будет продолжаться через process_audio_response
            
        except Exception as e:
            print(f"❌ Ошибка запуска интервью: {e}")
            import traceback
            traceback.print_exc()
        
        # НЕ возвращаем состояние - метод должен продолжать работать
        # return initial_state


async def main():
    """Главная функция."""
    print("🚀 ТЕХНИЧЕСКОЕ ИНТЕРВЬЮ С АДАПТИВНЫМИ ВОПРОСАМИ")
    print("=" * 60)
    
    # Конфигурация
    CONFIG_FILE = "interview_config.json"
    
    # Проверяем наличие файла конфигурации
    if not Path(CONFIG_FILE).exists():
        print(f"❌ Ошибка: Файл {CONFIG_FILE} не найден")
        return
    
    # Вопросы по умолчанию для тестирования
    questions = {
        "Java Backend": {
            "id": "java_start",
            "text": "Скажите вы разработчик, четкий ответ да/нет?"
        },
        "Java Core": {
            "id": "java_core_start", 
            "text": "Скажите вы умный, четкий ответ да/нет?"
        },
        "Spring Framework": {
            "id": "spring_start",
            "text": "Скажите вы пунктуальный, четкий ответ да/нет?"
        }
    }
    
    try:
        # Создание системы
        print("🔧 Инициализация системы...")
        system = TechnicalInterviewSystem(
            questions=questions,
            config_file=CONFIG_FILE
        )
        
        print("✅ Система инициализирована")
        print("\n📋 Конфигурация:")
        print(f"  - Максимальная глубина: {system.config['max_depth']}")
        print(f"  - Минимальный порог: {system.config['min_score_threshold']}/10")
        
        print("\n🎯 Начинаем интервью...")
        print("=" * 60)
        
        # Запуск интервью
        result = await system.run_interview()
        
        print("\n🎉 ИНТЕРВЬЮ ЗАВЕРШЕНО!")
        print("=" * 60)
        
        if result['interview_report']:
            report = result['interview_report']
            print(f"📊 Статистика:")
            print(f"  - Всего вопросов: {report['total_questions']}")
            print(f"  - Покрытые темы: {', '.join(report['topics_covered'])}")
            print(f"  - Средняя оценка: {report['average_score']:.1f}/10")
            print(f"  - Отчет сохранен: technical_interview_report.json")
        
    except KeyboardInterrupt:
        print("\n\n⏹️ Интервью прервано пользователем")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
