-- ===============================================
-- HR System Database - Views & Functions
-- Полезные представления и функции для работы с данными
-- ===============================================

-- ===============================================
-- ПРЕДСТАВЛЕНИЯ (Views)
-- ===============================================

-- Полная информация о кандидатах со всеми этапами
CREATE OR REPLACE VIEW candidates_full_info AS
SELECT 
    c.candidate_id,
    c.candidate_name,
    c.email,
    c.preferred_contact,
    c.filename,
    c.created_at as candidate_created_at,
    
    -- Информация о запросе
    r.request_id,
    r.vacancy_title,
    r.created_at as request_created_at,
    
    -- Анализ CV (Блок 1)
    cv.score as cv_score,
    cv.suitability_conclusion,
    cv.reasoning,
    cv.key_strengths,
    cv.concerns,
    cv.interview_questions,
    
    -- Планирование интервью (Блок 2)
    i.interview_date,
    i.interview_format,
    i.email_sent,
    i.interviewer_name,
    i.interviewer_email,
    
    -- Последний диалог интервью (Блок 3)
    d.dialog_type as last_interview_type,
    d.status as interview_status,
    d.technical_score,
    d.communication_score,
    d.culture_fit_score,
    d.started_at as last_interview_date,
    
    -- Итоговое решение (Блок 4)
    fd.decision,
    fd.decision_reason,
    fd.overall_score,
    fd.salary_offer,
    fd.position_offered,
    fd.start_date,
    fd.decision_date

FROM candidates c
LEFT JOIN requests r ON c.request_id = r.request_id
LEFT JOIN cv_analysis cv ON c.candidate_id = cv.candidate_id
LEFT JOIN interviews_scheduled i ON c.candidate_id = i.candidate_id
LEFT JOIN final_decisions fd ON c.candidate_id = fd.candidate_id
LEFT JOIN LATERAL (
    SELECT * FROM interview_dialogs 
    WHERE candidate_id = c.candidate_id 
    ORDER BY round_number DESC 
    LIMIT 1
) d ON true;

-- Статистика по запросам
CREATE OR REPLACE VIEW requests_statistics AS
SELECT 
    r.request_id,
    r.vacancy_title,
    r.created_at,
    r.total_candidates,
    
    -- Статистика по оценкам CV
    COUNT(cv.candidate_id) as analyzed_candidates,
    AVG(cv.score) as avg_cv_score,
    COUNT(CASE WHEN cv.suitability_conclusion = 'Высокая пригодность' THEN 1 END) as high_suitability,
    COUNT(CASE WHEN cv.suitability_conclusion = 'Средняя пригодность' THEN 1 END) as medium_suitability,
    COUNT(CASE WHEN cv.suitability_conclusion = 'Низкая пригодность' THEN 1 END) as low_suitability,
    
    -- Статистика по интервью
    COUNT(i.candidate_id) as interviews_scheduled,
    COUNT(CASE WHEN i.email_sent = true THEN 1 END) as emails_sent,
    
    -- Статистика по решениям
    COUNT(CASE WHEN fd.decision = 'hired' THEN 1 END) as hired,
    COUNT(CASE WHEN fd.decision = 'rejected' THEN 1 END) as rejected,
    COUNT(CASE WHEN fd.decision = 'pending' THEN 1 END) as pending

FROM requests r
LEFT JOIN candidates c ON r.request_id = c.request_id
LEFT JOIN cv_analysis cv ON c.candidate_id = cv.candidate_id
LEFT JOIN interviews_scheduled i ON c.candidate_id = i.candidate_id
LEFT JOIN final_decisions fd ON c.candidate_id = fd.candidate_id
GROUP BY r.request_id, r.vacancy_title, r.created_at, r.total_candidates;

-- Кандидаты готовые к найму
CREATE OR REPLACE VIEW candidates_ready_to_hire AS
SELECT 
    c.candidate_id,
    c.candidate_name,
    c.email,
    c.preferred_contact,
    cv.score as cv_score,
    cv.suitability_conclusion,
    fd.overall_score,
    fd.salary_offer,
    fd.position_offered,
    fd.start_date,
    r.vacancy_title
FROM candidates c
JOIN cv_analysis cv ON c.candidate_id = cv.candidate_id
JOIN final_decisions fd ON c.candidate_id = fd.candidate_id
JOIN requests r ON c.request_id = r.request_id
WHERE fd.decision = 'hired'
ORDER BY fd.decision_date DESC;

-- ===============================================
-- ФУНКЦИИ для интеграции с блоками
-- ===============================================

-- Функция для вставки данных из Блока 1 (CV анализ)
CREATE OR REPLACE FUNCTION insert_cv_analysis_data(
    p_request_id UUID,
    p_vacancy_title VARCHAR(500),
    p_vacancy_description TEXT,
    p_candidates_data JSONB  -- Массив кандидатов из cv-ui
) RETURNS UUID AS $$
DECLARE
    candidate_record JSONB;
    new_request_id UUID;
