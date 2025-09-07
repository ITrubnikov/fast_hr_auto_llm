# HR System Database

PostgreSQL база данных для обмена данными между всеми 4 блоками HR системы автоматизации подбора персонала.

## 🏗️ Архитектура

Система состоит из 6 основных таблиц, связанных между собой:

```
requests (сессии анализа)
    ↓ 1:N
candidates (информация о кандидатах)
    ↓ 1:1        ↓ 1:1        ↓ 1:N        ↓ 1:1
cv_analysis  interviews   interview    final
             _scheduled   _dialogs     _decisions
```

## 📊 Схема таблиц

### **requests** - Сессии анализа резюме
- `request_id` (UUID PK) - ID сессии анализа
- `vacancy_title` - Название вакансии
- `vacancy_description` - Полное описание требований
- `total_candidates` - Количество кандидатов
- `status` - Статус обработки

### **candidates** - Основная информация о кандидатах  
- `candidate_id` (VARCHAR PK) - cv_a1b2c3d4e5f6
- `request_id` (UUID FK) - Связь с сессией
- `candidate_name` - Имя кандидата
- `email`, `preferred_contact` - Контактная информация
- `cv_text` - Полный текст резюме

### **cv_analysis** - Результаты блока 1 (Анализ CV)
- `candidate_id` (FK) - Связь с кандидатом
- `score` (1-10) - Оценка соответствия
- `reasoning` - Обоснование оценки
- `key_strengths`, `concerns` (JSONB) - Сильные/слабые стороны
- `interview_questions` (JSONB) - Персонализированные вопросы
- `suitability_conclusion` - Высокая/Средняя/Низкая пригодность

### **interviews_scheduled** - Блок 2 (Планирование встреч)
- `candidate_id` (FK) - Связь с кандидатом  
- `interview_date` - Дата и время собеседования
- `interview_format` - online/office/hybrid
- `meeting_link` - Ссылка на видеоконференцию
- `email_sent`, `email_status` - Статус отправки уведомлений
- `interviewer_name`, `interviewer_email` - Интервьюер

### **interview_dialogs** - Блок 3 (Диалоги интервью)
- `id` (SERIAL PK) - Уникальный ID диалога
- `candidate_id` (FK) - Связь с кандидатом
- `round_number` - Раунд интервью (1, 2, 3...)
- `dialog_messages` (JSONB) - Массив сообщений чата
- `technical_score`, `communication_score`, `culture_fit_score` - Оценки
- `interviewer_notes` - Заметки интервьюера

### **final_decisions** - Блок 4 (Итоговые решения)
- `candidate_id` (FK) - Связь с кандидатом
- `decision` - hired/rejected/pending/on_hold
- `decision_reason` - Обоснование решения
- `overall_score` - Итоговая оценка
- `salary_offer`, `position_offered` - Детали предложения
- `feedback_summary` (JSONB) - Сводка по всем этапам

## 🚀 Быстрый старт

### 1. Запуск PostgreSQL в Docker

```bash
# Из корня проекта
docker-compose up postgres_hr -d

# Проверка запуска
docker logs hr_postgres
```

### 2. Проверка подключения

```bash
# Подключение к БД
docker exec -it hr_postgres psql -U hr_user -d hr_system

# Проверка таблиц
\dt

# Проверка тестовых данных
SELECT candidate_name, score, suitability_conclusion FROM candidates_full_info;
```

### 3. Переменные окружения

Добавьте в ваш `.env` файл:

```env
# PostgreSQL настройки
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=hr_system
POSTGRES_USER=hr_user
POSTGRES_PASSWORD=hr_secure_password_2024

# URL для приложений
DATABASE_URL=postgresql://hr_user:hr_secure_password_2024@localhost:5432/hr_system
```

## 🔧 Интеграция с блоками

### Блок 1: CV-UI интеграция

```python
# Добавьте в services/cv-ui/requirements.txt
asyncpg==0.29.0

# Пример сохранения в БД
from database.integration_examples import Block1_CVAnalysisDB

async def save_results_to_db(results, job_description, vacancy_title):
    db_client = Block1_CVAnalysisDB()
    await db_client.save_cv_analysis_results(
        request_id, vacancy_title, job_description, candidates_data
    )
```

