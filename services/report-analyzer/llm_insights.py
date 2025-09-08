# LLM-powered аналитика для кандидатов

import os
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.schema.output_parser import StrOutputParser
from typing import Dict, Any, Optional
import json

class CandidateInsightGenerator:
    """Генератор умных выводов о кандидате с помощью LLM"""
    
    def __init__(self):
        self.enabled = os.getenv("LLM_ENABLED", "false").lower() == "true"
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        self.openrouter_base_url = "https://openrouter.ai/api/v1"
        
        if self.enabled and self.openrouter_api_key:
            self.llm = ChatOpenAI(
                model="openai/gpt-4o-mini",
                temperature=0.3,
                api_key=self.openrouter_api_key,
                base_url=self.openrouter_base_url,
                max_tokens=1000
            )
        else:
            self.llm = None
        
        # Промпт для анализа кандидата
        self.analysis_prompt = PromptTemplate(
            input_variables=["candidate_data", "vacancy_title"],
            template="""
            Ты - эксперт HR с 10+ лет опыта. Проведи глубокий анализ кандидата на позицию {vacancy_title}.
            
            ДАННЫЕ КАНДИДАТА:
            {candidate_data}
            
            ЗАДАЧА: Составь детальный профессиональный отчет со следующими разделами:

            1. ИСПОЛНИТЕЛЬНОЕ РЕЗЮМЕ (3-4 предложения) - ключевые выводы для руководства
            
            2. СИЛЬНЫЕ СТОРОНЫ (3-5 пунктов) - конкретные навыки и достижения
            
            3. ОБЛАСТИ РАЗВИТИЯ (2-4 пункта) - навыки, требующие улучшения
            
            4. ФИНАЛЬНАЯ РЕКОМЕНДАЦИЯ:
               - hired: если кандидат превосходит ожидания  
               - rejected: если не соответствует требованиям
               - additional_interview: если нужна дополнительная оценка
               - manual_review: если требуется экспертное мнение
               
            5. ПРЕДЛОЖЕНИЕ ЗАРПЛАТЫ (для hired) - основанное на опыте и навыках
            
            6. УРОВЕНЬ УВЕРЕННОСТИ в оценке
            
            ВАЖНО: Учитывай специфику позиции, уровень требований, опыт кандидата.
            
            Ответ СТРОГО в JSON формате:
            {{
                "summary": "детальное исполнительное резюме для руководства",
                "strengths": ["конкретная сильная сторона 1", "конкретная сильная сторона 2", "..."],
                "development_areas": ["область развития 1", "область развития 2"],
                "recommendation": "hired|rejected|additional_interview|manual_review",
                "salary_range": "диапазон в рублях (если hired) или null",
                "confidence": "высокая|средняя|низкая"
            }}
            """
        )
    
    def generate_insights(self, candidate_data: Dict[str, Any], vacancy_title: str) -> Dict[str, Any]:
        """Генерирует умные выводы о кандидате"""
        
        if not self.enabled or not self.llm:
            return {
                "summary": "🤖 LLM анализ отключен. Включите в настройках.",
                "strengths": ["Анализ недоступен"],
                "development_areas": ["Анализ недоступен"], 
                "recommendation": "manual_review",
                "salary_range": "Определите самостоятельно",
                "confidence": "низкая"
            }
        
        try:
            # Подготовка данных для LLM
            formatted_data = self._format_candidate_data(candidate_data)
            
            # Создаем цепочку: промпт → LLM → парсер
            chain = self.analysis_prompt | self.llm | StrOutputParser()
            
            # Генерация через LLM
            result = chain.invoke({
                "candidate_data": formatted_data,
                "vacancy_title": vacancy_title
            })
            
            # Парсинг JSON ответа (может быть в markdown блоке)
            try:
                parsed_json = self._extract_json_from_response(result)
                return parsed_json
            except (json.JSONDecodeError, ValueError) as e:
                print(f"Ошибка парсинга JSON: {e}")
                print(f"Сырой ответ LLM: {result}")
                # Если не JSON, возвращаем как текстовый анализ
                return {
                    "summary": "❌ Ошибка парсинга ответа LLM",
                    "strengths": ["Анализ недоступен"],
                    "development_areas": ["Анализ недоступен"],
                    "recommendation": "manual_review", 
                    "salary_range": "Определите самостоятельно",
                    "confidence": "низкая"
                }
                
        except Exception as e:
            return {
                "summary": f"❌ Ошибка LLM анализа: {str(e)}",
                "strengths": ["Ошибка генерации"],
                "development_areas": ["Ошибка генерации"],
                "recommendation": "manual_review",
                "salary_range": "Определите самостоятельно", 
                "confidence": "низкая"
            }
    
    def _format_candidate_data(self, data: Dict[str, Any]) -> str:
        """Форматирует данные кандидата для LLM"""
        cv_score = data.get('cv_score', 'н/д')
        interview_score = data.get('interview_score', 'н/д')
        overall_score = data.get('overall_score', 'н/д')
        
        # Определяем уровень по оценкам
        def get_level(score):
            if score == 'н/д' or score is None:
                return 'не оценено'
            if score >= 8:
                return 'высокий'
            elif score >= 6:
                return 'средний'
            else:
                return 'низкий'
        
        # Форматируем детали интервью
        interview_section = ""
        if data.get('interview_details'):
            interview_section = f"""
=== ДЕТАЛИ ИНТЕРВЬЮ (вопросы и ответы) ===
{data.get('interview_details')}
"""
        
        # Форматируем финальное решение  
        decision_section = ""
        if data.get('final_decision'):
            decision_section = f"""
=== ФИНАЛЬНОЕ РЕШЕНИЕ HR ===
• Решение: {data.get('final_decision', 'н/д')}
• Общая оценка: {overall_score}/10 (уровень: {get_level(overall_score)})
• Обоснование решения: {data.get('decision_reason', 'Не указано')}
• Предложенная зарплата: {data.get('salary_offer', 'Не указана')}
"""
        
        return f"""
=== ПРОФИЛЬ КАНДИДАТА ===
Имя: {data.get('name', 'Неизвестно')}
Текущий этап процесса: {data.get('current_stage', 'н/д')}

=== АНАЛИЗ РЕЗЮМЕ (БЛОК 1) ===
• Оценка CV: {cv_score}/10 (уровень: {get_level(cv_score if cv_score != 'н/д' else 0)})
• Обоснование оценки: {data.get('cv_reasoning', 'Нет данных')}
• Сильные стороны: {', '.join(data.get('key_strengths', ['Не указаны']))}
• Замечания и риски: {', '.join(data.get('concerns', ['Нет замечаний']))}

=== СОБЕСЕДОВАНИЕ (БЛОК 2-3) ===
• Интервью запланировано: {'Да' if data.get('interview_scheduled') else 'Нет'}
• Интервью завершено: {'Да' if data.get('interview_completed') else 'Нет'}
• Оценка интервью: {interview_score}/10 (уровень: {get_level(interview_score if interview_score != 'н/д' else 0)})
• Всего вопросов: {data.get('total_questions', 0)} | Отвечено: {data.get('answered_questions', 0)}
• Резюме интервьюера: {data.get('dialog_summary', 'Интервью не проведено')}{interview_section}{decision_section}

=== ГОТОВНОСТЬ К РЕШЕНИЮ ===
• Полнота процесса: {('Все этапы завершены' if cv_score != 'н/д' and interview_score != 'н/д' else 'Требуется завершить оценку')}
• Статус: {data.get('current_stage', 'Не определен')}
        """
    
    def generate_quick_summary(self, candidate_data: Dict[str, Any]) -> str:
        """Генерирует сверх-краткое резюме кандидата в 1 предложение"""
        
        if not self.enabled or not self.llm:
            return "🤖 Краткий ИИ-анализ недоступен"
        
        try:
            quick_prompt = PromptTemplate(
                input_variables=["candidate_data"],
                template="""
                На основе данных кандидата дай ОДНО предложение - моментальное впечатление:
                
                {candidate_data}
                
                Ответь ТОЛЬКО одним предложением в формате:
                "[Качество] кандидат: [главная характеристика], [краткий вердикт]"
                
                Примеры:
                - "Сильный кандидат: отличные технические навыки (CV 9/10), рекомендую к найму"
                - "Средний кандидат: базовые знания с пробелами (CV 6/10), нужна оценка мотивации"
                - "Слабый кандидат: недостаточно опыта для Senior роли, рассмотреть Junior"
                
                БЕЗ ДОПОЛНИТЕЛЬНЫХ ОБЪЯСНЕНИЙ. ТОЛЬКО ОДНО ПРЕДЛОЖЕНИЕ.
                """
            )
            
            formatted_data = self._format_candidate_data(candidate_data)
            chain = quick_prompt | self.llm | StrOutputParser()
            
            result = chain.invoke({"candidate_data": formatted_data})
            return result.strip()
            
        except Exception as e:
            return f"❌ Ошибка анализа: {str(e)}"
    
    def _extract_json_from_response(self, response: str) -> Dict[str, Any]:
        """Извлекает JSON из ответа LLM, даже если он в markdown блоке"""
        import re
        
        # Убираем лишние пробелы и переносы строк
        response = response.strip()
        
        # Пытаемся найти JSON в markdown блоке
        json_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
        match = re.search(json_pattern, response, re.DOTALL)
        
        if match:
            json_str = match.group(1)
        else:
            # Если нет markdown блока, пробуем найти JSON в тексте
            json_pattern = r'(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})'
            match = re.search(json_pattern, response, re.DOTALL)
            if match:
                json_str = match.group(1)
            else:
                json_str = response
        
        # Парсим JSON
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # Если все еще не получается, пытаемся очистить от лишних символов
            cleaned = re.sub(r'[^\{\}"\[\]:,\s\w\-\.\/]', '', json_str)
            return json.loads(cleaned)


class PatternAnalyzer:
    """Анализатор паттернов в HR данных (для будущих версий)"""
    
    def __init__(self):
        self.llm = None  # Будет реализовано в v2.0
    
    def analyze_hiring_patterns(self, candidates_data: list) -> Dict[str, Any]:
        """Анализирует паттерны найма для улучшения процесса"""
        
        # TODO: v2.0 функциональность
        # - Корреляция между оценкой CV и результатами интервью
        # - Успешность кандидатов по источникам  
        # - Временные тренды в качестве кандидатов
        # - Генерация рекомендаций для HR процесса
        
        return {"message": "Функция будет доступна в v2.0"}
