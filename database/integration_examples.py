# ===============================================
# HR System Database Integration Examples
# Примеры интеграции всех 4 блоков с PostgreSQL
# ===============================================

import asyncpg
import json
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Optional

# Настройки подключения к БД
DATABASE_URL = "postgresql://hr_user:hr_secure_password_2024@localhost:5432/hr_system"

# ===============================================
# БЛОК 1: ИНТЕГРАЦИЯ CV-UI с БД
# ===============================================

class Block1_CVAnalysisDB:
    """Интеграция первого блока (анализ CV) с базой данных"""
    
    def __init__(self, db_url: str = DATABASE_URL):
        self.db_url = db_url
    
    async def save_cv_analysis_results(
        self, 
        request_id: str,
        vacancy_title: str, 
        vacancy_description: str,
        candidates_data: List[Dict]
    ) -> str:
        """
        Сохранение результатов анализа CV в БД
        Вызывается из cv-ui модуля после завершения анализа
        """
        conn = await asyncpg.connect(self.db_url)
        try:
            # Используем готовую функцию БД
            result = await conn.fetchval(
                """
                SELECT insert_cv_analysis_data($1::UUID, $2, $3, $4::JSONB)
                """,
                uuid.UUID(request_id),
                vacancy_title,
                vacancy_description,
                json.dumps(candidates_data)
            )
            return str(result)
        finally:
            await conn.close()
    
    # Пример использования в cv-ui/app.py:
    """
    # В конце функции process_uploaded_files()
    async def save_to_database(self, results: List[CandidateResult], 
                              job_description: str, vacancy_title: str):
        db_client = Block1_CVAnalysisDB()
        candidates_data = []
        
        for result in results:
            candidates_data.append({
                "candidateId": result.candidate_id,
                "candidateName": result.name,
                "email": result.email,
                "preferredContact": result.preferred_contact,
                "cvText": result.cv_text,
                "score": result.score,
                "reasoning": result.reasoning,
                "suitabilityConclusion": _conclusion(result.score),
                "questionsForApplicant": result.interview_questions
            })
        
        request_id = st.session_state.get("request_id")
        await db_client.save_cv_analysis_results(
            request_id, vacancy_title, job_description, candidates_data
        )
    """

# ===============================================
# БЛОК 2: ПЛАНИРОВАНИЕ ИНТЕРВЬЮ
# ===============================================

