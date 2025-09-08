#!/usr/bin/env python3
"""
Веб-сервер для системы технических интервью с WebRTC
"""

import asyncio
import json
import uuid
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

from langgraph_interview import TechnicalInterviewSystem
from room_manager import get_room_manager
from kafka_consumer import start_kafka_consumer


@dataclass
class InterviewRoom:
    """Комната интервью."""
    room_id: str
    questions: Dict[str, Any]
    interview_system: TechnicalInterviewSystem
    created_at: float
    is_active: bool = True
    participants: List[str] = None  # WebSocket connections
    
    def __post_init__(self):
        if self.participants is None:
            self.participants = []


class CreateRoomRequest(BaseModel):
    """Запрос на создание комнаты."""
    questions: Dict[str, Any]
    candidate_name: str = "Алексей"  # Имя кандидата по умолчанию


class JoinRoomRequest(BaseModel):
    """Запрос на подключение к комнате."""
    room_code: str


class InterviewServer:
    """Сервер интервью."""
    
    def __init__(self):
        self.app = FastAPI(title="Interview System API", version="1.0.0")
        self.rooms: Dict[str, InterviewRoom] = {}
        self.active_connections: Dict[str, WebSocket] = {}
        self.room_manager = get_room_manager()
        self.setup_middleware()
        self.setup_routes()
        self.setup_kafka_consumer()
        self.setup_startup_events()
    
    def setup_middleware(self):
        """Настройка CORS и middleware."""
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    def setup_kafka_consumer(self):
        """Настройка Kafka consumer для получения сообщений из step1."""
        print("🔧 Настройка Kafka consumer...")
        
        # Создаем обработчик сообщений
        async def handle_kafka_message(message_data: Dict[str, Any]):
            """Обработать сообщение из Kafka."""
            try:
                await self.room_manager.handle_kafka_message(message_data)
            except Exception as e:
                print(f"❌ Ошибка обработки Kafka сообщения: {e}")
        
        # Сохраняем обработчик для запуска в startup event
        self.kafka_message_handler = handle_kafka_message
        print("✅ Kafka consumer настроен")

    def setup_startup_events(self):
        """Настройка startup events."""
        @self.app.on_event("startup")
        async def startup_event():
            """Запуск Kafka consumer при старте приложения."""
            print("🚀 Запуск Kafka consumer...")
            print(f"🔧 Handler: {self.kafka_message_handler}")
            try:
                # Запускаем Kafka consumer в фоновой задаче
                print("🔧 Вызываем start_kafka_consumer...")
                start_kafka_consumer(self.kafka_message_handler)
                print("✅ Kafka consumer запущен")
                # Не ждем завершения задачи, чтобы не блокировать startup
            except Exception as e:
                print(f"❌ Ошибка запуска Kafka consumer: {e}")
                import traceback
                traceback.print_exc()
    
    def setup_routes(self):
        """Настройка маршрутов API."""
        
        @self.app.get("/")
        async def root():
            return {"message": "Interview System API", "status": "running"}
        
        @self.app.post("/api/rooms/create")
        async def create_room(request: CreateRoomRequest):
            """Создать новую комнату интервью."""
            try:
                # Генерируем уникальный код комнаты
                room_code = self.generate_room_code()
                
                # Создаем систему интервью с вопросами напрямую
                interview_system = TechnicalInterviewSystem(
                    questions=request.questions,
                    config_file="interview_config.json",
                    candidate_name=request.candidate_name
                )
                
                # Создаем комнату
                room = InterviewRoom(
                    room_id=room_code,
                    questions=request.questions,
                    interview_system=interview_system,
                    created_at=time.time()
                )
                
                self.rooms[room_code] = room
                
                return {
                    "success": True,
                    "room_code": room_code,
                    "web_url": f"/room/{room_code}",
                    "message": "Комната создана успешно"
                }
                
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Ошибка создания комнаты: {str(e)}")
        
        @self.app.get("/api/rooms/{room_code}/status")
        async def get_room_status(room_code: str):
            """Получить статус комнаты."""
            if room_code not in self.rooms:
                raise HTTPException(status_code=404, detail="Комната не найдена")
            
            room = self.rooms[room_code]
            return {
                "room_id": room.room_id,
                "is_active": room.is_active,
                "participants_count": len(room.participants),
                "created_at": room.created_at
            }
        
        @self.app.websocket("/ws/{room_code}")
        async def websocket_endpoint(websocket: WebSocket, room_code: str):
            """WebSocket подключение к комнате."""
            await websocket.accept()
            
            room_data = self.room_manager.get_room(room_code)
            if not room_data:
                await websocket.close(code=4004, reason="Комната не найдена")
                return
            
            connection_id = str(uuid.uuid4())
            self.active_connections[connection_id] = websocket
            
            try:
                # Отправляем информацию о комнате
                await websocket.send_text(json.dumps({
                    "type": "room_info",
                    "room_code": room_code,
                    "status": "connected"
                }))
                
                # Обрабатываем сообщения
                while True:
                    data = await websocket.receive_text()
                    message = json.loads(data)
                    await self.handle_websocket_message(room_code, connection_id, message)
                    
            except WebSocketDisconnect:
                pass
            except Exception as e:
                print(f"Ошибка WebSocket: {e}")
            finally:
                # Очищаем соединение
                if connection_id in self.active_connections:
                    del self.active_connections[connection_id]
        
        @self.app.get("/room/{room_code}")
        async def room_page(room_code: str):
            """Страница комнаты интервью."""
            # Проверяем комнату в RoomManager
            room_data = self.room_manager.get_room(room_code)
            if not room_data:
                return HTMLResponse(content="<h1>Комната не найдена</h1>", status_code=404)
            
            html_content = self.get_room_html(room_code, room_data)
            return HTMLResponse(content=html_content)
    
    def generate_room_code(self) -> str:
        """Генерировать код комнаты."""
        return str(uuid.uuid4())[:8].upper()
    
    async def handle_websocket_message(self, room_code: str, connection_id: str, message: Dict[str, Any]):
        """Обработать сообщение WebSocket."""
        room_data = self.room_manager.get_room(room_code)
        if not room_data:
            return
            
        websocket = self.active_connections[connection_id]
        
        message_type = message.get("type")
        
        if message_type == "start_interview":
            await self.start_interview(room_code, room_data, websocket)
        elif message_type == "audio_data":
            await self.handle_audio_data(room_code, room_data, websocket, message.get("audio_data"))
        elif message_type == "next_question":
            await self.ask_next_question(room_code, room_data, websocket)
        elif message_type == "end_interview":
            await self.end_interview(room_code, room_data, websocket)
    
    async def start_interview(self, room_code: str, room_data: Dict[str, Any], websocket: WebSocket):
        """Начать интервью."""
        try:
            # Инициализируем систему интервью если еще не инициализирована
            if not room_data.get("interview_system"):
                from langgraph_interview import TechnicalInterviewSystem
                
                # Создаем вопросы из данных комнаты
                questions = room_data.get("questions", [])
                questions_dict = {}
                for i, question in enumerate(questions):
                    questions_dict[f"question_{i}"] = {
                        "id": f"q_{i}",
                        "text": question
                    }
                
                # Создаем систему интервью
                interview_system = TechnicalInterviewSystem(questions_dict)
                room_data["interview_system"] = interview_system
                
                # Обновляем данные в RoomManager
                self.room_manager.active_rooms[room_code] = room_data
            
            # Проверяем, не запущено ли уже интервью
            if not room_data.get("interview_started", False):
                room_data["interview_started"] = True
                # Запускаем интервью в отдельной задаче
                asyncio.create_task(self.run_interview(room_code, room_data, websocket))
            else:
                print("⚠️ Интервью уже запущено для этой комнаты")
            
            if websocket.client_state.name == "CONNECTED":
                await websocket.send_text(json.dumps({
                    "type": "interview_started",
                    "message": "Интервью началось"
                }))
            
        except Exception as e:
            print(f"❌ Ошибка запуска интервью: {e}")
            if websocket.client_state.name == "CONNECTED":
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": f"Ошибка запуска интервью: {str(e)}"
                }))
    
    async def run_interview(self, room_code: str, room_data: Dict[str, Any], websocket: WebSocket):
        """Запустить интервью."""
        try:
            interview_system = room_data.get("interview_system")
            if not interview_system:
                raise Exception("Система интервью не инициализирована")
            
            # Запускаем интервью с передачей WebSocket
            await interview_system.run_interview(websocket)
            
            # НЕ отправляем interview_completed сразу - интервью продолжается
            
        except Exception as e:
            print(f"❌ Ошибка выполнения интервью: {e}")
            # Проверяем, что соединение еще открыто
            if websocket.client_state.name == "CONNECTED":
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": f"Ошибка интервью: {str(e)}"
                }))
    
    async def handle_audio_data(self, room_code: str, room_data: Dict[str, Any], websocket: WebSocket, audio_data: str):
        """Обработать аудио данные от пользователя."""
        try:
            import base64
            import tempfile
            import os
            import asyncio
            
            # Декодируем base64 аудио данные
            audio_bytes = base64.b64decode(audio_data)
            
            # Сохраняем во временный файл
            with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as temp_file:
                temp_file.write(audio_bytes)
                temp_audio_path = temp_file.name
                print(f"📁 Создан временный файл: {temp_audio_path}")
            
            try:
                # Отправляем подтверждение получения
                if websocket.client_state.name == "CONNECTED":
                    await websocket.send_text(json.dumps({
                        "type": "audio_received",
                        "message": "Аудио получено и обрабатывается..."
                    }))
                
                # Получаем систему интервью
                interview_system = room_data.get("interview_system")
                if not interview_system:
                    raise Exception("Система интервью не инициализирована")
                
                # Интервью уже запущено при нажатии кнопки, просто обрабатываем аудио
                
                # Создаем объект-обертку для совместимости
                class RoomWrapper:
                    def __init__(self, room_data, interview_system):
                        self.room_data = room_data
                        self.interview_system = interview_system
                        # Добавляем недостающие атрибуты для совместимости
                        self.room_id = room_data.get("room_id", "unknown")
                        self.participants = []
                
                room_wrapper = RoomWrapper(room_data, interview_system)
                
                # Обрабатываем аудио через систему интервью
                await interview_system.process_audio_response(
                    room_wrapper, websocket, temp_audio_path
                )
                
            finally:
                # Удаляем временный файл
                if os.path.exists(temp_audio_path):
                    os.unlink(temp_audio_path)
                    print(f"🗑️ Временный файл удален: {temp_audio_path}")
                else:
                    print(f"⚠️ Файл уже не существует: {temp_audio_path}")
                    
        except Exception as e:
            print(f"Ошибка обработки аудио: {e}")
            if websocket.client_state.name == "CONNECTED":
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": f"Ошибка обработки аудио: {str(e)}"
                }))
    
    async def ask_next_question(self, room_code: str, room_data: Dict[str, Any], websocket: WebSocket):
        """Задать следующий вопрос."""
        try:
            interview_system = room_data.get("interview_system")
            if not interview_system:
                raise Exception("Система интервью не инициализирована")
            
            # Создаем объект-обертку для совместимости
            class RoomWrapper:
                def __init__(self, room_data, interview_system):
                    self.room_data = room_data
                    self.interview_system = interview_system
                    # Добавляем недостающие атрибуты для совместимости
                    self.room_id = room_data.get("room_id", "unknown")
                    self.participants = []
            
            room_wrapper = RoomWrapper(room_data, interview_system)
            
            # Продолжаем интервью
            await interview_system._continue_interview(room_wrapper, websocket)
            
        except Exception as e:
            print(f"❌ Ошибка запроса следующего вопроса: {e}")
            if websocket.client_state.name == "CONNECTED":
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": f"Ошибка запроса следующего вопроса: {str(e)}"
                }))
    
    async def end_interview(self, room_code: str, room_data: Dict[str, Any], websocket: WebSocket):
        """Завершить интервью."""
        room_data["status"] = "ended"
        if websocket.client_state.name == "CONNECTED":
            await websocket.send_text(json.dumps({
                "type": "interview_ended",
                "message": "Интервью завершено"
            }))
    
    def get_room_html(self, room_code: str, room_data: Dict[str, Any] = None) -> str:
        """Получить HTML страницу комнаты."""
        candidate_name = room_data.get('candidate_name', 'Кандидат') if room_data else 'Кандидат'
        vacancy_title = room_data.get('vacancy_title', 'Позиция') if room_data else 'Позиция'
        return f"""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Интервью - {room_code}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
        }}
        .candidate-info {{
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            margin: 15px 0;
            border-left: 4px solid #2196f3;
        }}
        .candidate-info h2, .candidate-info h3 {{
            margin: 5px 0;
            color: #333;
        }}
        .candidate-info h2 {{
            color: #1976d2;
        }}
        .room-code {{
            background: #e3f2fd;
            padding: 10px;
            border-radius: 5px;
            font-family: monospace;
            font-size: 18px;
            margin: 10px 0;
        }}
        .status {{
            padding: 10px;
            border-radius: 5px;
            margin: 10px 0;
            text-align: center;
        }}
        .status.connected {{
            background: #e8f5e8;
            color: #2e7d32;
        }}
        .status.disconnected {{
            background: #ffebee;
            color: #c62828;
        }}
        .controls {{
            text-align: center;
            margin: 30px 0;
        }}
        button {{
            background: #2196f3;
            color: white;
            border: none;
            padding: 15px 30px;
            border-radius: 5px;
            font-size: 16px;
            cursor: pointer;
            margin: 10px;
        }}
        button:hover {{
            background: #1976d2;
        }}
        button:disabled {{
            background: #ccc;
            cursor: not-allowed;
        }}
        .interview-area {{
            margin: 20px 0;
            padding: 20px;
            border: 2px dashed #ddd;
            border-radius: 10px;
            text-align: center;
            min-height: 200px;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }}
        .question {{
            font-size: 18px;
            margin: 20px 0;
            padding: 15px;
            background: #f0f8ff;
            border-radius: 5px;
        }}
        .audio-controls {{
            margin: 20px 0;
            display: flex;
            justify-content: center;
            gap: 10px;
            flex-wrap: wrap;
        }}
        .audio-btn {{
            background: #4caf50;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 25px;
            font-size: 14px;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: all 0.3s;
        }}
        .audio-btn:hover {{
            background: #45a049;
            transform: translateY(-2px);
        }}
        .audio-btn:disabled {{
            background: #ccc;
            cursor: not-allowed;
            transform: none;
        }}
        .audio-btn.recording {{
            background: #f44336;
            animation: pulse 1.5s infinite;
        }}
        .audio-btn.recording:hover {{
            background: #d32f2f;
        }}
        @keyframes pulse {{
            0% {{ transform: scale(1); }}
            50% {{ transform: scale(1.05); }}
            100% {{ transform: scale(1); }}
        }}
        .audio-visualizer {{
            width: 100%;
            height: 60px;
            background: #f5f5f5;
            border-radius: 10px;
            margin: 15px 0;
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
            overflow: hidden;
        }}
        .wave-bar {{
            width: 4px;
            background: #2196f3;
            margin: 0 2px;
            border-radius: 2px;
            animation: wave 0.5s ease-in-out infinite alternate;
        }}
        .wave-bar:nth-child(odd) {{
            animation-delay: 0.1s;
        }}
        .wave-bar:nth-child(even) {{
            animation-delay: 0.3s;
        }}
        @keyframes wave {{
            0% {{ height: 10px; }}
            100% {{ height: 40px; }}
        }}
        .audio-player {{
            width: 100%;
            margin: 15px 0;
        }}
        .audio-player audio {{
            width: 100%;
            height: 40px;
        }}
        .recording-status {{
            font-size: 16px;
            margin: 10px 0;
            padding: 10px;
            border-radius: 5px;
            background: #fff3cd;
            border: 1px solid #ffeaa7;
            color: #856404;
        }}
        .recording-status.recording {{
            background: #f8d7da;
            border-color: #f5c6cb;
            color: #721c24;
        }}
        
        .completion-summary {{
            background: #e8f5e8;
            padding: 20px;
            border-radius: 8px;
            margin: 10px 0;
            border-left: 4px solid #4caf50;
            text-align: center;
        }}
        
        .completion-summary h2 {{
            color: #2e7d32;
            margin: 0 0 15px 0;
        }}
        
        .stats {{
            background: white;
            padding: 15px;
            border-radius: 6px;
            margin: 15px 0;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        
        .stats p {{
            margin: 8px 0;
            font-size: 16px;
        }}
        .answer {{
            font-size: 16px;
            margin: 10px 0;
            padding: 10px;
            background: #f9f9f9;
            border-radius: 5px;
        }}
        .logs {{
            background: #f5f5f5;
            padding: 15px;
            border-radius: 5px;
            font-family: monospace;
            font-size: 12px;
            max-height: 300px;
            overflow-y: auto;
            margin: 20px 0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎤 Техническое Интервью</h1>
            <div class="candidate-info">
                <h2>👤 Кандидат: {candidate_name}</h2>
                <h3>💼 Вакансия: {vacancy_title}</h3>
            </div>
            <div class="room-code">Код комнаты: {room_code}</div>
            <div id="status" class="status disconnected">Подключение...</div>
        </div>
        
        <div class="controls">
            <button id="startBtn" onclick="startInterview()" disabled>Начать Интервью</button>
            <button id="endBtn" onclick="endInterview()" disabled>Завершить</button>
        </div>
        
        <div class="interview-area" id="interviewArea">
            <p>Нажмите "Начать Интервью" для начала</p>
        </div>
        
        <div class="audio-controls" id="audioControls" style="display: none;">
            <button class="audio-btn" id="recordBtn" onclick="toggleRecording()">
                <span id="recordIcon">🎤</span>
                <span id="recordText">Начать запись</span>
            </button>
            <button class="audio-btn" id="stopBtn" onclick="stopRecording()" disabled>
                <span>⏹️</span>
                <span>Остановить</span>
            </button>
            <button class="audio-btn" id="sendBtn" onclick="sendRecording()" disabled>
                <span>📤</span>
                <span>Отправить ответ</span>
            </button>
        </div>
        
        <div class="audio-visualizer" id="audioVisualizer" style="display: none;">
            <div class="wave-bar"></div>
            <div class="wave-bar"></div>
            <div class="wave-bar"></div>
            <div class="wave-bar"></div>
            <div class="wave-bar"></div>
            <div class="wave-bar"></div>
            <div class="wave-bar"></div>
            <div class="wave-bar"></div>
            <div class="wave-bar"></div>
            <div class="wave-bar"></div>
        </div>
        
        <div class="recording-status" id="recordingStatus" style="display: none;">
            <span id="statusText">Готов к записи</span>
        </div>
        
        <div class="audio-player" id="audioPlayer" style="display: none;">
            <audio id="questionAudio" controls></audio>
        </div>
        
        <div class="logs" id="logs"></div>
    </div>

    <script>
        let ws = null;
        let isInterviewActive = false;
        let mediaRecorder = null;
        let audioChunks = [];
        let isRecording = false;
        let audioContext = null;
        let analyser = null;
        let microphone = null;
        let animationId = null;
        
        // Подключение к WebSocket
        function connectWebSocket() {{
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${{protocol}}//${{window.location.host}}/ws/{room_code}`;
            
            ws = new WebSocket(wsUrl);
            
            ws.onopen = function() {{
                updateStatus('Подключено', 'connected');
                document.getElementById('startBtn').disabled = false;
                addLog('✅ Подключено к серверу');
            }};
            
            ws.onmessage = function(event) {{
                const message = JSON.parse(event.data);
                handleMessage(message);
            }};
            
            ws.onclose = function() {{
                updateStatus('Отключено', 'disconnected');
                document.getElementById('startBtn').disabled = true;
                document.getElementById('endBtn').disabled = true;
                addLog('❌ Соединение потеряно');
            }};
            
            ws.onerror = function(error) {{
                addLog('❌ Ошибка WebSocket: ' + error);
            }};
        }}
        
        function updateStatus(text, className) {{
            const statusEl = document.getElementById('status');
            statusEl.textContent = text;
            statusEl.className = 'status ' + className;
        }}
        
        function addLog(message) {{
            const logsEl = document.getElementById('logs');
            const time = new Date().toLocaleTimeString();
            logsEl.innerHTML += `[${{time}}] ${{message}}<br>`;
            logsEl.scrollTop = logsEl.scrollHeight;
        }}
        
        // Функции для работы с аудио
        async function initAudio() {{
            try {{
                audioContext = new (window.AudioContext || window.webkitAudioContext)();
                analyser = audioContext.createAnalyser();
                analyser.fftSize = 256;
                
                addLog('🎵 Аудио система инициализирована');
                return true;
            }} catch (error) {{
                addLog('❌ Ошибка инициализации аудио: ' + error.message);
                return false;
            }}
        }}
        
        async function toggleRecording() {{
            if (isRecording) {{
                stopRecording();
            }} else {{
                await startRecording();
            }}
        }}
        
        async function startRecording() {{
            try {{
                const stream = await navigator.mediaDevices.getUserMedia({{ 
                    audio: {{ 
                        echoCancellation: true, 
                        noiseSuppression: true,
                        sampleRate: 16000
                    }} 
                }});
                
                mediaRecorder = new MediaRecorder(stream, {{
                    mimeType: 'audio/webm;codecs=opus'
                }});
                
                audioChunks = [];
                
                mediaRecorder.ondataavailable = (event) => {{
                    if (event.data.size > 0) {{
                        audioChunks.push(event.data);
                    }}
                }};
                
                mediaRecorder.onstop = () => {{
                    const audioBlob = new Blob(audioChunks, {{ type: 'audio/webm' }});
                    const audioUrl = URL.createObjectURL(audioBlob);
                    
                    // Сохраняем URL для отправки
                    window.currentAudioBlob = audioBlob;
                    
                    // Показываем кнопку отправки
                    document.getElementById('sendBtn').disabled = false;
                    document.getElementById('recordBtn').disabled = false;
                    document.getElementById('recordText').textContent = 'Записать заново';
                    
                    // Скрываем статус записи
                    document.getElementById('recordingStatus').style.display = 'none';
                    
                    addLog('✅ Запись завершена. Нажмите "Отправить ответ" для отправки');
                }};
                
                // Настройка визуализации
                microphone = audioContext.createMediaStreamSource(stream);
                microphone.connect(analyser);
                
                mediaRecorder.start();
                isRecording = true;
                
                // Обновляем UI
                document.getElementById('recordBtn').classList.add('recording');
                document.getElementById('recordBtn').disabled = true;
                document.getElementById('stopBtn').disabled = false;
                document.getElementById('sendBtn').disabled = true;
                document.getElementById('audioVisualizer').style.display = 'flex';
                document.getElementById('recordingStatus').style.display = 'block';
                document.getElementById('statusText').textContent = 'Идет запись...';
                document.getElementById('statusText').parentElement.classList.add('recording');
                
                // Запускаем анимацию визуализации
                startVisualization();
                
                addLog('🎤 Начата запись');
                
            }} catch (error) {{
                addLog('❌ Ошибка записи: ' + error.message);
            }}
        }}
        
        function stopRecording() {{
            if (mediaRecorder && isRecording) {{
                mediaRecorder.stop();
                isRecording = false;
                
                // Останавливаем визуализацию
                stopVisualization();
                
                // Обновляем UI
                document.getElementById('recordBtn').classList.remove('recording');
                document.getElementById('stopBtn').disabled = true;
                document.getElementById('audioVisualizer').style.display = 'none';
                document.getElementById('recordingStatus').style.display = 'none';
                
                addLog('⏹️ Запись остановлена');
            }}
        }}
        
        function startVisualization() {{
            const bars = document.querySelectorAll('.wave-bar');
            
            function animate() {{
                if (!isRecording) return;
                
                const dataArray = new Uint8Array(analyser.frequencyBinCount);
                analyser.getByteFrequencyData(dataArray);
                
                bars.forEach((bar, index) => {{
                    const value = dataArray[index] || 0;
                    const height = Math.max(10, (value / 255) * 50);
                    bar.style.height = height + 'px';
                }});
                
                animationId = requestAnimationFrame(animate);
            }}
            
            animate();
        }}
        
        function stopVisualization() {{
            if (animationId) {{
                cancelAnimationFrame(animationId);
                animationId = null;
            }}
            
            // Сбрасываем высоту баров
            const bars = document.querySelectorAll('.wave-bar');
            bars.forEach(bar => {{
                bar.style.height = '10px';
            }});
        }}
        
        async function sendRecording() {{
            if (!window.currentAudioBlob) {{
                addLog('❌ Нет записи для отправки');
                return;
            }}
            
            try {{
                // Конвертируем в base64 для отправки
                const arrayBuffer = await window.currentAudioBlob.arrayBuffer();
                const base64Audio = btoa(String.fromCharCode(...new Uint8Array(arrayBuffer)));
                
                if (ws && ws.readyState === WebSocket.OPEN) {{
                    ws.send(JSON.stringify({{
                        type: 'audio_data',
                        audio_data: base64Audio,
                        format: 'webm'
                    }}));
                    
                    addLog('📤 Аудио отправлено на сервер');
                    
                    // Сбрасываем состояние
                    document.getElementById('sendBtn').disabled = true;
                    document.getElementById('recordText').textContent = 'Начать запись';
                    document.getElementById('stopBtn').disabled = true;
                    window.currentAudioBlob = null;
                    
                    // Показываем статус обработки
                    document.getElementById('recordingStatus').style.display = 'block';
                    document.getElementById('statusText').textContent = 'Обработка ответа...';
                    document.getElementById('statusText').parentElement.classList.remove('recording');
                }}
            }} catch (error) {{
                addLog('❌ Ошибка отправки аудио: ' + error.message);
            }}
        }}
        
        function playQuestionAudio(audioData) {{
            try {{
                const audioBlob = new Blob([audioData], {{ type: 'audio/mp3' }});
                const audioUrl = URL.createObjectURL(audioBlob);
                const audioElement = document.getElementById('questionAudio');
                
                audioElement.src = audioUrl;
                audioElement.style.display = 'block';
                document.getElementById('audioPlayer').style.display = 'block';
                
                audioElement.play().then(() => {{
                    addLog('🔊 Воспроизведение вопроса (OpenAI TTS)');
                }}).catch(error => {{
                    addLog('❌ Ошибка воспроизведения: ' + error.message);
                }});
                
            }} catch (error) {{
                addLog('❌ Ошибка создания аудио: ' + error.message);
            }}
        }}
        
        function speakText(text, voice = 'alloy', language = 'ru') {{
            try {{
                if ('speechSynthesis' in window) {{
                    // Останавливаем предыдущее воспроизведение
                    speechSynthesis.cancel();
                    
                    const utterance = new SpeechSynthesisUtterance(text);
                    utterance.voice = getVoice(voice, language);
                    utterance.rate = 0.9;
                    utterance.pitch = 1.0;
                    utterance.volume = 1.0;
                    
                    utterance.onstart = () => {{
                        addLog('🗣️ Начало воспроизведения вопроса');
                    }};
                    
                    utterance.onend = () => {{
                        addLog('✅ Вопрос озвучен полностью');
                    }};
                    
                    utterance.onerror = (event) => {{
                        addLog('❌ Ошибка TTS: ' + event.error);
                    }};
                    
                    speechSynthesis.speak(utterance);
                }} else {{
                    addLog('❌ Браузер не поддерживает Web Speech API');
                }}
            }} catch (error) {{
                addLog('❌ Ошибка браузерного TTS: ' + error.message);
            }}
        }}
        
        function getVoice(voiceName, language) {{
            const voices = speechSynthesis.getVoices();
            
            // Ищем голос по языку и имени
            let voice = voices.find(v => v.lang.startsWith(language) && v.name.includes(voiceName));
            
            // Если не найден, ищем по языку
            if (!voice) {{
                voice = voices.find(v => v.lang.startsWith(language));
            }}
            
            // Если все еще не найден, берем первый доступный
            if (!voice && voices.length > 0) {{
                voice = voices[0];
            }}
            
            return voice;
        }}
        
        // Загружаем голоса при инициализации
        if ('speechSynthesis' in window) {{
            speechSynthesis.onvoiceschanged = () => {{
                const voices = speechSynthesis.getVoices();
                addLog(`🗣️ Доступно голосов: ${{voices.length}}`);
            }};
        }}
        
        function handleMessage(message) {{
            addLog(`📨 Получено: ${{message.type}}`);
            
            switch(message.type) {{
                case 'room_info':
                    addLog('🏠 Информация о комнате получена');
                    break;
                    
                case 'interview_started':
                    isInterviewActive = true;
                    document.getElementById('startBtn').disabled = true;
                    document.getElementById('endBtn').disabled = false;
                    document.getElementById('audioControls').style.display = 'flex';
                    document.getElementById('interviewArea').innerHTML = '<p>🎤 Интервью началось! Нажмите "Начать запись" для ответа на вопрос</p>';
                    addLog('🎉 Интервью началось');
                    break;
                    
                case 'interview_completed':
                    isInterviewActive = false;
                    document.getElementById('startBtn').disabled = false;
                    document.getElementById('endBtn').disabled = true;
                    
                    // Показываем детальную информацию о завершении
                    const totalQuestions = message.total_questions || 0;
                    
                    document.getElementById('interviewArea').innerHTML = `
                        <div class="completion-summary">
                            <h2>✅ Интервью завершено!</h2>
                            <div class="stats">
                                <p><strong>Всего вопросов:</strong> ` + totalQuestions + `</p>
                            </div>
                            <p>Спасибо за участие в интервью!</p>
                        </div>
                    `;
                    addLog(`🏁 Интервью завершено (` + totalQuestions + ` вопросов)`);
                    break;
                    
                case 'question':
                    document.getElementById('interviewArea').innerHTML = 
                        `<div class="question">📝 Вопрос: ${{message.question}}</div>`;
                    addLog(`❓ Вопрос: ${{message.question}}`);
                    
                    // Если есть аудио данные вопроса, воспроизводим их
                    if (message.audio_data) {{
                        try {{
                            const audioData = Uint8Array.from(atob(message.audio_data), c => c.charCodeAt(0));
                            playQuestionAudio(audioData);
                        }} catch (error) {{
                            addLog('❌ Ошибка декодирования аудио вопроса: ' + error.message);
                        }}
                    }}
                    break;
                    
                case 'audio_data':
                    addLog(`🔊 Получено аудио от OpenAI TTS`);
                    try {{
                        const audioData = Uint8Array.from(atob(message.audio_data), c => c.charCodeAt(0));
                        playQuestionAudio(audioData);
                    }} catch (error) {{
                        addLog('❌ Ошибка воспроизведения аудио: ' + error.message);
                    }}
                    break;
                    
                case 'tts_speak':
                    addLog(`🗣️ Получена команда TTS: ${{message.text}}`);
                    speakText(message.text, message.voice, message.language);
                    break;
                    
                case 'answer':
                    document.getElementById('interviewArea').innerHTML += 
                        `<div class="answer">💬 Ответ: ${{message.answer}}</div>`;
                    addLog(`💬 Ответ: ${{message.answer}}`);
                    break;
                    
                case 'waiting_for_answer':
                    document.getElementById('interviewArea').innerHTML = 
                        `<div class="question">📝 Вопрос: ${{message.question}}</div>
                         <p>🎤 Готов к записи ответа. Нажмите "Начать запись" и говорите, затем "Остановить" когда закончите</p>`;
                    addLog(`❓ Ожидание ответа на вопрос: ${{message.question}}`);
                    break;
                    
                case 'audio_received':
                    document.getElementById('recordingStatus').style.display = 'block';
                    document.getElementById('statusText').textContent = 'Обработка аудио...';
                    document.getElementById('statusText').parentElement.classList.remove('recording');
                    addLog('🔄 ' + message.message);
                    break;
                    
                case 'evaluation':
                    // Оценки не отображаются пользователю - это внутренняя информация системы
                    addLog(`✅ Ответ получен и обработан`);
                    break;
                    
                case 'error':
                    addLog(`❌ Ошибка: ${{message.message}}`);
                    break;
            }}
        }}
        
        function startInterview() {{
            if (ws && ws.readyState === WebSocket.OPEN) {{
                ws.send(JSON.stringify({{
                    type: 'start_interview'
                }}));
                addLog('🚀 Запрос на начало интервью отправлен');
            }}
        }}
        
        function endInterview() {{
            if (ws && ws.readyState === WebSocket.OPEN) {{
                ws.send(JSON.stringify({{
                    type: 'end_interview'
                }}));
                addLog('🛑 Запрос на завершение интервью отправлен');
            }}
        }}
        
        // Подключаемся при загрузке страницы
        window.onload = async function() {{
            await initAudio();
            connectWebSocket();
        }};
    </script>
</body>
</html>
        """


def main():
    """Запуск сервера."""
    server = InterviewServer()
    
    print("🚀 Запуск сервера интервью...")
    print("📡 API доступно по адресу: http://localhost:8000")
    print("🌐 Веб-интерфейс: http://localhost:8000/room/{room_code}")
    print("📚 API документация: http://localhost:8000/docs")
    
    uvicorn.run(
        server.app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )


if __name__ == "__main__":
    main()