### Блок 2: Планирование интервью  

```python
from database.integration_examples import Block2_InterviewSchedulingDB

# Получение кандидатов для планирования
db_client = Block2_InterviewSchedulingDB()
candidates = await db_client.get_candidates_for_scheduling(min_score=6)

# Планирование интервью
await db_client.schedule_interview(
    candidate_id, interview_date, 
    interviewer_name, interviewer_email
)
```

### Блок 3: Диалоги интервью

```python
from database.integration_examples import Block3_InterviewDialogsDB

# Сохранение диалога
db_client = Block3_InterviewDialogsDB()
await db_client.save_interview_dialog(
    candidate_id, dialog_messages,
    technical_score=8, communication_score=7
)
```

### Блок 4: Итоговые решения

```python
from database.integration_examples import Block4_FinalDecisionsDB

# Принятие решения
db_client = Block4_FinalDecisionsDB()
await db_client.make_final_decision(
    candidate_id, 'hired', 'Отличные результаты',
    overall_score=9, salary_offer='320000 RUB'
)
```

## 📈 Готовые представления и функции

### Представления (Views)
- `candidates_full_info` - Полная информация о кандидатах со всех этапов
- `requests_statistics` - Статистика по запросам анализа
- `candidates_ready_to_hire` - Кандидаты с положительным решением

### Функции интеграции
- `insert_cv_analysis_data()` - Вставка из блока 1
- `get_candidates_for_interview_scheduling()` - Получение для блока 2  
- `schedule_interview()` - Планирование интервью
- `save_interview_dialog()` - Сохранение диалогов блока 3
- `make_final_decision()` - Финальные решения блока 4

### Аналитические функции
- `get_hr_analytics()` - Статистика HR процессов
- Автоматические триггеры обновления счетчиков

## 📊 Примеры запросов

### Кандидаты с высокими оценками
```sql
SELECT candidate_name, score, suitability_conclusion, decision
FROM candidates_full_info 
WHERE cv_score >= 8 
ORDER BY cv_score DESC;
```

### Статистика по вакансиям
```sql
SELECT vacancy_title, total_candidates, hired, rejected,
       ROUND(hired::NUMERIC / total_candidates * 100, 1) as hire_rate
FROM requests_statistics
WHERE created_at >= CURRENT_DATE - INTERVAL '30 days';
```

### Эффективность интервьюеров
```sql
SELECT interviewer_name, 
       COUNT(*) as interviews_conducted,
       AVG(technical_score) as avg_technical_score
FROM interviews_scheduled i
JOIN interview_dialogs d ON i.candidate_id = d.candidate_id
WHERE d.status = 'completed'
GROUP BY interviewer_name;
```

## 🔒 Безопасность

- Все подключения через SSL (в продакшене)
- Ограниченные права доступа для пользователя `hr_user`
- Регулярные бэкапы (настроены в docker-compose)
- Валидация данных через CHECK constraints
- Защита от SQL-инъекций через параметризованные запросы

## 🚚 Бэкапы и миграции

### Создание бэкапа
```bash
docker exec hr_postgres pg_dump -U hr_user hr_system > backup_$(date +%Y%m%d).sql
```

### Восстановление из бэкапа
```bash  
docker exec -i hr_postgres psql -U hr_user hr_system < backup_file.sql
```

### Миграции
Новые миграции добавляйте в `database/init/` с префиксом номера (04_, 05_, ...)

## 📞 Поддержка

При возникновении проблем:

1. Проверьте логи: `docker logs hr_postgres`
2. Проверьте подключение: `docker exec hr_postgres pg_isready`
3. Проверьте переменные окружения в `.env`
4. Убедитесь что БД инициализирована: `\dt` в psql

## 🎯 Roadmap

- [ ] Индексы для улучшения производительности
- [ ] Партиционирование больших таблиц
- [ ] Мониторинг и алерты  
- [ ] Репликация для высокой доступности
- [ ] GraphQL API для frontend
