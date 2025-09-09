#!/usr/bin/env python3
"""
Тестовый скрипт для проверки API
"""

import requests
import json
import time


def test_api():
    """Тестировать API сервера."""
    base_url = "http://localhost:8000"
    
    print("🧪 Тестирование Interview System API")
    print("=" * 50)
    
    # Тестовые вопросы
    questions = {
        "Java Backend": {
            "id": "java_start",
            "text": "Скажите вы разработчик, четкий ответ да/нет?"
        },
        "Spring Framework": {
            "id": "spring_start", 
            "text": "Скажите вы пунктуальный, четкий ответ да/нет?"
        }
    }
    
    try:
        # 1. Создание интервью
        print("1️⃣ Создание интервью...")
        response = requests.post(
            f"{base_url}/api/interview/create",
            json={"questions": questions}
        )
        
        if response.status_code == 200:
            data = response.json()
            room_id = data["room_id"]
            connection_code = data["connection_code"]
            
            print(f"✅ Интервью создано!")
            print(f"   ID комнаты: {room_id}")
            print(f"   Код подключения: {connection_code}")
            print(f"   Статус: {data['status']}")
            
            # 2. Проверка статуса
            print("\n2️⃣ Проверка статуса...")
            time.sleep(1)
            
            status_response = requests.get(f"{base_url}/api/interview/{room_id}/status")
            if status_response.status_code == 200:
                status_data = status_response.json()
                print(f"✅ Статус получен: {status_data['status']}")
                print(f"   Активно: {status_data['is_active']}")
            else:
                print(f"❌ Ошибка получения статуса: {status_response.status_code}")
            
            # 3. Проверка веб-интерфейса
            print("\n3️⃣ Проверка веб-интерфейса...")
            web_response = requests.get(f"{base_url}/")
            if web_response.status_code == 200:
                print("✅ Веб-интерфейс доступен")
                print(f"   Размер страницы: {len(web_response.text)} символов")
            else:
                print(f"❌ Ошибка веб-интерфейса: {web_response.status_code}")
            
            # 4. Удаление интервью
            print("\n4️⃣ Удаление интервью...")
            delete_response = requests.delete(f"{base_url}/api/interview/{room_id}")
            if delete_response.status_code == 200:
                print("✅ Интервью удалено")
            else:
                print(f"❌ Ошибка удаления: {delete_response.status_code}")
            
            print(f"\n🎉 Тест завершен успешно!")
            print(f"🌐 Веб-интерфейс: {base_url}")
            print(f"📚 API документация: {base_url}/docs")
            
        else:
            print(f"❌ Ошибка создания интервью: {response.status_code}")
            print(f"   Ответ: {response.text}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Не удалось подключиться к серверу")
        print("   Убедитесь, что сервер запущен: python3 start_server.py")
    except Exception as e:
        print(f"❌ Ошибка тестирования: {e}")


if __name__ == "__main__":
    test_api()
