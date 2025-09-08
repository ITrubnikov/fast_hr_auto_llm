import re
import json
import asyncio
from typing import Any, List, Optional, Dict
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage
from langchain.output_parsers import PydanticOutputParser


class CVAnalysis(BaseModel):
    candidate_name: str = Field(default="Имя не найдено", description="Имя кандидата")
    score: int = Field(description="Оценка кандидата по шкале от 1 до 10", ge=1, le=10)
    reasoning: str = Field(description="Подробное обоснование оценки")
    key_strengths: List[str] = Field(description="Список ключевых преимуществ кандидата")
    concerns: List[str] = Field(description="Список замечаний или недостатков")
    cv_summary: str = Field(description="Краткое резюме профиля кандидата")
    relevant_experience: str = Field(default="Опыт не указан", description="Релевантный опыт работы")
    education: str = Field(default="Образование не указано", description="Образование кандидата")
    technical_skills: List[str] = Field(description="Технические навыки")
    languages: List[str] = Field(description="Языки программирования или иностранные языки")
    interview_questions: List[str] = Field(description="Список вопросов для первичного собеседования с кандидатом")


class CVAnalyzer:
    def __init__(
        self,
        model_name: str = "google/gemma-3-27b-it:free",
        model_url: str = "https://openrouter.ai/api/v1",
        api_key_env: str = "OPENROUTER_API_KEY",
    ) -> None:
        # LangChain ChatOpenAI (langchain-openai) ожидает параметры base_url и api_key
        import os
        from dotenv import load_dotenv
        
        # Загружаем переменные окружения из .env файла
        load_dotenv("../../.env")

        raw_key = os.getenv(api_key_env) or os.getenv("OPENAI_API_KEY", "")
        api_key = (raw_key or "").strip().strip('"').strip("'")

        self.llm = ChatOpenAI(
            model=model_name,
            base_url=model_url,
            api_key=api_key or "test",
            temperature=0,
            max_tokens=8000,
        )

        self.parser = PydanticOutputParser(pydantic_object=CVAnalysis)
    
    def _create_analysis_prompt(self, cv_text: str, job_description: str) -> List[Any]:
        format_instructions = self.parser.get_format_instructions()
        
        system_prompt = f"""Ты - эксперт HR в области подбора персонала для крупной финансовой компании. 
Твоя задача - строго проанализировать резюме кандидата и оценить его соответствие требованиям вакансии.

КРИТЕРИИ СТРОГОЙ ОЦЕНКИ по шкале от 1 до 10:
- 1-2: Полностью не подходит (отсутствуют важные требования)
- 3-4: Очень слабое соответствие (есть базовые навыки, но много пробелов)
- 5-6: Минимальное соответствие (половина требований выполнена)
- 7: Хорошее соответствие (большинство требований выполнено)
- 8: Очень хорошее соответствие (почти все требования + некоторые плюсы)
- 9-10: Исключительное соответствие (все требования + значительные преимущества)

СТРОГИЕ ПРАВИЛА ОЦЕНКИ:
- Если кандидат НЕ соответствует КЛЮЧЕВЫМ техническим требованиям очень сильно занижай его баллы- максимум 2 балла
- Если отсутствует релевантный опыт работы (менее 70% требуемого) - максимум 4 баллов
- Если недостаточное образование для позиции - минус 1-2 балла
- Если отсутствуют обязательные сертификации - минус 1-3 балла
- Если стаж работы меньше требуемого - минус 1-2 балла
- Если кандидат работал меньше года на последнем или предпоследнем месте работы - минус 1-2 балла
- Если у кандидата были перерывы в работе более 6 месяцев - минус 1-2 балла
- Если кандидат параллельно работал в нескольких компаниях - минус 1 балл
- Если часовой пояс кандидата отличается от часового пояса вакансии более чем на 5 часов - минус 1 балл

Обрати особое внимание на:
1. Опыт работы в релевантных областях
2. Технические навыки и компетенции
3. Образование и сертификации
4. Опыт работы в финансовой или IT сфере (плюс)
5. Стаж работы
6. Знание языков программирования/технологий
7. Лидерские качества и управленческий опыт, опыт наставничества, менторинга
8. Знание иностранных языков
9. Опыт работы в крупных компаниях с хорошо выстроенными процессами (большой плюс): Ostrovok (Островок), 2Gis, РЖД, С7 (S7), Cian, Expedia, Купибилет, Суточно.ру, Онэлия, Airbnb, BlaBlaCar, Связной Трэвел, HRS, Аэроэкспресс, Google Travel, Trivago, Trip.com, Ozon.travel, UFS.ru, SimpleTrip, PoiSk.ru, Biletix, RoomGuru, emarket.rzd.ru, Booking.com, Ozon, Яндекс.Маркет, Wildberries, СберМегаМаркет, Megamarket (ex-Goods.ru), AliExpress Россия, Alibaba.com, Avito, Joom, Lamoda, Pandao, СДЭК, СДЭК.Маркет, Ситилинк, ВсеИнструменты.ру, Kaspi.kz, ПочтаМаркет, Книга.ру (book24.ru), Почта России, Goods.ru, Юлмарт, DNS-shop, Леруа Мерлен, ВкусВилл доставка, М.Видео – Эльдорадо, Детский Мир, O’KEY, SPAR, Rozetka.ua, Впрок (Перекрёсток онлайн), Озон Экспресс, OZON Fresh, Тинькофф, Сбер, Райффайзен, Альфа-Банк, ВТБ, Росбанк, Газпромбанк, Ак Барс Банк, Home Credit Bank, Совкомбанк, БКС Банк, Открытие (Банк Открытие), Ренессанс Кредит, Росгосстрах Банк, МКБ, УБРиР, СКБ-Банк, Промсвязьбанк, ЮниКредит банк, ЮMoney (бывшая Яндекс.Деньги), WebMoney, Банк Санкт-Петербург, МТС Банк, Рокетбанк (до 2020), СПБ Биржа, Московская Биржа, Qiwi, Почта-банк, Revolut, PayPal, Binance, Яндекс Банк, Monzo, N26, Wise, Росгосстрах Банк, Positive Technologies, Лаборатория Касперского, ABBYY, JetBrains, SberCloud, Лента, METRO, Ашан, Globus, X5 Retail Group, Магнит, ВкусВилл, Азбука Вкуса, М.Видео — Эльдорадо, DNS, Лемана Про, OBI, Детский мир, Красное & Белое, Fix Price, IKEA (до ухода из РФ), Утконос, Рив Гош, Зоозавр, 4 Лапы (4lapy.ru), Mothercare, O’KEY, SPAR Россия, Litres, Лабиринт, Bookmate, Издательство АСТ & ЭКСМО, Читай-город, Леруа Мерлен, ВсеИнструменты.ру, Gett/Яндекс Go, Delivery Club, Самокат, Ситимобил, InDrive, Окко, IVI, Кинопоиск HD, SberBox, Megogo, Netflix, Disney+, Spotify, Amazon Prime Video, Яндекс Еда, Яндекс Лавка, OZON Express, СберМаркет, Партия еды, Пятерочка доставка, МегаФон, МТС (оператор + банк), Beeline, Tele2, Yota, Funbox, Ростелеком, РОСЧАТ, СберМобайл, Тинькофф Мобайл, SimTelecom, TeloSIM / Yesim, Enforta, Netbynet, Дом.ру, Zebra Telecom, Aviasales, Gettrabster, Aeroclub, One two trip, BestDoctor, Bioniq, Профи, Яндекс.Путешествия, Level travel, Достависта, Tutu, Selectel



ГЕНЕРАЦИЯ ВОПРОСОВ ДЛЯ СОБЕСЕДОВАНИЯ:
Составь 5-8 персонализированных вопросов для первичного собеседования, основываясь на:
1. Пробелах в резюме (что нужно уточнить)
2. Ключевых технических компетенциях из требований
3. Релевантном опыте (детализация проектов)
4. Сложных или специфических требованиях вакансии
5. Мотивации и карьерных планах
6. Уточни организационные вопросы: размер желаемой и комфортной заработной платы, локацию кандидата, часовой пояс и готовность работать по часовому поясу вакансии
7. Уточни, подходит ли кандидату локация вакансии, график, формат работы (удаленка, гибрид, офис)


Примеры хороших вопросов:
- "Расскажи о своём последнем месте работы? Чем занимался? Какие задачи решал? Какие технологии использовал?"
- "Какой у вас опыт работы с технологией Y?"
- "Какой у тебя был основной стек?" 
- "Как вы решали задачу Z в предыдущих проектах?"
- "Как видишь свой дальнейший карьерный трек? Куда хотел бы развиваться?"
- "На какую зарплату сейчас ориентируешься?"
- "Почему так быстро ушел из компании N (если кандидат работал в компании менее года)?"
- "Заметила, что у тебя был длительный перерыв в работе, расскажи, чем занимался в это время? (если у кандидата был перерыв в работе больше 6 месяцев)"
- "Чего хочется от новой работы? Какие задачи интересны?"
- "Представим ситуацию, что у тебя несколько офферов. Как будешь выбирать, какой оффер принять?"
- "Расскажи, почему решил менять работу?"
- "Расскажи о кейсе, которым гордишься?"
- "Расскажи о ситуации, когда ты допустила ошибку? Как решал ситуацию? Какие выводы для себя сделал?"
- "Из какой локации планируешь работать?"
- "Подходит ли тебе наш тип оформления?"

{format_instructions}

ОТВЕТ ВОЗВРАЩАЙ СТРОГО В ВИДЕ ЧИСТОГО JSON БЕЗ КАКИХ-ЛИБО ПОЯСНЕНИЙ, ТЕКСТА ВОКРУГ ИЛИ КОДОВЫХ БЛОКОВ.

Описание вакансии:
{job_description}

---

Резюме кандидата:
{cv_text}

---

Проанализируй это резюме относительно требований вакансии и дай детальную оценку в указанном формате:"""

        return [
            HumanMessage(content=system_prompt)
        ]
    
    async def analyze_cv(self, cv_text: str, job_description: str) -> CVAnalysis:
        messages = self._create_analysis_prompt(cv_text, job_description)
        last_error: Optional[Exception] = None

        for attempt in range(3):
            try:
                response = await self.llm.ainvoke(messages)
                content: Optional[str] = getattr(response, "content", None)
                if not content or not isinstance(content, str) or not content.strip():
                    raise ValueError("Пустой ответ модели")

                analysis = self._parse_llm_content(content)
                analysis = self._complete_analysis(analysis, cv_text)
                return analysis
            except Exception as e:
                last_error = e
                # Небольшая экспоненциальная пауза перед повтором
                await asyncio.sleep(0.4 * (attempt + 1))

        # Fallback: конструируем минимально полезный ответ, чтобы не падать UI
        return self._fallback_analysis(cv_text=cv_text, job_description=job_description, error_message=str(last_error) if last_error else "unknown error")

    def _parse_llm_content(self, content: str) -> CVAnalysis:
        # 1) Пытаемся штатно распарсить
        try:
            return self.parser.parse(content)
        except Exception:
            pass

        # 2) Пробуем вытащить JSON-объект из текста
        try:
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1 and end > start:
                json_str = content[start : end + 1]
                data: Dict[str, Any] = json.loads(json_str)
                # Приводим поля к ожидаемым типам/дефолтам
                normalized = {
                    "candidate_name": data.get("candidate_name") or "Имя не найдено",
                    "score": int(data.get("score", 5) or 5),
                    "reasoning": data.get("reasoning") or "Анализ недоступен",
                    "key_strengths": data.get("key_strengths") or [],
                    "concerns": data.get("concerns") or [],
                    "cv_summary": data.get("cv_summary") or "",
                    "relevant_experience": data.get("relevant_experience") or "Опыт не указан",
                    "education": data.get("education") or "Образование не указано",
                    "technical_skills": data.get("technical_skills") or [],
                    "languages": data.get("languages") or [],
                }
                return CVAnalysis.model_validate(normalized)
        except Exception:
            pass

        # 3) Не удалось – бросаем исключение, чтобы сработал внешний fallback
        raise ValueError("Не удалось распарсить ответ модели в формат CVAnalysis")

    def _fallback_analysis(self, cv_text: str, job_description: str, error_message: str) -> CVAnalysis:
        # Простой эвристический ответ, чтобы UI не падал
        name = self._extract_name_from_cv(cv_text)
        reasoning = (
            "Автоматический упрощённый разбор: не удалось корректно распарсить ответ модели. "
            f"Причина: {error_message}. Оценка выставлена эвристически."
        )
        return CVAnalysis(
            candidate_name=name,
            score=5,
            reasoning=reasoning,
            key_strengths=[],
            concerns=[],
            cv_summary="Анализ профиля кандидата",
            relevant_experience="Опыт работы не указан",
            education="Образование не указано",
            technical_skills=[],
            languages=[],
            interview_questions=[],
        )
    
    def _complete_analysis(self, analysis: CVAnalysis, cv_text: str) -> CVAnalysis:
        if not analysis.candidate_name or analysis.candidate_name == "Неизвестный кандидат":
            analysis.candidate_name = self._extract_name_from_cv(cv_text)
        
        if not isinstance(analysis.score, int) or analysis.score < 1 or analysis.score > 10:
            analysis.score = max(1, min(10, int(analysis.score)))
        
        if not analysis.cv_summary or analysis.cv_summary == "Не определено":
            analysis.cv_summary = "Анализ профиля кандидата"
        
        if not analysis.relevant_experience or analysis.relevant_experience == "Не определено":
            analysis.relevant_experience = "Опыт работы не указан"
        
        if not analysis.education or analysis.education == "Не определено":
            analysis.education = "Образование не указано"
        
        return analysis
    
    def _extract_name_from_cv(self, cv_text: str) -> str:
        lines = cv_text.split('\n')
        for line in lines:
            line = line.strip()
            if re.match(r'^[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?$', line):
                return line
        return "Имя не найдено"
    
    def create_summary_report(self, results: List[CVAnalysis], job_description: str) -> str:
        if not results:
            return "Нет результатов для анализа"
        
        sorted_results = sorted(results, key=lambda x: x.score, reverse=True)
        
        report = f"""
# Отчет по анализу кандидатов

## Статистика
- Всего кандидатов: {len(results)}
- Отличные кандидаты (8-10): {len([r for r in results if r.score >= 8])}
- Хорошие кандидаты (6-7): {len([r for r in results if 6 <= r.score < 8])}
- Удовлетворительные (4-5): {len([r for r in results if 4 <= r.score < 6])}
- Неподходящие (1-3): {len([r for r in results if r.score < 4])}

## Топ-3 кандидата

"""

        for i, result in enumerate(sorted_results[:3], 1):
            report += f"""
### {i}. {result.candidate_name} - {result.score}/10

**Ключевые преимущества:**
{chr(10).join([f"- {strength}" for strength in result.key_strengths])}

**Обоснование:** {result.reasoning}

---
"""
        
        return report