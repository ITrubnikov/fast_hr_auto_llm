import os
import asyncpg
import pandas as pd
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import json


@dataclass
class CandidateReport:
    """Структура итогового отчета о кандидате"""
    candidate_id: str
    candidate_name: str
    email: str
    preferred_contact: str
    filename: str
    request_id: str
    vacancy_title: str
    
    # CV Analysis данные
    cv_score: Optional[int] = None
    cv_reasoning: Optional[str] = None
    cv_summary: Optional[str] = None
    key_strengths: Optional[List[str]] = None
    concerns: Optional[List[str]] = None
    interview_questions: Optional[List[str]] = None
    
    # Interview данные
    interview_scheduled: bool = False
    interview_date: Optional[datetime] = None
    email_sent: bool = False
    interviewer_name: Optional[str] = None
    interview_format: Optional[str] = None
    
    # Dialog данные
    interview_completed: bool = False
    dialog_summary: Optional[str] = None
    interview_score: Optional[int] = None
    total_questions: int = 0
    answered_questions: int = 0
    dialog_details: Optional[List[Dict]] = None
    
    # Final Decision данные
    final_decision: Optional[str] = None
    decision_reason: Optional[str] = None
    overall_score: Optional[int] = None
    salary_offer: Optional[int] = None
    decided_by: Optional[str] = None
    decision_date: Optional[datetime] = None


