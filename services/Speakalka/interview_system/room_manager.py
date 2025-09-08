"""Менеджер комнат интервью для обработки сообщений из Kafka."""

import json
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime
import uuid


class RoomManager:
    """Менеджер для создания и управления комнатами интервью."""
    
    def __init__(self):
        self.active_rooms: Dict[str, Dict[str, Any]] = {}
        print("🏠 RoomManager инициализирован")

    async def handle_kafka_message(self, message_data: Dict[str, Any]):
        """Обработать сообщение из Kafka и создать комнату интервью."""
        try:
            candidate_id = message_data.get('candidateId')
            candidate_name = message_data.get('candidateName', 'Кандидат')
            vacancy_title = message_data.get('vacancyTitle', 'Позиция')
            questions = message_data.get('questionsForApplicant', [])
            
            if not candidate_id:
                print("❌ Отсутствует candidateId в сообщении")
                return
                
            print(f"🎯 Создание комнаты для кандидата: {candidate_name}")
            print(f"🆔 Candidate ID: {candidate_id}")
            print(f"💼 Вакансия: {vacancy_title}")
            print(f"❓ Количество вопросов: {len(questions)}")
            
            # Создаем комнату
            room_data = await self.create_interview_room(
                candidate_id=candidate_id,
                candidate_name=candidate_name,
                vacancy_title=vacancy_title,
                questions=questions,
                message_data=message_data
            )
            
            if room_data:
                print(f"✅ Комната создана: {candidate_id}")
                print(f"🌐 URL: http://localhost:8000/room/{candidate_id}")
            else:
                print(f"❌ Не удалось создать комнату для {candidate_id}")
                
        except Exception as e:
            print(f"❌ Ошибка обработки сообщения Kafka: {e}")

    async def create_interview_room(
        self, 
        candidate_id: str, 
        candidate_name: str,
        vacancy_title: str,
        questions: list,
        message_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Создать комнату интервью."""
        try:
            # Проверяем, не существует ли уже комната
            if candidate_id in self.active_rooms:
                print(f"⚠️ Комната {candidate_id} уже существует")
                return self.active_rooms[candidate_id]
            
            # Создаем данные комнаты
            room_data = {
                "room_id": candidate_id,
                "candidate_name": candidate_name,
                "vacancy_title": vacancy_title,
                "created_at": datetime.now().isoformat(),
                "status": "created",
                "questions": questions,
                "message_data": message_data,
                "interview_system": None,  # Будет инициализирован при первом подключении
                "websocket": None,  # Будет установлен при WebSocket подключении
            }
            
            # Сохраняем комнату
            self.active_rooms[candidate_id] = room_data
            
            print(f"📝 Комната {candidate_id} создана успешно")
            print(f"👤 Кандидат: {candidate_name}")
            print(f"💼 Вакансия: {vacancy_title}")
            print(f"❓ Вопросов: {len(questions)}")
            
            return room_data
            
        except Exception as e:
            print(f"❌ Ошибка создания комнаты {candidate_id}: {e}")
            return None

    def get_room(self, room_id: str) -> Optional[Dict[str, Any]]:
        """Получить данные комнаты по ID."""
        return self.active_rooms.get(room_id)

    def get_all_rooms(self) -> Dict[str, Dict[str, Any]]:
        """Получить все активные комнаты."""
        return self.active_rooms.copy()

    def remove_room(self, room_id: str) -> bool:
        """Удалить комнату."""
        if room_id in self.active_rooms:
            del self.active_rooms[room_id]
            print(f"🗑️ Комната {room_id} удалена")
            return True
        return False

    def update_room_status(self, room_id: str, status: str) -> bool:
        """Обновить статус комнаты."""
        if room_id in self.active_rooms:
            self.active_rooms[room_id]["status"] = status
            self.active_rooms[room_id]["updated_at"] = datetime.now().isoformat()
            print(f"📊 Статус комнаты {room_id} обновлен: {status}")
            return True
        return False

    def set_room_websocket(self, room_id: str, websocket) -> bool:
        """Установить WebSocket соединение для комнаты."""
        if room_id in self.active_rooms:
            self.active_rooms[room_id]["websocket"] = websocket
            print(f"🔌 WebSocket установлен для комнаты {room_id}")
            return True
        return False

    def set_room_interview_system(self, room_id: str, interview_system) -> bool:
        """Установить систему интервью для комнаты."""
        if room_id in self.active_rooms:
            self.active_rooms[room_id]["interview_system"] = interview_system
            print(f"🤖 Система интервью установлена для комнаты {room_id}")
            return True
        return False


# Глобальный экземпляр менеджера комнат
_room_manager: Optional[RoomManager] = None


def get_room_manager() -> RoomManager:
    """Получить глобальный экземпляр менеджера комнат."""
    global _room_manager
    if _room_manager is None:
        _room_manager = RoomManager()
    return _room_manager
