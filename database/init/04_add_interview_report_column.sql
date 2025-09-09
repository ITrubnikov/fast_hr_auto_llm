-- ===============================================
-- Добавление колонки для полного отчета интервью
-- Блок 3 (Speakalka) генерирует детальные отчеты
-- ===============================================

-- Добавляем колонку для полного отчета интервью в interview_dialogs
ALTER TABLE interview_dialogs 
ADD COLUMN IF NOT EXISTS full_interview_report JSONB DEFAULT '{}',
ADD COLUMN IF NOT EXISTS interview_transcript TEXT,
ADD COLUMN IF NOT EXISTS emotion_analysis_summary JSONB DEFAULT '{}',
ADD COLUMN IF NOT EXISTS question_scores JSONB DEFAULT '[]'; -- [{"question": "...", "answer": "...", "score": 8}]

-- Добавляем индексы для новых полей
CREATE INDEX IF NOT EXISTS idx_interview_transcript_search ON interview_dialogs USING gin(to_tsvector('russian', interview_transcript));
CREATE INDEX IF NOT EXISTS idx_full_report_search ON interview_dialogs USING gin(full_interview_report);

-- Комментарии к новым колонкам
COMMENT ON COLUMN interview_dialogs.full_interview_report IS 'Полный структурированный отчет интервью от Speakalka (JSON)';
COMMENT ON COLUMN interview_dialogs.interview_transcript IS 'Полный текстовый транскрипт интервью';
COMMENT ON COLUMN interview_dialogs.emotion_analysis_summary IS 'Сводка анализа эмоций кандидата';
COMMENT ON COLUMN interview_dialogs.question_scores IS 'Массив оценок по каждому вопросу с транскриптами';

-- Создаем функцию для сохранения отчета от Speakalka
CREATE OR REPLACE FUNCTION save_speakalka_interview_report(
    p_candidate_id VARCHAR(50),
    p_round_number INTEGER,
    p_full_report JSONB,
    p_transcript TEXT,
    p_emotion_analysis JSONB,
    p_question_scores JSONB
) RETURNS BOOLEAN AS $$
DECLARE
    dialog_exists BOOLEAN;
BEGIN
    -- Проверяем существует ли запись диалога
    SELECT EXISTS(
        SELECT 1 FROM interview_dialogs 
        WHERE candidate_id = p_candidate_id 
        AND round_number = p_round_number
    ) INTO dialog_exists;
    
    IF dialog_exists THEN
        -- Обновляем существующую запись
        UPDATE interview_dialogs 
        SET 
            full_interview_report = p_full_report,
            interview_transcript = p_transcript,
            emotion_analysis_summary = p_emotion_analysis,
            question_scores = p_question_scores,
            status = 'completed',
            ended_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE candidate_id = p_candidate_id 
        AND round_number = p_round_number;
    ELSE
        -- Создаем новую запись
        INSERT INTO interview_dialogs (
            candidate_id, round_number, dialog_type,
            full_interview_report, interview_transcript,
            emotion_analysis_summary, question_scores,
            status, ended_at
        ) VALUES (
            p_candidate_id, p_round_number, 'technical',
            p_full_report, p_transcript,
            p_emotion_analysis, p_question_scores,
            'completed', CURRENT_TIMESTAMP
        );
    END IF;
    
    RETURN TRUE;
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'Ошибка сохранения отчета Speakalka: %', SQLERRM;
        RETURN FALSE;
END;
$$ LANGUAGE plpgsql;

-- Создаем представление для удобного доступа к отчетам интервью
CREATE OR REPLACE VIEW interview_reports_full AS
SELECT 
    c.candidate_name,
    c.candidate_id,
    r.vacancy_title,
    cv.score as cv_score,
    cv.suitability_conclusion,
    
    -- Данные интервью
    id.round_number,
    id.dialog_type,
    id.technical_score,
    id.communication_score,
    id.culture_fit_score,
    id.duration_minutes,
    
    -- Новые поля отчета
    id.full_interview_report,
    id.interview_transcript,
    id.emotion_analysis_summary,
    id.question_scores,
    
    -- Временные метки
    id.started_at,
    id.ended_at,
    id.status,
    
    -- Итоговое решение
    fd.decision,
    fd.overall_score,
    fd.decision_reason

FROM candidates c
LEFT JOIN requests r ON c.request_id = r.request_id
LEFT JOIN cv_analysis cv ON c.candidate_id = cv.candidate_id
LEFT JOIN interview_dialogs id ON c.candidate_id = id.candidate_id
LEFT JOIN final_decisions fd ON c.candidate_id = fd.candidate_id
WHERE id.candidate_id IS NOT NULL
ORDER BY id.started_at DESC;

COMMENT ON VIEW interview_reports_full IS 'Полное представление отчетов интервью с данными от Speakalka';