class Block2_InterviewSchedulingDB:
    """Интеграция второго блока (планирование интервью) с БД"""
    
    def __init__(self, db_url: str = DATABASE_URL):
        self.db_url = db_url
    
    async def get_candidates_for_scheduling(
        self, 
        request_id: Optional[str] = None,
        min_score: int = 6
    ) -> List[Dict]:
        """Получение кандидатов для планирования интервью"""
        conn = await asyncpg.connect(self.db_url)
        try:
            if request_id:
                rows = await conn.fetch(
                    "SELECT * FROM get_candidates_for_interview_scheduling($1::UUID, $2)",
                    uuid.UUID(request_id), min_score
                )
            else:
                rows = await conn.fetch(
                    "SELECT * FROM get_candidates_for_interview_scheduling(NULL, $1)",
                    min_score
                )
            
            candidates = []
            for row in rows:
                candidates.append({
                    'candidate_id': row['candidate_id'],
                    'candidate_name': row['candidate_name'],
                    'email': row['email'],
                    'preferred_contact': row['preferred_contact'],
                    'score': row['score'],
                    'suitability_conclusion': row['suitability_conclusion'],
                    'interview_questions': row['interview_questions'],
                    'vacancy_title': row['vacancy_title']
                })
            return candidates
        finally:
            await conn.close()
    
    async def schedule_interview(
        self,
        candidate_id: str,
        interview_date: datetime,
        interviewer_name: str,
        interviewer_email: str,
        meeting_link: Optional[str] = None
    ) -> bool:
        """Планирование интервью с кандидатом"""
        conn = await asyncpg.connect(self.db_url)
        try:
            result = await conn.fetchval(
                "SELECT schedule_interview($1, $2, $3, $4, $5)",
                candidate_id, interview_date, interviewer_name,
                interviewer_email, meeting_link
            )
            return result
        finally:
            await conn.close()
    
    async def mark_email_sent(self, candidate_id: str, status: str = 'sent') -> bool:
        """Отметка об отправке email уведомления"""
        conn = await asyncpg.connect(self.db_url)
        try:
            await conn.execute(
                """
                UPDATE interviews_scheduled 
                SET email_sent = TRUE, email_sent_at = CURRENT_TIMESTAMP, email_status = $2
                WHERE candidate_id = $1
                """,
                candidate_id, status
            )
            return True
        finally:
            await conn.close()
    
    # Пример использования в блоке 2:
    """
    # Основной workflow блока 2
    async def main_scheduling_workflow():
        db_client = Block2_InterviewSchedulingDB()
        
        # 1. Получаем кандидатов для планирования
        candidates = await db_client.get_candidates_for_scheduling(min_score=6)
        
        # 2. Планируем интервью для каждого подходящего кандидата
        for candidate in candidates:
            if candidate['score'] >= 7:  # Только высокие оценки
                interview_date = datetime.now() + timedelta(days=2)
                
                success = await db_client.schedule_interview(
                    candidate['candidate_id'],
                    interview_date,
                    "Анна Иванова",
                    "anna.ivanova@company.com",
                    "https://zoom.us/j/123456789"
                )
                
                if success:
                    # 3. Отправляем email и отмечаем в БД
                    await send_interview_invitation_email(candidate)
                    await db_client.mark_email_sent(candidate['candidate_id'])
    """

# ===============================================
# БЛОК 3: ДИАЛОГИ ИНТЕРВЬЮ
# ===============================================

class Block3_InterviewDialogsDB:
    """Интеграция третьего блока (диалоги интервью) с БД"""
    
    def __init__(self, db_url: str = DATABASE_URL):
        self.db_url = db_url
    
    async def get_scheduled_interviews(self) -> List[Dict]:
        """Получение запланированных интервью"""
        conn = await asyncpg.connect(self.db_url)
        try:
            rows = await conn.fetch(
                """
                SELECT 
                    i.candidate_id, c.candidate_name, i.interview_date,
                    i.interviewer_name, i.meeting_link, cv.interview_questions,
                    r.vacancy_title
                FROM interviews_scheduled i
                JOIN candidates c ON i.candidate_id = c.candidate_id  
                JOIN cv_analysis cv ON c.candidate_id = cv.candidate_id
                JOIN requests r ON c.request_id = r.request_id
                WHERE i.interview_date BETWEEN CURRENT_TIMESTAMP 
                    AND CURRENT_TIMESTAMP + INTERVAL '24 hours'
                ORDER BY i.interview_date
                """
            )
            
            interviews = []
            for row in rows:
                interviews.append({
                    'candidate_id': row['candidate_id'],
                    'candidate_name': row['candidate_name'],
                    'interview_date': row['interview_date'],
                    'interviewer_name': row['interviewer_name'],
                    'meeting_link': row['meeting_link'],
                    'interview_questions': row['interview_questions'],
                    'vacancy_title': row['vacancy_title']
                })
            return interviews
        finally:
            await conn.close()
    
    async def save_interview_dialog(
        self,
        candidate_id: str,
        dialog_messages: List[Dict],
        technical_score: Optional[int] = None,
        communication_score: Optional[int] = None,
        culture_fit_score: Optional[int] = None,
        interviewer_notes: Optional[str] = None
    ) -> int:
        """Сохранение диалога интервью"""
        conn = await asyncpg.connect(self.db_url)
        try:
            dialog_id = await conn.fetchval(
                "SELECT save_interview_dialog($1, $2::JSONB, $3, $4, $5, $6)",
                candidate_id, json.dumps(dialog_messages),
                technical_score, communication_score, culture_fit_score,
                interviewer_notes
            )
            return dialog_id
        finally:
            await conn.close()
    
    async def update_interview_status(
        self,
        candidate_id: str,
        round_number: int,
        status: str,
        duration_minutes: Optional[int] = None
    ) -> bool:
        """Обновление статуса интервью"""
        conn = await asyncpg.connect(self.db_url)
        try:
            await conn.execute(
                """
                UPDATE interview_dialogs 
                SET status = $3, duration_minutes = $4, ended_at = CURRENT_TIMESTAMP
                WHERE candidate_id = $1 AND round_number = $2
                """,
                candidate_id, round_number, status, duration_minutes
            )
            return True
        finally:
            await conn.close()
    
    # Пример использования в блоке 3:
    """
    # WebSocket handler для интервью
    async def handle_interview_session(websocket, candidate_id: str):
        db_client = Block3_InterviewDialogsDB()
        dialog_messages = []
        
        async for message in websocket:
            # Сохраняем каждое сообщение
            dialog_messages.append({
                "role": message["role"],
                "message": message["content"], 
                "timestamp": datetime.now().isoformat()
            })
            
            # Периодически сохраняем в БД
            if len(dialog_messages) % 10 == 0:
                await db_client.save_interview_dialog(
                    candidate_id, dialog_messages
                )
        
        # Финальное сохранение с оценками
        await db_client.save_interview_dialog(
            candidate_id, dialog_messages,
            technical_score=8, communication_score=7, culture_fit_score=9,
            interviewer_notes="Отличные технические знания, хорошая коммуникация"
        )
    """

