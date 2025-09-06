## Быстрый запуск

1) Создать `.env` из примера и заполнить ключи

```bash
cp env_example .env
# отредактируйте .env и укажите реальный OPENROUTER_API_KEY=sk-or-...
```

2) Выполнить команды запуска

```bash
docker network create ocr_network || true
docker compose up --build -d
open http://localhost:8503   # Windows: start http://localhost:8503
```