BEGIN
    -- Создаем новый запрос если не существует
    INSERT INTO requests (request_id, vacancy_title, vacancy_description, status)
    VALUES (p_request_id, p_vacancy_title, p_vacancy_description, 'processing')
    ON CONFLICT (request_id) DO UPDATE SET
        vacancy_title = EXCLUDED.vacancy_title,
        vacancy_description = EXCLUDED.vacancy_description
    RETURNING request_id INTO new_request_id;
    
    -- Проходим по всем кандидатам
    FOR candidate_record IN SELECT * FROM jsonb_array_elements(p_candidates_data)
    LOOP
        -- Вставляем кандидата
        INSERT INTO candidates (
            candidate_id, request_id, candidate_name, email, 
            preferred_contact, cv_text
        ) VALUES (
            candidate_record->>'candidateId',
            p_request_id,
            candidate_record->>'candidateName',
            candidate_record->>'email',
            candidate_record->>'preferredContact',
            candidate_record->>'cvText'
        ) ON CONFLICT (candidate_id) DO UPDATE SET
            candidate_name = EXCLUDED.candidate_name,
            email = EXCLUDED.email,
            preferred_contact = EXCLUDED.preferred_contact,
            cv_text = EXCLUDED.cv_text;
        
        -- Вставляем анализ CV
        INSERT INTO cv_analysis (
            candidate_id, score, reasoning, suitability_conclusion, interview_questions
        ) VALUES (
            candidate_record->>'candidateId',
            (candidate_record->>'score')::INTEGER,
            candidate_record->>'reasoning',
            candidate_record->>'suitabilityConclusion',
            candidate_record->'questionsForApplicant'
        ) ON CONFLICT (candidate_id) DO UPDATE SET
            score = EXCLUDED.score,
            reasoning = EXCLUDED.reasoning,
            suitability_conclusion = EXCLUDED.suitability_conclusion,
            interview_questions = EXCLUDED.interview_questions;
    END LOOP;
    
    RETURN new_request_id;
END;
$$ LANGUAGE plpgsql;