# ===============================================
# БЛОК 4: ИТОГОВЫЕ РЕШЕНИЯ  
# ===============================================

class Block4_FinalDecisionsDB:
    """Интеграция четвертого блока (итоговые решения) с БД"""
    
    def __init__(self, db_url: str = DATABASE_URL):
        self.db_url = db_url
    
    async def get_candidates_for_decision(self) -> List[Dict]:
        """Получение кандидатов готовых для принятия решения"""
        conn = await asyncpg.connect(self.db_url)
        try:
            rows = await conn.fetch(
                """
                SELECT 
                    c.candidate_id, c.candidate_name, c.email, c.preferred_contact,
                    cv.score as cv_score, cv.suitability_conclusion,
                    AVG(d.technical_score) as avg_technical_score,
                    AVG(d.communication_score) as avg_communication_score,
                    AVG(d.culture_fit_score) as avg_culture_fit_score,
                    COUNT(d.id) as interviews_completed,
                    r.vacancy_title
                FROM candidates c
                JOIN cv_analysis cv ON c.candidate_id = cv.candidate_id
                JOIN requests r ON c.request_id = r.request_id
                LEFT JOIN interview_dialogs d ON c.candidate_id = d.candidate_id 
                    AND d.status = 'completed'
                LEFT JOIN final_decisions fd ON c.candidate_id = fd.candidate_id
                WHERE fd.candidate_id IS NULL  -- Еще не принято решение
                GROUP BY c.candidate_id, c.candidate_name, c.email, c.preferred_contact,
                         cv.score, cv.suitability_conclusion, r.vacancy_title
                HAVING COUNT(d.id) > 0  -- Есть завершенные интервью
                ORDER BY cv.score DESC, AVG(d.technical_score) DESC
                """
            )
            
            candidates = []
            for row in rows:
                candidates.append({
                    'candidate_id': row['candidate_id'],
                    'candidate_name': row['candidate_name'],
                    'email': row['email'],
                    'preferred_contact': row['preferred_contact'],
                    'cv_score': row['cv_score'],
                    'suitability_conclusion': row['suitability_conclusion'],
                    'avg_technical_score': float(row['avg_technical_score']) if row['avg_technical_score'] else None,
                    'avg_communication_score': float(row['avg_communication_score']) if row['avg_communication_score'] else None,
                    'avg_culture_fit_score': float(row['avg_culture_fit_score']) if row['avg_culture_fit_score'] else None,
                    'interviews_completed': row['interviews_completed'],
                    'vacancy_title': row['vacancy_title']
                })
            return candidates
        finally:
            await conn.close()
    
    async def make_final_decision(
        self,
        candidate_id: str,
        decision: str,  # 'hired', 'rejected', 'pending', 'on_hold'
        decision_reason: str,
        overall_score: Optional[int] = None,
        salary_offer: Optional[str] = None,
        position_offered: Optional[str] = None,
        decided_by: Optional[str] = None
    ) -> bool:
        """Принятие финального решения по кандидату"""
        conn = await asyncpg.connect(self.db_url)
        try:
            result = await conn.fetchval(
                "SELECT make_final_decision($1, $2, $3, $4, $5, $6, $7)",
                candidate_id, decision, decision_reason, overall_score,
                salary_offer, position_offered, decided_by
            )
            return result
        finally:
            await conn.close()
    
    async def get_hired_candidates(self) -> List[Dict]:
        """Получение кандидатов с положительным решением"""
        conn = await asyncpg.connect(self.db_url)
        try:
            rows = await conn.fetch("SELECT * FROM candidates_ready_to_hire")
            
            hired = []
            for row in rows:
                hired.append({
                    'candidate_id': row['candidate_id'],
                    'candidate_name': row['candidate_name'],
                    'email': row['email'],
                    'preferred_contact': row['preferred_contact'],
                    'cv_score': row['cv_score'],
                    'overall_score': row['overall_score'],
                    'salary_offer': row['salary_offer'],
                    'position_offered': row['position_offered'],
                    'start_date': row['start_date'],
                    'vacancy_title': row['vacancy_title']
                })
            return hired
        finally:
            await conn.close()
    
    # Пример использования в блоке 4:
    """
    # Автоматическое принятие решений на основе критериев
    async def automated_decision_making():
        db_client = Block4_FinalDecisionsDB()
        
        candidates = await db_client.get_candidates_for_decision()
        
        for candidate in candidates:
            cv_score = candidate['cv_score']
            tech_score = candidate['avg_technical_score'] or 0
            comm_score = candidate['avg_communication_score'] or 0
            
            # Критерии найма
            if (cv_score >= 8 and tech_score >= 7 and comm_score >= 7):
                await db_client.make_final_decision(
                    candidate['candidate_id'],
                    'hired',
                    'Высокие оценки по всем критериям',
                    overall_score=9,
                    salary_offer='320000 RUB',
                    position_offered='Senior Python Developer',
                    decided_by='automated_system'
                )
            elif (cv_score >= 6 and tech_score >= 6):
                await db_client.make_final_decision(
                    candidate['candidate_id'],
                    'pending',
                    'Хорошие результаты, требуется дополнительная проверка',
                    overall_score=7,
                    decided_by='automated_system'
                )
            else:
                await db_client.make_final_decision(
                    candidate['candidate_id'],
                    'rejected',
                    'Не соответствует минимальным требованиям',
                    overall_score=candidate['cv_score'],
                    decided_by='automated_system'
                )
    """

