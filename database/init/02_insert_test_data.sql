-- ===============================================
-- Тестовые данные для HR System Database
-- ===============================================

-- ===============================================
-- 1. Вставка тестовой сессии анализа
-- ===============================================
INSERT INTO requests (request_id, vacancy_title, vacancy_description, total_candidates, status, created_by, hr_manager_email) 
VALUES 
('12345678-1234-5678-9abc-123456789def', 
 'Senior Python Developer', 
 'Требуется Senior Python Developer для разработки торговых систем.
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
- Офис в центре Москвы', 
 0, 'processing', 'hr_manager', 'hr@company.com');

-- ===============================================
-- 2. Вставка тестовых кандидатов
-- ===============================================
INSERT INTO candidates (candidate_id, request_id, candidate_name, email, preferred_contact, filename, cv_text) 
VALUES 
-- Сильный кандидат
('cv_a8f9e2b1c4d7', '12345678-1234-5678-9abc-123456789def', 'Иван Петров', 'ivan.petrov@yandex.ru', '📧 ivan.petrov@yandex.ru', 'ivan_petrov_cv.pdf',
'Иван Петров
Senior Python Developer
Телефон: +7-999-123-45-67
Email: ivan.petrov@yandex.ru

Опыт работы:
2019-2024: Senior Python Developer в Сбербанк
- Разработка торговых систем на Django
- Работа с PostgreSQL, Redis
- Опыт с Docker и Kubernetes
- Команда из 8 разработчиков

2017-2019: Python Developer в Тинькофф
- Backend разработка на FastAPI
- Микросервисная архитектура
- Высоконагруженные системы

Образование:
2017: МГУ, Факультет ВМК, Программная инженерия

Технические навыки:
Python, Django, FastAPI, PostgreSQL, Redis, Docker, Kubernetes, Git, Linux'),

-- Средний кандидат
('cv_b2e7f8a3c9d1', '12345678-1234-5678-9abc-123456789def', 'Анна Сидорова', '', '💬 Telegram: @anna_dev', 'anna_sidorova_cv.pdf',
'Анна Сидорова
Python Developer
Телефон: 8-495-123-45-67
Telegram: @anna_dev

Опыт работы:
2020-2024: Python Developer в Яндекс
- Разработка веб-приложений на Django
- Работа с PostgreSQL
- Участие в проектах с нагрузкой 1M+ пользователей

2018-2020: Junior Python Developer в StartUp XYZ
- Backend разработка
- Работа с API
- Изучение лучших практик

Образование:
2018: МФТИ, Прикладная математика и информатика

Навыки:
Python, Django, PostgreSQL, Git, Linux, HTML, CSS, JavaScript'),

-- Слабый кандидат
('cv_c5d8e1f2a6b9', '12345678-1234-5678-9abc-123456789def', 'Михаил Козлов', '', '💼 LinkedIn: linkedin.com/in/mikhail-kozlov', 'mikhail_kozlov_cv.pdf',
'Михаил Козлов
Fullstack Developer
Контакты: linkedin.com/in/mikhail-kozlov

Опыт работы:
2022-2024: Frontend Developer в Ozon
- Разработка на React, JavaScript
- Работа с REST API
- Участие в кросс-функциональной команде

2020-2022: Junior Developer в веб-студии
- Верстка сайтов
- Изучение программирования
- Работа с клиентами

Образование:
2020: Курсы программирования GeekBrains

Навыки:
JavaScript, React, HTML, CSS, Python (базовый), Git');

-- ===============================================
-- 3. Результаты анализа CV (Блок 1)
-- ===============================================
INSERT INTO cv_analysis (
    candidate_id, score, reasoning, key_strengths, concerns, cv_summary, 
    interview_questions, suitability_conclusion, relevant_experience, education, technical_skills, languages
) VALUES 
-- Иван Петров - сильный кандидат
('cv_a8f9e2b1c4d7', 9, 
'Исключительно сильный кандидат с 7-летним опытом работы в Python. Имеет опыт в финтех (Сбербанк, Тинькофф), знает все требуемые технологии включая Django, FastAPI, PostgreSQL, Redis, Docker и Kubernetes. Опыт работы с высоконагруженными системами и лидерские качества.',
'["5+ лет опыта с Python", "Опыт в финтех (Сбербанк, Тинькофф)", "Знание всех требуемых технологий", "Опыт с микросервисами", "Лидерский опыт (команда 8 человек)", "Высшее техническое образование МГУ"]',
'["Может быть переквалифицирован для текущих задач"]',
'Senior Python разработчик с 7-летним опытом в финтех. Специализируется на торговых системах, имеет опыт с микросервисной архитектурой и управлением командой.',
'["Расскажите подробнее о торговых системах, которые вы разрабатывали в Сбербанке", "Как вы организовывали работу команды из 8 разработчиков?", "Какие вызовы возникали при работе с высоконагруженными системами в Тинькофф?", "Опишите ваш опыт с микросервисной архитектурой", "Как вы решали проблемы производительности в работе с базами данных?", "Что вас привлекает в нашей вакансии и почему вы хотите сменить работу?"]',
'Высокая пригодность',
'7 лет опыта Python разработки в финтех компаниях',
'МГУ, Факультет ВМК, Программная инженерия (2017)',
'["Python", "Django", "FastAPI", "PostgreSQL", "Redis", "Docker", "Kubernetes", "Git", "Linux"]',
'["Python", "SQL"]'),

-- Анна Сидорова - средний кандидат
('cv_b2e7f8a3c9d1', 6,
'Кандидат имеет 4 года опыта с Python, что меньше требуемых 5+. Знание Django есть, но отсутствует опыт с FastAPI и Redis. Нет опыта в финтех, но есть опыт работы с высоконагруженными системами в Яндексе. Хорошее техническое образование МФТИ.',
'["Опыт с Django", "Работа с PostgreSQL", "Опыт с высоконагруженными системами", "Хорошее образование МФТИ", "4 года коммерческого опыта"]',
'["Опыт менее 5+ лет", "Нет опыта с FastAPI", "Отсутствует опыт с Redis", "Нет опыта в финтех", "Нет опыта с Docker/Kubernetes"]',
'Python разработчик с 4-летним опытом в крупных IT компаниях. Специализируется на веб-приложениях Django с опытом высоких нагрузок.',
'["У вас 4 года опыта, но требуется 5+. Как вы планируете компенсировать этот пробел?", "Расскажите о проектах в Яндексе с высокой нагрузкой", "Какой у вас опыт работы с Redis? Почему его нет в резюме?", "Знакомы ли вы с FastAPI? Готовы ли изучить?", "Есть ли у вас опыт работы в финансовой сфере?", "Почему вас интересует переход в финтех?"]',
'Средняя пригодность',
'4 года Python разработки в IT компаниях',
'МФТИ, Прикладная математика и информатика (2018)',
'["Python", "Django", "PostgreSQL", "Git", "Linux", "HTML", "CSS", "JavaScript"]',
'["Python", "JavaScript"]'),

-- Михаил Козлов - слабый кандидат
('cv_c5d8e1f2a6b9', 2,
'Кандидат не подходит для позиции Senior Python Developer. Основной опыт во Frontend разработке (React, JavaScript). Python указан как "базовый" без коммерческого опыта. Нет опыта с Django/FastAPI, базами данных, отсутствует высшее техническое образование.',
'["Знание JavaScript и React", "Опыт работы в крупной компании (Ozon)", "Базовые знания Python"]',
'["Нет коммерческого опыта с Python", "Отсутствует опыт с Django/FastAPI", "Нет опыта работы с БД", "Frontend-специализация", "Отсутствует профильное высшее образование", "Не подходит уровень Senior"]',
'Frontend разработчик с опытом React/JavaScript, базовые знания Python без коммерческого применения.',
'["У вас нет опыта с Python в коммерческих проектах. Почему вы откликнулись на эту вакансию?", "Готовы ли вы кардинально сменить технологический стек с Frontend на Backend?", "Какой у вас реальный уровень знания Python?", "Есть ли опыт работы с базами данных?", "Сколько времени вам потребуется для изучения Django/FastAPI?", "Рассматриваете ли вы Junior/Middle позиции по Python?"]',
'Низкая пригодность',
'Frontend разработка, Python без коммерческого опыта',
'Курсы программирования GeekBrains (2020)',
'["JavaScript", "React", "HTML", "CSS", "Git", "Python"]',
'["JavaScript", "Python"]);

-- ===============================================
-- 4. Планирование интервью (Блок 2) 
-- ===============================================
INSERT INTO interviews_scheduled (
    candidate_id, interview_date, interview_format, meeting_link, 
    email_sent, email_sent_at, email_status, interviewer_name, interviewer_email, 
    interview_agenda, interview_type, scheduled_by
) VALUES 
-- Для Ивана Петрова (сильный кандидат)
('cv_a8f9e2b1c4d7', '2024-12-20 14:00:00+03', 'online', 'https://zoom.us/j/123456789',
TRUE, '2024-12-19 10:00:00+03', 'delivered', 'Анна Иванова', 'anna.ivanova@company.com',
'[{"topic": "Обзор опыта", "duration": 10}, {"topic": "Технические вопросы по Django", "duration": 20}, {"topic": "Архитектура микросервисов", "duration": 20}, {"topic": "Вопросы кандидата", "duration": 10}]',
'technical', 'hr_manager'),

-- Для Анны Сидоровой (средний кандидат) 
('cv_b2e7f8a3c9d1', '2024-12-21 15:30:00+03', 'online', 'https://meet.google.com/abc-defg-hij',
TRUE, '2024-12-19 11:00:00+03', 'sent', 'Сергей Петров', 'sergey.petrov@company.com',
'[{"topic": "Опыт работы в Яндекс", "duration": 15}, {"topic": "Пробелы в технологиях", "duration": 20}, {"topic": "Готовность к изучению", "duration": 15}, {"topic": "Мотивация", "duration": 10}]',
'hr', 'hr_manager');

-- Михаил Козлов - интервью не планируется из-за низкой оценки

-- ===============================================
-- 5. Диалоги интервью (Блок 3) - Пример для Ивана
-- ===============================================
INSERT INTO interview_dialogs (
    candidate_id, round_number, dialog_type, dialog_messages, interviewer_notes,
    candidate_responses_quality, technical_score, communication_score, culture_fit_score,
    duration_minutes, started_at, ended_at, status, interviewer_id
) VALUES 
('cv_a8f9e2b1c4d7', 1, 'technical',
'[
  {"role": "interviewer", "message": "Расскажите о торговых системах, которые вы разрабатывали", "timestamp": "2024-12-20T14:05:00Z"},
  {"role": "candidate", "message": "В Сбербанке я работал над системой обработки заявок на кредиты. Система обрабатывала до 50К заявок в день...", "timestamp": "2024-12-20T14:06:00Z"},
  {"role": "interviewer", "message": "Как вы решали проблемы производительности?", "timestamp": "2024-12-20T14:10:00Z"},
  {"role": "candidate", "message": "Использовали Redis для кэширования, оптимизировали SQL запросы, внедрили асинхронную обработку через Celery...", "timestamp": "2024-12-20T14:12:00Z"}
]',
'Отличные технические знания. Четко объясняет архитектурные решения. Хорошо знает Django ORM и оптимизацию запросов.',
9, 8, 9, 8, 45,
'2024-12-20 14:00:00+03', '2024-12-20 14:45:00+03', 'completed', 'anna.ivanova');

-- ===============================================
-- 6. Итоговые решения (Блок 4)
-- ===============================================
INSERT INTO final_decisions (
    candidate_id, decision, decision_reason, overall_score, salary_offer, 
    position_offered, start_date, work_format, feedback_summary, 
    strengths_summary, hr_notes, decided_by
) VALUES 
-- Иван Петров - нанят!
('cv_a8f9e2b1c4d7', 'hired', 
'Исключительно сильный кандидат с идеальным соответствием требованиям. Показал отличные технические знания, имеет релевантный опыт в финтех.',
9, '320000 RUB', 'Senior Python Developer', '2025-01-15', 'hybrid',
'{"cv_score": 9, "interview_score": 8, "technical_skills": "excellent", "culture_fit": "high"}',
'Глубокие знания Python и Django, опыт в финтех, лидерские качества',
'Рекомендую к найму без колебаний. Может стать тимлидом в будущем.',
'anna.ivanova'),

-- Анна Сидорова - на рассмотрении
('cv_b2e7f8a3c9d1', 'pending', 
'Кандидат показал хорошие базовые знания, но есть пробелы в требуемых технологиях. Готовность к изучению высокая.',
6, '250000 RUB', 'Middle Python Developer', NULL, 'remote',
'{"cv_score": 6, "interview_score": 7, "learning_attitude": "positive"}',
'Хороший потенциал, быстро обучается',
'Рассмотреть для позиции Middle после прохождения технического задания.',
'sergey.petrov'),

-- Михаил Козлов - отклонен
('cv_c5d8e1f2a6b9', 'rejected',
'Не соответствует требованиям позиции. Нет коммерческого опыта с Python.',
2, NULL, NULL, NULL, NULL,
'{"cv_score": 2, "rejection_reason": "insufficient_python_experience"}',
'Опыт frontend разработки',
'Не подходит для Python позиций. Рекомендовать вакансии Frontend.',
'hr_manager');

-- ===============================================
-- Обновление статуса запроса
-- ===============================================
UPDATE requests 
SET status = 'completed', total_candidates = 3 
WHERE request_id = '12345678-1234-5678-9abc-123456789def';
