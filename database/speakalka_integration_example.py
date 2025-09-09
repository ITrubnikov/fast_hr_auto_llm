"""
Пример интеграции Speakalka (Блок 3) с базой данных
Сохранение полных отчетов интервью
"""

import asyncpg
import json
from typing import Dict, Any, Optional
from datetime import datetime

DATABASE_URL = "postgresql://hr_user:hr_secure_password_2024@postgres_hr:5432/hr_system"


class SpeakalkaDBIntegration:
    """Интеграция системы Speakalka с базой данных"""
    
    def __init__(self, db_url: str = DATABASE_URL):
        self.db_url = db_url
    
    async def save_interview_report(
        self, 
        candidate_id: str,
        interview_report: Dict[str, Any],
        round_number: int = 1
    ) -> bool:
        """
        Сохранение полного отчета интервью от Speakalka
        
        Args:
            candidate_id: ID кандидата (cv_a1b2c3d4e5f6)
            interview_report: Полный отчет интервью от LangGraph системы
            round_number: Номер раунда интервью
            
        Returns:
            bool: Успех операции
        """
        conn = await asyncpg.connect(self.db_url)
        try:
            # Извлекаем данные из отчета Speakalka
            transcript = self._extract_transcript(interview_report)
            emotion_analysis = interview_report.get('emotion_analysis', {})
            question_scores = interview_report.get('question_evaluations', [])
            
            # Вычисляем средние оценки
            technical_score = self._calculate_average_score(question_scores)
            
            # Используем функцию БД для сохранения
            success = await conn.fetchval(
                """
                SELECT save_speakalka_interview_report($1, $2, $3::JSONB, $4, $5::JSONB, $6::JSONB)
                """,
                candidate_id,
                round_number,
                json.dumps(interview_report),  # Полный отчет как JSON
                transcript,                    # Текстовый транскрипт
                json.dumps(emotion_analysis),  # Анализ эмоций
                json.dumps(question_scores)    # Оценки по вопросам
            )
            
            if success:
                print(f"✅ Отчет интервью сохранен для кандидата: {candidate_id}")
                
                # Обновляем оценки в interview_dialogs
                await self._update_interview_scores(
                    conn, candidate_id, round_number, 
                    interview_report
                )
                
                return True
            else:
                print(f"❌ Ошибка сохранения отчета для: {candidate_id}")
                return False
                
        except Exception as e:
            print(f"❌ Ошибка интеграции с БД: {e}")
            return False
        finally:
            await conn.close()
    
    async def _update_interview_scores(
        self, 
        conn, 
        candidate_id: str, 
        round_number: int,
        report: Dict[str, Any]
    ):
        """Обновление оценок в таблице interview_dialogs"""
        
        # Извлекаем оценки из отчета
        technical_score = self._calculate_average_score(
            report.get('question_evaluations', [])
        )
        
        # Примерные оценки коммуникации и культурного соответствия
        # на основе анализа эмоций и качества ответов
        emotion_data = report.get('emotion_analysis', {})
        communication_score = self._calculate_communication_score(emotion_data)
        culture_fit_score = self._calculate_culture_fit_score(emotion_data, report)
        
        # Вычисляем длительность интервью
        duration = report.get('interview_duration_minutes', 0)
        
        await conn.execute(
            """
            UPDATE interview_dialogs 
            SET 
                technical_score = $3,
                communication_score = $4,
                culture_fit_score = $5,
                duration_minutes = $6,
                updated_at = CURRENT_TIMESTAMP
            WHERE candidate_id = $1 AND round_number = $2
            """,
            candidate_id, round_number,
            technical_score, communication_score, 
            culture_fit_score, duration
        )
    
    def _extract_transcript(self, report: Dict[str, Any]) -> str:
        """Извлечение полного транскрипта из отчета"""
        transcript_parts = []
        
        # Добавляем вопросы и ответы
        questions_data = report.get('question_evaluations', [])
        for item in questions_data:
            question = item.get('question', '')
            answer = item.get('answer', '')
            
            if question:
                transcript_parts.append(f"🤖 Интервьюер: {question}")
            if answer:
                transcript_parts.append(f"👤 Кандидат: {answer}")
        
        return "\n\n".join(transcript_parts)
    
    def _calculate_average_score(self, question_scores: list) -> Optional[int]:
        """Вычисление средней оценки по вопросам"""
        if not question_scores:
            return None
            
        scores = [item.get('score', 0) for item in question_scores if item.get('score')]
        return round(sum(scores) / len(scores)) if scores else None
    
    def _calculate_communication_score(self, emotion_data: Dict[str, Any]) -> Optional[int]:
        """Вычисление оценки коммуникации на основе эмоций"""
        if not emotion_data:
            return None
        
        # Ищем позитивные эмоции и уверенность
        enthusiasm = emotion_data.get('enthusiasm', 0)
        confidence = emotion_data.get('confidence', 0)
        happiness = emotion_data.get('happiness', 0)
        
        # Негативные факторы
        fear = emotion_data.get('fear', 0)
        anxiety = emotion_data.get('anxiety', 0)
        
        # Простая формула оценки коммуникации
        positive_score = (enthusiasm + confidence + happiness) / 3
        negative_impact = (fear + anxiety) / 2
        
        communication_score = max(1, min(10, round((positive_score - negative_impact) * 10)))
        return communication_score
    
    def _calculate_culture_fit_score(
        self, 
        emotion_data: Dict[str, Any], 
        report: Dict[str, Any]
    ) -> Optional[int]:
        """Вычисление культурного соответствия"""
        if not emotion_data:
            return None
        
        # Факторы культурного соответствия
        enthusiasm = emotion_data.get('enthusiasm', 0)
        confidence = emotion_data.get('confidence', 0)
        
        # Качество ответов как индикатор заинтересованности
        avg_score = self._calculate_average_score(
            report.get('question_evaluations', [])
        ) or 5
        
        # Нормализуем оценку CV (предполагаем что она есть в отчете)
        normalized_avg = avg_score / 10.0
        
        culture_score = round(((enthusiasm + confidence) / 2 + normalized_avg) / 2 * 10)
        return max(1, min(10, culture_score))