# ===============================================
# АНАЛИТИКА И ОТЧЕТЫ
# ===============================================

class HRAnalyticsDB:
    """Аналитика и отчеты по HR процессам"""
    
    def __init__(self, db_url: str = DATABASE_URL):
        self.db_url = db_url
    
    async def get_hr_analytics(self, days: int = 30) -> Dict:
        """Получение аналитики за период"""
        conn = await asyncpg.connect(self.db_url)
        try:
            from_date = datetime.now() - timedelta(days=days)
            row = await conn.fetchrow(
                "SELECT * FROM get_hr_analytics($1, $2)",
                from_date, datetime.now()
            )
            
            return {
                'total_requests': row['total_requests'],
                'total_candidates': row['total_candidates'],
                'avg_cv_score': float(row['avg_cv_score']) if row['avg_cv_score'] else 0,
                'interviews_completed': row['interviews_completed'],
                'hired_count': row['hired_count'],
                'rejection_rate': float(row['rejection_rate']) if row['rejection_rate'] else 0
            }
        finally:
            await conn.close()
    
    async def get_detailed_statistics(self) -> Dict:
        """Подробная статистика по всем запросам"""
        conn = await asyncpg.connect(self.db_url)
        try:
            rows = await conn.fetch("SELECT * FROM requests_statistics ORDER BY created_at DESC")
            
            stats = []
            for row in rows:
                stats.append({
                    'request_id': str(row['request_id']),
                    'vacancy_title': row['vacancy_title'],
                    'created_at': row['created_at'],
                    'total_candidates': row['total_candidates'],
                    'analyzed_candidates': row['analyzed_candidates'],
                    'avg_cv_score': float(row['avg_cv_score']) if row['avg_cv_score'] else 0,
                    'high_suitability': row['high_suitability'],
                    'medium_suitability': row['medium_suitability'],
                    'low_suitability': row['low_suitability'],
                    'interviews_scheduled': row['interviews_scheduled'],
                    'emails_sent': row['emails_sent'],
                    'hired': row['hired'],
                    'rejected': row['rejected'],
                    'pending': row['pending']
                })
            return {'requests': stats}
        finally:
            await conn.close()