class HRReportDatabase:
    """Класс для работы с базой данных HR системы"""
    
    def __init__(self):
        self.db_url = os.getenv(
            "DATABASE_URL", 
            "postgresql://hr_user:hr_secure_password_2024@postgres_hr:5432/hr_system"
        )
        self.enabled = os.getenv("DATABASE_ENABLED", "true").lower() == "true"
    
    async def get_candidate_report(self, candidate_id: str) -> Optional[CandidateReport]:
        """Получает полный отчет о кандидате из базы данных"""
        if not self.enabled:
            print(f"Database is disabled: DATABASE_ENABLED={os.getenv('DATABASE_ENABLED', 'not set')}")
            return None
            
        try:
            print(f"Attempting to connect to: {self.db_url}")
            conn = await asyncpg.connect(self.db_url)
            print(f"Successfully connected to database")
            
            # Базовая информация о кандидате
            candidate_query = """
            SELECT 
                c.candidate_id,
                c.candidate_name,
                c.email,
                c.preferred_contact,
                c.filename,
                c.request_id,
                r.vacancy_title
            FROM candidates c
            LEFT JOIN requests r ON c.request_id = r.request_id
            WHERE c.candidate_id = $1
            """
            
            candidate_row = await conn.fetchrow(candidate_query, candidate_id)
            if not candidate_row:
                await conn.close()
                return None
            
            report = CandidateReport(
                candidate_id=candidate_row['candidate_id'],
                candidate_name=candidate_row['candidate_name'],
                email=candidate_row['email'] or "",
                preferred_contact=candidate_row['preferred_contact'] or "",
                filename=candidate_row['filename'] or "",
                request_id=str(candidate_row['request_id']),
                vacancy_title=candidate_row['vacancy_title'] or ""
            )
            
            # CV Analysis данные
            cv_query = """
            SELECT 
                score, reasoning, cv_summary, key_strengths, 
                concerns, interview_questions, analyzed_at
            FROM cv_analysis
            WHERE candidate_id = $1
            """
            
            cv_row = await conn.fetchrow(cv_query, candidate_id)
            if cv_row:
                report.cv_score = cv_row['score']
                report.cv_reasoning = cv_row['reasoning']
                report.cv_summary = cv_row['cv_summary']
                
                # Парсим JSON поля
                try:
                    if cv_row['key_strengths']:
                        report.key_strengths = json.loads(cv_row['key_strengths'])
                    if cv_row['concerns']:
                        report.concerns = json.loads(cv_row['concerns'])
                    if cv_row['interview_questions']:
                        report.interview_questions = json.loads(cv_row['interview_questions'])
                except json.JSONDecodeError:
                    pass
            
            # Interview Scheduled данные
            interview_query = """
            SELECT 
                interview_date, email_sent, interviewer_name, 
                interview_format, email_sent_at
            FROM interviews_scheduled
            WHERE candidate_id = $1
            """
            
            interview_row = await conn.fetchrow(interview_query, candidate_id)
            if interview_row:
                report.interview_scheduled = True
                report.interview_date = interview_row['interview_date']
                report.email_sent = interview_row['email_sent'] or False
                report.interviewer_name = interview_row['interviewer_name']
                report.interview_format = interview_row['interview_format']
            
            # Interview Dialog данные
            dialog_query = """
            SELECT 
                interviewer_notes, technical_score, communication_score, 
                culture_fit_score, dialog_messages, duration_minutes,
                started_at, ended_at, created_at
            FROM interview_dialogs
            WHERE candidate_id = $1
            """
            
            dialog_row = await conn.fetchrow(dialog_query, candidate_id)
            if dialog_row:
                report.interview_completed = True
                report.dialog_summary = dialog_row['interviewer_notes'] or "Нет комментариев"
                
                # Средний балл из трех компонентов
                scores = [
                    dialog_row['technical_score'] or 0,
                    dialog_row['communication_score'] or 0, 
                    dialog_row['culture_fit_score'] or 0
                ]
                report.interview_score = round(sum(s for s in scores if s > 0) / len([s for s in scores if s > 0])) if any(scores) else 0
                
                # Считаем вопросы из dialog_messages
                if dialog_row['dialog_messages'] and isinstance(dialog_row['dialog_messages'], list):
                    report.total_questions = len(dialog_row['dialog_messages'])
                    report.answered_questions = report.total_questions
                    report.dialog_details = dialog_row['dialog_messages']
                else:
                    report.total_questions = 0
                    report.answered_questions = 0
                    report.dialog_details = []
            
            # Final Decision данные
            decision_query = """
            SELECT 
                decision, decision_reason, overall_score, 
                salary_offer, decided_by, decision_date
            FROM final_decisions
            WHERE candidate_id = $1
            """
            
            decision_row = await conn.fetchrow(decision_query, candidate_id)
            if decision_row:
                report.final_decision = decision_row['decision']
                report.decision_reason = decision_row['decision_reason']
                report.overall_score = decision_row['overall_score']
                report.salary_offer = decision_row['salary_offer']
                report.decided_by = decision_row['decided_by']
                report.decision_date = decision_row['decision_date']
            
            await conn.close()
            return report
            
        except Exception as e:
            print(f"Ошибка получения данных о кандидате {candidate_id}: {e}")
            print(f"DB URL: {self.db_url}")
            print(f"DB enabled: {self.enabled}")
            import traceback
            traceback.print_exc()
            return None
    
    async def get_candidates_list(self, request_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Получает список всех кандидатов или кандидатов конкретного запроса"""
        if not self.enabled:
            return []
            
        try:
            conn = await asyncpg.connect(self.db_url)
            
            if request_id:
                query = """
                SELECT 
                    c.candidate_id,
                    c.candidate_name,
                    r.vacancy_title,
                    c.created_at,
                    CASE WHEN fd.candidate_id IS NOT NULL THEN 'completed'
                         WHEN id.candidate_id IS NOT NULL THEN 'interviewed'
                         WHEN ints.candidate_id IS NOT NULL THEN 'scheduled'
                         WHEN cv.candidate_id IS NOT NULL THEN 'analyzed'
                         ELSE 'new'
                    END as status
                FROM candidates c
                LEFT JOIN requests r ON c.request_id = r.request_id
                LEFT JOIN cv_analysis cv ON c.candidate_id = cv.candidate_id
                LEFT JOIN interviews_scheduled ints ON c.candidate_id = ints.candidate_id
                LEFT JOIN interview_dialogs id ON c.candidate_id = id.candidate_id
                LEFT JOIN final_decisions fd ON c.candidate_id = fd.candidate_id
                WHERE c.request_id = $1
                ORDER BY c.created_at DESC
                """
                rows = await conn.fetch(query, request_id)
            else:
                query = """
                SELECT 
                    c.candidate_id,
                    c.candidate_name,
                    r.vacancy_title,
                    c.created_at,
                    CASE WHEN fd.candidate_id IS NOT NULL THEN 'completed'
                         WHEN id.candidate_id IS NOT NULL THEN 'interviewed'
                         WHEN ints.candidate_id IS NOT NULL THEN 'scheduled'
                         WHEN cv.candidate_id IS NOT NULL THEN 'analyzed'
                         ELSE 'new'
                    END as status
                FROM candidates c
                LEFT JOIN requests r ON c.request_id = r.request_id
                LEFT JOIN cv_analysis cv ON c.candidate_id = cv.candidate_id
                LEFT JOIN interviews_scheduled ints ON c.candidate_id = ints.candidate_id
                LEFT JOIN interview_dialogs id ON c.candidate_id = id.candidate_id
                LEFT JOIN final_decisions fd ON c.candidate_id = fd.candidate_id
                ORDER BY c.created_at DESC
                LIMIT 50
                """
                rows = await conn.fetch(query)
            
            await conn.close()
            
            return [
                {
                    'candidate_id': row['candidate_id'],
                    'candidate_name': row['candidate_name'],
                    'vacancy_title': row['vacancy_title'] or "Не указана",
                    'created_at': row['created_at'],
                    'status': row['status']
                }
                for row in rows
            ]
            
        except Exception as e:
            print(f"Ошибка получения списка кандидатов: {e}")
            return []


class ReportAnalyzer:
    """Анализатор для генерации итоговых отчетов"""
    
    def __init__(self):
        self.db = HRReportDatabase()
    
    def calculate_overall_rating(self, report: CandidateReport) -> Dict[str, Any]:
        """Вычисляет общий рейтинг кандидата"""
        scores = []
        weights = []
        
        # CV анализ (30% веса)
        if report.cv_score is not None:
            scores.append(report.cv_score)
            weights.append(0.3)
        
        # Интервью (50% веса)
        if report.interview_score is not None:
            scores.append(report.interview_score)
            weights.append(0.5)
        
        # Финальная оценка (20% веса)
        if report.overall_score is not None:
            scores.append(report.overall_score)
            weights.append(0.2)
        
        if not scores:
            return {
                'total_score': 0,
                'rating': 'Нет данных',
                'color': 'gray'
            }
        
        # Взвешенная средняя
        if len(scores) > 1:
            total_weight = sum(weights)
            weighted_score = sum(s * w for s, w in zip(scores, weights)) / total_weight
        else:
            weighted_score = scores[0]
        
        # Определяем рейтинг
        if weighted_score >= 8:
            rating = "Отличный кандидат"
            color = "green"
        elif weighted_score >= 6:
            rating = "Хороший кандидат"
            color = "blue"
        elif weighted_score >= 4:
            rating = "Средний кандидат"
            color = "orange"
        else:
            rating = "Слабый кандидат"
            color = "red"
        
        return {
            'total_score': round(weighted_score, 1),
            'rating': rating,
            'color': color,
            'cv_score': report.cv_score,
            'interview_score': report.interview_score,
            'final_score': report.overall_score
        }
    
    def get_process_status(self, report: CandidateReport) -> Dict[str, Any]:
        """Определяет статус прохождения процесса"""
        stages = {
            'cv_analysis': bool(report.cv_score is not None),
            'interview_scheduled': report.interview_scheduled,
            'interview_completed': report.interview_completed,
            'final_decision': bool(report.final_decision is not None)
        }
        
        completed_stages = sum(stages.values())
        total_stages = len(stages)
        
        current_stage = "Анализ CV"
        if stages['final_decision']:
            current_stage = "Процесс завершен"
        elif stages['interview_completed']:
            current_stage = "Принятие решения"
        elif stages['interview_scheduled']:
            current_stage = "Проведение интервью"
        elif stages['cv_analysis']:
            current_stage = "Планирование интервью"
        
        return {
            'stages': stages,
            'completed_stages': completed_stages,
            'total_stages': total_stages,
            'progress_percent': (completed_stages / total_stages) * 100,
            'current_stage': current_stage
        }
