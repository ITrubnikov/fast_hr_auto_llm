-- ===============================================
-- HR System Database Schema
-- Создание таблиц для всех 4 блоков HR системы
-- ===============================================

-- Включение расширений
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ===============================================
-- 1. Таблица requests - Сессии анализа резюме
-- ===============================================
CREATE TABLE requests (
    request_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    vacancy_title VARCHAR(500) NOT NULL,
    vacancy_description TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    total_candidates INTEGER DEFAULT 0,
    status VARCHAR(50) DEFAULT 'pending',
    
    -- Метаданные
    created_by VARCHAR(100),
    hr_manager_email VARCHAR(255),
    
    -- Constraints
    CONSTRAINT requests_status_check CHECK (status IN ('pending', 'processing', 'completed', 'failed'))
);

-- ===============================================
-- 2. Таблица candidates - Информация о кандидатах
-- ===============================================
CREATE TABLE candidates (
    candidate_id VARCHAR(50) PRIMARY KEY, -- cv_a1b2c3d4e5f6
    request_id UUID NOT NULL REFERENCES requests(request_id) ON DELETE CASCADE,
    candidate_name VARCHAR(255) NOT NULL,
    email VARCHAR(255),
    preferred_contact TEXT,
    filename VARCHAR(500),
    cv_text TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Индексы и ограничения
    CONSTRAINT candidates_id_format CHECK (candidate_id ~ '^cv_[a-f0-9]{12}$')
);

-- ===============================================
-- 3. Таблица cv_analysis - Результаты блока 1 (Анализ CV)
-- ===============================================
CREATE TABLE cv_analysis (
    candidate_id VARCHAR(50) PRIMARY KEY REFERENCES candidates(candidate_id) ON DELETE CASCADE,
    score INTEGER NOT NULL CHECK (score >= 1 AND score <= 10),
    reasoning TEXT NOT NULL,
    key_strengths JSONB DEFAULT '[]',
    concerns JSONB DEFAULT '[]',
    cv_summary TEXT,
    interview_questions JSONB DEFAULT '[]',
    suitability_conclusion VARCHAR(50) CHECK (suitability_conclusion IN ('Высокая пригодность', 'Средняя пригодность', 'Низкая пригодность')),
    analyzed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Дополнительные поля из CVAnalysis
    relevant_experience TEXT,
    education TEXT,
    technical_skills JSONB DEFAULT '[]',
    languages JSONB DEFAULT '[]'
);

-- ===============================================
-- 4. Таблица interviews_scheduled - Блок 2 (Планирование встреч)
-- ===============================================
CREATE TABLE interviews_scheduled (
    candidate_id VARCHAR(50) PRIMARY KEY REFERENCES candidates(candidate_id) ON DELETE CASCADE,
    interview_date TIMESTAMP WITH TIME ZONE,
    interview_format VARCHAR(50) DEFAULT 'online' CHECK (interview_format IN ('online', 'office', 'hybrid')),
    meeting_link TEXT,
    meeting_room VARCHAR(100),
    
    -- Email уведомления
    email_sent BOOLEAN DEFAULT FALSE,
    email_sent_at TIMESTAMP WITH TIME ZONE,
    email_status VARCHAR(50) DEFAULT 'pending' CHECK (email_status IN ('pending', 'sent', 'delivered', 'failed', 'bounced')),
    email_template_used VARCHAR(100),
    
    -- Информация об интервьюере
    interviewer_name VARCHAR(255),
    interviewer_email VARCHAR(255),
    interviewer_role VARCHAR(100),
    
    -- План собеседования
    interview_agenda JSONB DEFAULT '[]',
    estimated_duration_minutes INTEGER DEFAULT 60,
    interview_type VARCHAR(50) DEFAULT 'technical' CHECK (interview_type IN ('hr', 'technical', 'final', 'cultural')),
    
    -- Метаданные
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    scheduled_by VARCHAR(100)
);

-- ===============================================
-- 5. Таблица interview_dialogs - Блок 3 (Диалоги интервью)
-- ===============================================
CREATE TABLE interview_dialogs (
    id SERIAL PRIMARY KEY,
    candidate_id VARCHAR(50) NOT NULL REFERENCES candidates(candidate_id) ON DELETE CASCADE,
    round_number INTEGER DEFAULT 1,
    dialog_type VARCHAR(50) DEFAULT 'technical' CHECK (dialog_type IN ('hr', 'technical', 'final', 'cultural')),
    
    -- Диалог и сообщения
    dialog_messages JSONB DEFAULT '[]', -- [{"role": "interviewer", "message": "...", "timestamp": "..."}, ...]
    interviewer_notes TEXT,
    candidate_responses_quality INTEGER CHECK (candidate_responses_quality >= 1 AND candidate_responses_quality <= 10),
    
    -- Время и продолжительность
    duration_minutes INTEGER,
    started_at TIMESTAMP WITH TIME ZONE,
    ended_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(50) DEFAULT 'scheduled' CHECK (status IN ('scheduled', 'in_progress', 'completed', 'cancelled', 'no_show')),
    
    -- Оценки по категориям
    technical_score INTEGER CHECK (technical_score >= 1 AND technical_score <= 10),
    communication_score INTEGER CHECK (communication_score >= 1 AND communication_score <= 10),
    culture_fit_score INTEGER CHECK (culture_fit_score >= 1 AND culture_fit_score <= 10),
    
    -- Метаданные
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    interviewer_id VARCHAR(100),
    
    -- Уникальность: один диалог на раунд на кандидата
    UNIQUE(candidate_id, round_number)
);

