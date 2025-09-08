#!/usr/bin/env python3
"""
Эмулятор внешнего сервиса для создания комнат интервью
"""

import requests
import json
import time
from typing import Dict, Any


class InterviewClientEmulator:
    """Эмулятор клиента для создания интервью."""
    
    def __init__(self, api_base_url: str = "http://localhost:8000"):
        self.api_base_url = api_base_url
        self.session = requests.Session()
    
    def create_interview(self, questions: Dict[str, Any], config: Dict[str, Any] = None) -> Dict[str, Any]:
        """Создать новое интервью."""
        url = f"{self.api_base_url}/api/interview/create"
        
        payload = {
            "questions": questions,
            "config": config or {}
        }
        
        try:
            response = self.session.post(url, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ Ошибка создания интервью: {e}")
            return {}
    
    def get_interview_status(self, room_id: str) -> Dict[str, Any]:
        """Получить статус интервью."""
        url = f"{self.api_base_url}/api/interview/{room_id}/status"
        
        try:
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ Ошибка получения статуса: {e}")
            return {}
    
    def delete_interview(self, room_id: str) -> bool:
        """Удалить интервью."""
        url = f"{self.api_base_url}/api/interview/{room_id}"
        
        try:
            response = self.session.delete(url)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            print(f"❌ Ошибка удаления интервью: {e}")
            return False


def load_questions_from_file(file_path: str) -> Dict[str, Any]:
    """Загрузить вопросы из файла."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Ошибка загрузки вопросов: {e}")
        return {}


def main():
    """Основная функция эмулятора."""
    print("🎭 Эмулятор внешнего сервиса для создания интервью")
    print("=" * 60)
    
    # Инициализируем клиент
    client = InterviewClientEmulator()
    
    # Загружаем вопросы
    questions = load_questions_from_file("technical_questions.json")
    if not questions:
        print("❌ Не удалось загрузить вопросы")
        return
    
    print(f"📋 Загружено {len(questions)} тем для интервью")
    
    # Дополнительная конфигурация
    config = {
        "max_depth": 3,
        "min_score_threshold": 7,
        "max_questions_per_topic": 5,
        "timeout_minutes": 30
    }
    
    # Создаем интервью
    print("\n🚀 Создание интервью...")
    result = client.create_interview(questions, config)
    
    if not result:
        print("❌ Не удалось создать интервью")
        return
    
    room_id = result.get("room_id")
    connection_code = result.get("connection_code")
    
    print(f"✅ Интервью создано успешно!")
    print(f"🆔 ID комнаты: {room_id}")
    print(f"🔑 Код подключения: {connection_code}")
    print(f"📊 Статус: {result.get('status')}")
    print(f"⏰ Создано: {result.get('created_at')}")
    
    print(f"\n🌐 Для подключения пользователя:")
    print(f"   1. Откройте браузер: http://localhost:8000")
    print(f"   2. Введите ID комнаты: {room_id}")
    print(f"   3. Введите код подключения: {connection_code}")
    print(f"   4. Нажмите 'Подключиться к Интервью'")
    
    # Мониторим статус
    print(f"\n👀 Мониторинг статуса интервью...")
    print("   (Нажмите Ctrl+C для выхода)")
    
    try:
        while True:
            status = client.get_interview_status(room_id)
            if status:
                current_status = status.get("status", "unknown")
                is_active = status.get("is_active", False)
                print(f"📊 Статус: {current_status} | Активно: {is_active}")
                
                if current_status == "completed":
                    print("🏁 Интервью завершено!")
                    break
            else:
                print("❌ Не удалось получить статус")
            
            time.sleep(5)  # Проверяем каждые 5 секунд
            
    except KeyboardInterrupt:
        print(f"\n🛑 Остановка мониторинга...")
        
        # Удаляем интервью
        print(f"🗑️ Удаление интервью...")
        if client.delete_interview(room_id):
            print("✅ Интервью удалено")
        else:
            print("❌ Не удалось удалить интервью")
    
    print("👋 Эмулятор завершен")


if __name__ == "__main__":
    main()