# ===============================================
# ПРИМЕР ПОЛНОГО WORKFLOW
# ===============================================

async def complete_hr_workflow_example():
    """Пример полного HR workflow через все 4 блока"""
    
    print("=== HR System Workflow Example ===")
    
    # Блок 1: CV анализ (уже выполнен в cv-ui)
    print("1. CV Analysis completed in cv-ui module")
    
    # Блок 2: Планирование интервью
    print("2. Scheduling interviews...")
    block2 = Block2_InterviewSchedulingDB()
    candidates = await block2.get_candidates_for_scheduling(min_score=6)
    print(f"Found {len(candidates)} candidates for interviews")
    
    # Блок 3: Проведение интервью (симуляция)
    print("3. Conducting interviews...")
    block3 = Block3_InterviewDialogsDB()
    for candidate in candidates[:2]:  # Первые 2 кандидата
        dialog_messages = [
            {"role": "interviewer", "message": "Расскажите о своем опыте", "timestamp": datetime.now().isoformat()},
            {"role": "candidate", "message": "У меня 5 лет опыта с Python...", "timestamp": datetime.now().isoformat()}
        ]
        await block3.save_interview_dialog(
            candidate['candidate_id'], dialog_messages,
            technical_score=8, communication_score=7, culture_fit_score=8
        )
    
    # Блок 4: Принятие решений
    print("4. Making final decisions...")
    block4 = Block4_FinalDecisionsDB()
    decision_candidates = await block4.get_candidates_for_decision()
    
    for candidate in decision_candidates:
        if candidate['cv_score'] >= 8:
            await block4.make_final_decision(
                candidate['candidate_id'],
                'hired',
                'Отличные результаты на всех этапах',
                overall_score=9,
                salary_offer='320000 RUB',
                position_offered='Senior Python Developer'
            )
    
    # Аналитика
    print("5. Getting analytics...")
    analytics = HRAnalyticsDB()
    stats = await analytics.get_hr_analytics(days=30)
    print(f"Analytics: {stats}")
    
    print("=== Workflow completed ===")

# Запуск примера
if __name__ == "__main__":
    import asyncio
    asyncio.run(complete_hr_workflow_example())