-- ===============================================
-- 6. Таблица final_decisions - Блок 4 (Итоговые решения)
-- ===============================================
CREATE TABLE final_decisions (
    candidate_id VARCHAR(50) PRIMARY KEY REFERENCES candidates(candidate_id) ON DELETE CASCADE,
    decision VARCHAR(50) NOT NULL CHECK (decision IN ('hired', 'rejected', 'pending', 'on_hold')),
    decision_reason TEXT,
    overall_score INTEGER CHECK (overall_score >= 1 AND overall_score <= 10),
    
    -- Предложение о работе
    salary_offer VARCHAR(100),
    position_offered VARCHAR(255),
    start_date DATE,
    work_format VARCHAR(50) CHECK (work_format IN ('remote', 'office', 'hybrid')),
    
    -- Обратная связь и анализ
    feedback_summary JSONB DEFAULT '{}',
    strengths_summary TEXT,
    weaknesses_summary TEXT,
    
    -- HR заметки и процесс
    hr_notes TEXT,
    decision_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    decided_by VARCHAR(100),
    approved_by VARCHAR(100),
    
    -- Дополнительная информация
    offer_sent_date TIMESTAMP WITH TIME ZONE,
    offer_response_date TIMESTAMP WITH TIME ZONE,
    offer_status VARCHAR(50) CHECK (offer_status IN ('pending', 'accepted', 'rejected', 'negotiating', 'expired')),
    
    -- Метаданные
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ===============================================
-- ИНДЕКСЫ для оптимизации запросов
-- ===============================================

-- Основные индексы
CREATE INDEX idx_candidates_request_id ON candidates(request_id);
CREATE INDEX idx_candidates_created_at ON candidates(created_at);
CREATE INDEX idx_candidates_name ON candidates(candidate_name);

CREATE INDEX idx_cv_analysis_score ON cv_analysis(score);
CREATE INDEX idx_cv_analysis_conclusion ON cv_analysis(suitability_conclusion);
CREATE INDEX idx_cv_analysis_analyzed_at ON cv_analysis(analyzed_at);

CREATE INDEX idx_interviews_date ON interviews_scheduled(interview_date);
CREATE INDEX idx_interviews_status ON interviews_scheduled(email_status);
CREATE INDEX idx_interviews_interviewer ON interviews_scheduled(interviewer_email);

CREATE INDEX idx_dialogs_candidate ON interview_dialogs(candidate_id);
CREATE INDEX idx_dialogs_started_at ON interview_dialogs(started_at);
CREATE INDEX idx_dialogs_status ON interview_dialogs(status);

CREATE INDEX idx_decisions_decision ON final_decisions(decision);
CREATE INDEX idx_decisions_date ON final_decisions(decision_date);
CREATE INDEX idx_decisions_overall_score ON final_decisions(overall_score);

-- Композитные индексы
CREATE INDEX idx_requests_status_created ON requests(status, created_at);
CREATE INDEX idx_dialogs_candidate_round ON interview_dialogs(candidate_id, round_number);

-- ===============================================
-- ТРИГГЕРЫ для автоматического обновления
-- ===============================================

-- Триггер для обновления updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Применение триггеров
CREATE TRIGGER update_interviews_updated_at BEFORE UPDATE ON interviews_scheduled FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_dialogs_updated_at BEFORE UPDATE ON interview_dialogs FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_decisions_updated_at BEFORE UPDATE ON final_decisions FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Триггер для подсчета кандидатов в requests
CREATE OR REPLACE FUNCTION update_candidates_count()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE requests SET total_candidates = total_candidates + 1 WHERE request_id = NEW.request_id;
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE requests SET total_candidates = total_candidates - 1 WHERE request_id = OLD.request_id;
        RETURN OLD;
    END IF;
    RETURN NULL;
END;
$$ language 'plpgsql';

CREATE TRIGGER candidates_count_trigger 
    AFTER INSERT OR DELETE ON candidates 
    FOR EACH ROW EXECUTE FUNCTION update_candidates_count();

-- ===============================================
-- КОММЕНТАРИИ к таблицам
-- ===============================================

COMMENT ON TABLE requests IS 'Сессии анализа резюме - связывает всех кандидатов одного запроса';
COMMENT ON TABLE candidates IS 'Основная информация о кандидатах';
COMMENT ON TABLE cv_analysis IS 'Результаты анализа резюме (Блок 1)';
COMMENT ON TABLE interviews_scheduled IS 'Планирование и уведомления о собеседованиях (Блок 2)';
COMMENT ON TABLE interview_dialogs IS 'Диалоги и заметки интервью (Блок 3)';
COMMENT ON TABLE final_decisions IS 'Итоговые решения по кандидатам (Блок 4)';