-- Функция для получения кандидатов для Блока 2 (планирование интервью)
CREATE OR REPLACE FUNCTION get_candidates_for_interview_scheduling(
    p_request_id UUID DEFAULT NULL,
    p_min_score INTEGER DEFAULT 6
) RETURNS TABLE (
    candidate_id VARCHAR(50),
    candidate_name VARCHAR(255),
    email VARCHAR(255),
    preferred_contact TEXT,
    score INTEGER,
    suitability_conclusion VARCHAR(50),
    interview_questions JSONB,
    vacancy_title VARCHAR(500)
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        c.candidate_id,
        c.candidate_name,
        c.email,
        c.preferred_contact,
        cv.score,
        cv.suitability_conclusion,
        cv.interview_questions,
        r.vacancy_title
    FROM candidates c
    JOIN cv_analysis cv ON c.candidate_id = cv.candidate_id
    JOIN requests r ON c.request_id = r.request_id
    LEFT JOIN interviews_scheduled i ON c.candidate_id = i.candidate_id
    WHERE 
        (p_request_id IS NULL OR c.request_id = p_request_id)
        AND cv.score >= p_min_score
        AND i.candidate_id IS NULL  -- Еще не запланировано интервью
    ORDER BY cv.score DESC;
END;
$$ LANGUAGE plpgsql;

-- Функция для обновления статуса интервью (Блок 2)
CREATE OR REPLACE FUNCTION schedule_interview(
    p_candidate_id VARCHAR(50),
    p_interview_date TIMESTAMP WITH TIME ZONE,
    p_interviewer_name VARCHAR(255),
    p_interviewer_email VARCHAR(255),
    p_meeting_link TEXT DEFAULT NULL
) RETURNS BOOLEAN AS $$
BEGIN
    INSERT INTO interviews_scheduled (
        candidate_id, interview_date, interviewer_name, 
        interviewer_email, meeting_link, email_sent
    ) VALUES (
        p_candidate_id, p_interview_date, p_interviewer_name,
        p_interviewer_email, p_meeting_link, FALSE
    ) ON CONFLICT (candidate_id) DO UPDATE SET
        interview_date = EXCLUDED.interview_date,
        interviewer_name = EXCLUDED.interviewer_name,
        interviewer_email = EXCLUDED.interviewer_email,
        meeting_link = EXCLUDED.meeting_link,
        updated_at = CURRENT_TIMESTAMP;
    
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- Функция для сохранения диалога интервью (Блок 3)
CREATE OR REPLACE FUNCTION save_interview_dialog(
    p_candidate_id VARCHAR(50),
    p_dialog_messages JSONB,
    p_technical_score INTEGER DEFAULT NULL,
    p_communication_score INTEGER DEFAULT NULL,
    p_culture_fit_score INTEGER DEFAULT NULL,
    p_interviewer_notes TEXT DEFAULT NULL
) RETURNS INTEGER AS $$
DECLARE
    dialog_id INTEGER;
    current_round INTEGER;
BEGIN
    -- Получаем следующий номер раунда
    SELECT COALESCE(MAX(round_number), 0) + 1 
    INTO current_round 
    FROM interview_dialogs 
    WHERE candidate_id = p_candidate_id;
    
    INSERT INTO interview_dialogs (
        candidate_id, round_number, dialog_messages, 
        technical_score, communication_score, culture_fit_score,
        interviewer_notes, status, started_at, ended_at
    ) VALUES (
        p_candidate_id, current_round, p_dialog_messages,
        p_technical_score, p_communication_score, p_culture_fit_score,
        p_interviewer_notes, 'completed', 
        CURRENT_TIMESTAMP - INTERVAL '1 hour', CURRENT_TIMESTAMP
    ) RETURNING id INTO dialog_id;
    
    RETURN dialog_id;
END;
$$ LANGUAGE plpgsql;

-- Функция для принятия финального решения (Блок 4)
CREATE OR REPLACE FUNCTION make_final_decision(
    p_candidate_id VARCHAR(50),
    p_decision VARCHAR(50),
    p_decision_reason TEXT,
    p_overall_score INTEGER DEFAULT NULL,
    p_salary_offer VARCHAR(100) DEFAULT NULL,
    p_position_offered VARCHAR(255) DEFAULT NULL,
    p_decided_by VARCHAR(100) DEFAULT NULL
) RETURNS BOOLEAN AS $$
BEGIN
    INSERT INTO final_decisions (
        candidate_id, decision, decision_reason, overall_score,
        salary_offer, position_offered, decided_by
    ) VALUES (
        p_candidate_id, p_decision, p_decision_reason, p_overall_score,
        p_salary_offer, p_position_offered, p_decided_by
    ) ON CONFLICT (candidate_id) DO UPDATE SET
        decision = EXCLUDED.decision,
        decision_reason = EXCLUDED.decision_reason,
        overall_score = EXCLUDED.overall_score,
        salary_offer = EXCLUDED.salary_offer,
        position_offered = EXCLUDED.position_offered,
        decided_by = EXCLUDED.decided_by,
        decision_date = CURRENT_TIMESTAMP,
        updated_at = CURRENT_TIMESTAMP;
    
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- ===============================================
-- ФУНКЦИИ АНАЛИТИКИ
-- ===============================================

-- Функция для получения статистики по HR процессам
CREATE OR REPLACE FUNCTION get_hr_analytics(
    p_from_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_DATE - INTERVAL '30 days',
    p_to_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
) RETURNS TABLE (
    total_requests INTEGER,
    total_candidates INTEGER,
    avg_cv_score NUMERIC,
    interviews_completed INTEGER,
    hired_count INTEGER,
    rejection_rate NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        COUNT(DISTINCT r.request_id)::INTEGER as total_requests,
        COUNT(DISTINCT c.candidate_id)::INTEGER as total_candidates,
        ROUND(AVG(cv.score), 2) as avg_cv_score,
        COUNT(DISTINCT d.candidate_id)::INTEGER as interviews_completed,
        COUNT(CASE WHEN fd.decision = 'hired' THEN 1 END)::INTEGER as hired_count,
        ROUND(
            COUNT(CASE WHEN fd.decision = 'rejected' THEN 1 END)::NUMERIC / 
            NULLIF(COUNT(DISTINCT c.candidate_id), 0) * 100, 
            2
        ) as rejection_rate
    FROM requests r
    LEFT JOIN candidates c ON r.request_id = c.request_id
    LEFT JOIN cv_analysis cv ON c.candidate_id = cv.candidate_id
    LEFT JOIN interview_dialogs d ON c.candidate_id = d.candidate_id AND d.status = 'completed'
    LEFT JOIN final_decisions fd ON c.candidate_id = fd.candidate_id
    WHERE r.created_at BETWEEN p_from_date AND p_to_date;
END;
$$ LANGUAGE plpgsql;

-- ===============================================
-- КОММЕНТАРИИ
-- ===============================================

COMMENT ON VIEW candidates_full_info IS 'Полная информация о кандидатах со всеми этапами HR процесса';
COMMENT ON VIEW requests_statistics IS 'Статистика по запросам анализа резюме';
COMMENT ON VIEW candidates_ready_to_hire IS 'Кандидаты с положительным решением о найме';

COMMENT ON FUNCTION insert_cv_analysis_data IS 'Вставка данных из Блока 1 (анализ CV)';
COMMENT ON FUNCTION get_candidates_for_interview_scheduling IS 'Получение кандидатов для планирования интервью';
COMMENT ON FUNCTION schedule_interview IS 'Планирование интервью с кандидатом';
COMMENT ON FUNCTION save_interview_dialog IS 'Сохранение диалога интервью';
COMMENT ON FUNCTION make_final_decision IS 'Принятие финального решения по кандидату';
COMMENT ON FUNCTION get_hr_analytics IS 'Получение аналитики по HR процессам';
