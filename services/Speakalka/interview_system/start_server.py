#!/usr/bin/env python3
"""
Скрипт для запуска сервера интервью
"""

import subprocess
import sys
import os
from pathlib import Path

def main():
    """Запуск сервера."""
    # Переходим в директорию проекта
    project_dir = Path(__file__).parent
    os.chdir(project_dir)
    
    print("🚀 Запуск сервера интервью...")
    print(f"📁 Рабочая директория: {project_dir}")
    
    try:
        # Запускаем сервер
        subprocess.run([
            sys.executable, 
            "interview_server.py"
        ], check=True)
    except KeyboardInterrupt:
        print("\n🛑 Сервер остановлен")
    except Exception as e:
        print(f"❌ Ошибка запуска сервера: {e}")

if __name__ == "__main__":
    main()