# ===============================================
# ПРИМЕР ИСПОЛЬЗОВАНИЯ В SPEAKALKA
# ===============================================

async def save_interview_results_example():
    """
    Пример вызова из системы Speakalka после завершения интервью
    """
    
    # Пример отчета который генерирует Speakalka
    sample_report = {
        "candidate_id": "cv_a1b2c3d4e5f6",
        "interview_date": "2024-01-15T10:30:00",
        "interview_duration_minutes": 45,
        "total_questions_asked": 8,
        "questions_answered": 7,
        
        "question_evaluations": [
            {
                "question": "Расскажите о вашем опыте с Python",
                "answer": "Я работаю с Python уже 3 года, использую Django и FastAPI...",
                "score": 8,
                "evaluation": "Хороший ответ, демонстрирует практический опыт",
                "topic": "python_experience"
            },
            {
                "question": "Как вы решаете проблемы с производительностью?",
                "answer": "Сначала анализирую профайлером, затем оптимизирую узкие места...",
                "score": 9,
                "evaluation": "Отличный структурированный подход",
                "topic": "performance_optimization"
            }
        ],
        
        "emotion_analysis": {
            "enthusiasm": 0.7,
            "confidence": 0.8,
            "anxiety": 0.2,
            "happiness": 0.6,
            "fear": 0.1
        },
        
        "interview_summary": {
            "overall_impression": "Кандидат демонстрирует хорошие технические знания",
            "strengths": ["Практический опыт", "Системное мышление"],
            "weaknesses": ["Немного нервничал в начале"],
            "recommendation": "Рекомендую к найму"
        },
        
        "technical_assessment": {
            "python_knowledge": 8,
            "database_skills": 7,
            "system_design": 6,
            "problem_solving": 9
        }
    }
    
    # Сохранение в БД
    db_integration = SpeakalkaDBIntegration()
    success = await db_integration.save_interview_report(
        candidate_id="cv_a1b2c3d4e5f6",
        interview_report=sample_report,
        round_number=1
    )
    
    if success:
        print("🎉 Отчет успешно сохранен в базу данных!")
    else:
        print("❌ Ошибка сохранения отчета")


# Пример интеграции в основной код Speakalka
"""
# В файле services/Speakalka/interview_system/langgraph_interview.py
# После завершения интервью:

async def finalize_interview(self, candidate_id: str):
    # ... существующий код генерации отчета ...
    
    # Сохранение в БД
    from database.speakalka_integration_example import SpeakalkaDBIntegration
    
    db_integration = SpeakalkaDBIntegration()
    await db_integration.save_interview_report(
        candidate_id=candidate_id,
        interview_report=self.generate_final_report(),
        round_number=1
    )
"""
