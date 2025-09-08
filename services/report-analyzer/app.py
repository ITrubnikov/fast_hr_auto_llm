import streamlit as st
import asyncio
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import datetime
import uuid
from report_generator import HRReportDatabase, ReportAnalyzer, CandidateReport
from llm_insights import CandidateInsightGenerator
from typing import Optional, List, Dict, Any
import json


class StreamlitReportApp:
    """Streamlit приложение для генерации отчетов о кандидатах"""
    
    def __init__(self):
        self.db = HRReportDatabase()
        self.analyzer = ReportAnalyzer()
        self.insights_generator = CandidateInsightGenerator()
        
        # Настройка страницы
        st.set_page_config(
            page_title="HR Analytics | Отчеты о кандидатах",
            page_icon="📊",
            layout="wide",
            initial_sidebar_state="expanded"
        )
        
        # Инициализация session state
        if 'report_data' not in st.session_state:
            st.session_state.report_data = None
        if 'candidates_list' not in st.session_state:
            st.session_state.candidates_list = []
        if 'ai_insights' not in st.session_state:
            st.session_state.ai_insights = None
        if 'ai_summary' not in st.session_state:
            st.session_state.ai_summary = None
    
    def render_header(self):
        """Отрисовка заголовка приложения"""
        st.markdown("""
        <div style="background: linear-gradient(90deg, #667eea 0%, #764ba2 100%); 
                    padding: 20px; border-radius: 10px; margin-bottom: 30px;">
            <h1 style="color: white; text-align: center; margin: 0;">
                📊 HR Analytics - Отчеты о кандидатах
            </h1>
            <p style="color: white; text-align: center; margin: 10px 0 0 0; opacity: 0.9;">
                Блок 4: Финальный анализ и отчетность по кандидатам
            </p>
        </div>
        """, unsafe_allow_html=True)
    
    def render_sidebar(self):
        """Отрисовка боковой панели с поиском"""
        st.sidebar.markdown("## 🔍 Поиск кандидата")
        
        # Поле ввода ID кандидата
        candidate_id = st.sidebar.text_input(
            "ID кандидата:",
            placeholder="cv_a8f9e2b1c4d7",
            help="Введите уникальный ID кандидата для получения отчета"
        )
        
        # Кнопка поиска
        if st.sidebar.button("🔍 Найти кандидата", type="primary"):
            if candidate_id and candidate_id.strip():
                # Загружаем данные о кандидате
                report = asyncio.run(self.db.get_candidate_report(candidate_id.strip()))
                st.session_state.report_data = report
                # Сбрасываем AI инсайты при новом поиске
                st.session_state.ai_insights = None
                st.session_state.ai_summary = None
                
                if not report:
                    st.sidebar.error(f"❌ Кандидат с ID '{candidate_id}' не найден")
                else:
                    st.sidebar.success("✅ Кандидат найден!")
            else:
                st.sidebar.error("❌ Введите ID кандидата")
        
        st.sidebar.markdown("---")
        
        # Список последних кандидатов
        if st.sidebar.button("📋 Показать всех кандидатов"):
            candidates = asyncio.run(self.db.get_candidates_list())
            st.session_state.candidates_list = candidates
        
        # Отображаем список кандидатов если есть
        if st.session_state.candidates_list:
            st.sidebar.markdown("### 👥 Последние кандидаты")
            for candidate in st.session_state.candidates_list[:10]:
                status_emoji = {
                    'completed': '✅',
                    'interviewed': '🎤',
                    'scheduled': '📅',
                    'analyzed': '📄',
                    'new': '🆕'
                }.get(candidate['status'], '❓')
                
                if st.sidebar.button(
                    f"{status_emoji} {candidate['candidate_name'][:20]}",
                    key=f"candidate_{candidate['candidate_id']}"
                ):
                    report = asyncio.run(self.db.get_candidate_report(candidate['candidate_id']))
                    st.session_state.report_data = report
                    # Сбрасываем AI инсайты при выборе из списка
                    st.session_state.ai_insights = None
                    st.session_state.ai_summary = None
    
    def render_progress_chart(self, status_data: Dict[str, Any]) -> go.Figure:
        """Создает круговую диаграмму прогресса"""
        completed = status_data['completed_stages']
        total = status_data['total_stages']
        remaining = total - completed
        
        fig = go.Figure(data=[go.Pie(
            labels=['Завершено', 'Осталось'],
            values=[completed, remaining],
            hole=0.6,
            marker_colors=['#28a745', '#e9ecef'],
            showlegend=False,
            textinfo='none'
        )])
        
        fig.add_annotation(
            text=f"{status_data['progress_percent']:.0f}%<br><span style='font-size: 14px;'>завершено</span>",
            x=0.5, y=0.5,
            font_size=24,
            showarrow=False
        )
        
        fig.update_layout(
            title="Прогресс обработки",
            height=200,
            margin=dict(t=40, b=0, l=0, r=0)
        )
        
        return fig
    
    def render_scores_chart(self, rating_data: Dict[str, Any]) -> go.Figure:
        """Создает диаграмму оценок"""
        scores = []
        labels = []
        colors = []
        
        if rating_data['cv_score'] is not None:
            scores.append(rating_data['cv_score'])
            labels.append('Анализ CV')
            colors.append('#ff7f0e')
        
        if rating_data['interview_score'] is not None:
            scores.append(rating_data['interview_score'])
            labels.append('Интервью')
            colors.append('#2ca02c')
        
        if rating_data['final_score'] is not None:
            scores.append(rating_data['final_score'])
            labels.append('Итоговая оценка')
            colors.append('#d62728')
        
        if not scores:
            return None
        
        fig = go.Figure(data=[
            go.Bar(x=labels, y=scores, marker_color=colors)
        ])
        
        fig.update_layout(
            title="Оценки по этапам",
            yaxis_title="Балл (из 10)",
            yaxis=dict(range=[0, 10]),
            height=300,
            showlegend=False
        )
        
        return fig
    
    def render_timeline(self, report: CandidateReport) -> go.Figure:
        """Создает временную шкалу процесса"""
        events = []
        
        # CV Analysis
        if report.cv_score is not None:
            events.append({
                'stage': 'Анализ CV',
                'date': datetime.now(),  # Используем текущую дату как заглушку
                'status': 'completed',
                'score': report.cv_score
            })
        
        # Interview Scheduled
        if report.interview_scheduled:
            events.append({
                'stage': 'Интервью запланировано',
                'date': report.interview_date or datetime.now(),
                'status': 'completed' if report.interview_completed else 'pending',
                'score': None
            })
        
        # Interview Completed
        if report.interview_completed:
            events.append({
                'stage': 'Интервью проведено',
                'date': datetime.now(),
                'status': 'completed',
                'score': report.interview_score
            })
        
        # Final Decision
        if report.final_decision:
            events.append({
                'stage': 'Решение принято',
                'date': report.decision_date or datetime.now(),
                'status': 'completed',
                'score': report.overall_score
            })
        
        if not events:
            return None
        
        df = pd.DataFrame(events)
        
        fig = px.timeline(
            df,
            x_start='date',
            x_end='date',
            y='stage',
            color='status',
            title="Временная шкала процесса"
        )
        
        fig.update_layout(height=300)
        return fig
    
    def render_candidate_report(self, report: CandidateReport):
        """Отрисовка полного отчета о кандидате"""
        # Заголовок отчета
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                    padding: 25px; border-radius: 15px; margin-bottom: 30px; color: white;">
            <h2 style="margin: 0; font-size: 28px;">👤 {report.candidate_name}</h2>
            <p style="margin: 10px 0 0 0; opacity: 0.9;">
                🎯 {report.vacancy_title} | 🆔 {report.candidate_id}
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        # Получаем аналитические данные
        rating_data = self.analyzer.calculate_overall_rating(report)
        status_data = self.analyzer.get_process_status(report)
        
        # Основные метрики в колонках
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "Общий рейтинг",
                f"{rating_data['total_score']}/10",
                delta=rating_data['rating']
            )
        
        with col2:
            st.metric(
                "Прогресс",
                f"{status_data['completed_stages']}/{status_data['total_stages']}",
                delta=status_data['current_stage']
            )
        
        with col3:
            if report.cv_score:
                st.metric("Оценка CV", f"{report.cv_score}/10")
            else:
                st.metric("Оценка CV", "Не оценено")
        
        with col4:
            if report.interview_score:
                st.metric("Оценка интервью", f"{report.interview_score}/10")
            else:
                st.metric("Оценка интервью", "Не проведено")
        
        # Графики
        chart_col1, chart_col2 = st.columns(2)
        
        with chart_col1:
            # График прогресса
            progress_fig = self.render_progress_chart(status_data)
            st.plotly_chart(progress_fig, use_container_width=True)
        
        with chart_col2:
            # График оценок
            scores_fig = self.render_scores_chart(rating_data)
            if scores_fig:
                st.plotly_chart(scores_fig, use_container_width=True)
        
        # AI-анализ секция
        st.markdown("## 🧠 ИИ-анализ кандидата")
        
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            # Показываем краткое AI резюме если есть
            if st.session_state.ai_summary:
                st.markdown("### ⚡ Быстрое впечатление ИИ")
                if "Сильный кандидат" in st.session_state.ai_summary:
                    st.success(f"🎯 {st.session_state.ai_summary}")
                elif "Средний кандидат" in st.session_state.ai_summary:
                    st.warning(f"🤔 {st.session_state.ai_summary}")
                elif "Слабый кандидат" in st.session_state.ai_summary:
                    st.error(f"⚠️ {st.session_state.ai_summary}")
                else:
                    st.info(f"🤖 {st.session_state.ai_summary}")
            else:
                st.info("🤖 Нажмите кнопку для получения ИИ-анализа кандидата")
        
        with col2:
            if st.button("⚡ Быстрое впечатление", help="Моментальная оценка кандидата в одном предложении"):
                with st.spinner("⚡ Анализирую..."):
                    candidate_dict = {
                        'name': report.candidate_name,
                        'cv_score': report.cv_score,
                        'cv_reasoning': report.cv_reasoning,
                        'key_strengths': report.key_strengths or [],
                        'concerns': report.concerns or [],
                        'interview_score': report.interview_score,
                        'dialog_summary': report.dialog_summary,
                        'current_stage': status_data['current_stage']
                    }
                    st.session_state.ai_summary = self.insights_generator.generate_quick_summary(candidate_dict)
                    st.rerun()
        
        with col3:
            if st.button("📊 Детальный отчет", help="Полный профессиональный анализ с рекомендациями для руководства"):
                with st.spinner("🧠 Создаю отчет..."):
                    # Подробные данные интервью
                    interview_details = ""
                    if report.dialog_details:
                        interview_qa = []
                        for i, detail in enumerate(report.dialog_details[:5], 1):  # Берем первые 5 Q&A
                            qa = f"Q{i}: {detail.get('question', '')}\nA{i}: {detail.get('answer', '')}"
                            if detail.get('score'):
                                qa += f" (Оценка: {detail.get('score')}/10)"
                            if detail.get('comment'):
                                qa += f"\nКомментарий: {detail.get('comment')}"
                            interview_qa.append(qa)
                        interview_details = "\n\n".join(interview_qa)
                    
                    candidate_dict = {
                        'name': report.candidate_name,
                        'cv_score': report.cv_score,
                        'cv_reasoning': report.cv_reasoning,
                        'key_strengths': report.key_strengths or [],
                        'concerns': report.concerns or [],
                        'interview_score': report.interview_score,
                        'dialog_summary': report.dialog_summary,
                        'interview_details': interview_details,
                        'total_questions': report.total_questions,
                        'answered_questions': report.answered_questions,
                        'current_stage': status_data['current_stage'],
                        'final_decision': report.final_decision,
                        'decision_reason': report.decision_reason,
                        'overall_score': report.overall_score,
                        'salary_offer': report.salary_offer,
                        'interview_scheduled': report.interview_scheduled,
                        'interview_completed': report.interview_completed
                    }
                    st.session_state.ai_insights = self.insights_generator.generate_insights(
                        candidate_dict, 
                        report.vacancy_title
                    )
                    st.rerun()
        
        # Показываем детальный AI анализ если есть
        if st.session_state.ai_insights:
            insights = st.session_state.ai_insights
            
            # Основное резюме
            st.markdown("---")
            st.markdown("### 📋 Исполнительное резюме для руководства")
            summary_text = insights.get("summary", "Анализ не доступен")
            
            # Выделяем резюме в зависимости от тона
            if any(word in summary_text.lower() for word in ['превосходит', 'отличн', 'исключительн', 'рекомендую']):
                st.success(f"✅ {summary_text}")
            elif any(word in summary_text.lower() for word in ['средний', 'базовый', 'требует']):
                st.warning(f"🤔 {summary_text}")
            elif any(word in summary_text.lower() for word in ['не соответств', 'недостаточн', 'слабый']):
                st.error(f"❌ {summary_text}")
            else:
                st.info(f"📊 {summary_text}")
            
            # Колонки для сильных сторон и областей развития
            ai_col1, ai_col2 = st.columns(2)
            
            with ai_col1:
                st.markdown("**💪 ИИ: Сильные стороны**")
                for strength in insights.get("strengths", []):
                    st.success(f"✅ {strength}")
            
            with ai_col2:
                st.markdown("**📈 ИИ: Области развития**")
                for area in insights.get("development_areas", []):
                    st.warning(f"⚠️ {area}")
            
            # Рекомендации
            recommendation = insights.get("recommendation", "manual_review")
            confidence = insights.get("confidence", "средняя")
            salary = insights.get("salary_range", "Определите самостоятельно")
            
            st.markdown("### 🎯 ИИ-рекомендация")
            
            if recommendation == "hired":
                st.success(f"✅ **Рекомендация ИИ:** НАНЯТЬ ({confidence} уверенность)")
                st.info(f"💰 **Предлагаемая зарплата:** {salary}")
            elif recommendation == "rejected":
                st.error(f"❌ **Рекомендация ИИ:** ОТКЛОНИТЬ ({confidence} уверенность)")
            elif recommendation == "additional_interview":
                st.warning(f"🤔 **Рекомендация ИИ:** ДОПОЛНИТЕЛЬНОЕ ИНТЕРВЬЮ ({confidence} уверенность)")
            else:
                st.info(f"🔍 **Рекомендация ИИ:** РУЧНОЙ АНАЛИЗ ({confidence} уверенность)")
        
        st.markdown("---")
        
        # Детальная информация по этапам
        st.markdown("## 📋 Детальная информация")
        
        # Создаем табы для разных этапов
        if any([report.cv_score, report.interview_scheduled, report.interview_completed, report.final_decision]):
            tabs = []
            tab_names = []
            
            if report.cv_score is not None:
                tab_names.append("📄 Анализ CV")
            if report.interview_scheduled:
                tab_names.append("📅 Интервью")
            if report.interview_completed:
                tab_names.append("🎤 Диалог")
            if report.final_decision:
                tab_names.append("✅ Решение")
            
            if tab_names:
                tabs = st.tabs(tab_names)
                
                tab_idx = 0
                
                # Таб анализа CV
                if report.cv_score is not None:
                    with tabs[tab_idx]:
                        col1, col2 = st.columns([2, 1])
                        
                        with col1:
                            st.markdown(f"**📊 Оценка:** {report.cv_score}/10")
                            
                            if report.cv_reasoning:
                                st.markdown("**💭 Обоснование:**")
                                st.info(report.cv_reasoning)
                            
                            if report.cv_summary:
                                st.markdown("**📝 Краткое резюме:**")
                                st.write(report.cv_summary)
                        
                        with col2:
                            if report.key_strengths:
                                st.markdown("**💪 Сильные стороны:**")
                                for strength in report.key_strengths:
                                    st.success(f"✅ {strength}")
                            
                            if report.concerns:
                                st.markdown("**⚠️ Замечания:**")
                                for concern in report.concerns:
                                    st.warning(f"⚠️ {concern}")
                        
                        if report.interview_questions:
                            st.markdown("**❓ Рекомендуемые вопросы:**")
                            for i, question in enumerate(report.interview_questions, 1):
                                st.markdown(f"{i}. {question}")
                    
                    tab_idx += 1
                
                # Таб интервью
                if report.interview_scheduled:
                    with tabs[tab_idx]:
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.markdown("**📅 Статус:** Запланировано")
                            if report.interview_date:
                                st.markdown(f"**🕐 Дата:** {report.interview_date.strftime('%d.%m.%Y %H:%M')}")
                            if report.interviewer_name:
                                st.markdown(f"**👤 Интервьюер:** {report.interviewer_name}")
                            if report.interview_format:
                                st.markdown(f"**🎥 Формат:** {report.interview_format}")
                        
                        with col2:
                            email_status = "✅ Отправлено" if report.email_sent else "❌ Не отправлено"
                            st.markdown(f"**📧 Email:** {email_status}")
                    
                    tab_idx += 1
                
                # Таб диалога
                if report.interview_completed:
                    with tabs[tab_idx]:
                        col1, col2 = st.columns([2, 1])
                        
                        with col1:
                            st.markdown(f"**📊 Оценка интервью:** {report.interview_score}/10")
                            
                            if report.dialog_summary:
                                st.markdown("**📝 Резюме интервью:**")
                                st.info(report.dialog_summary)
                            
                            # Детали диалога
                            if report.dialog_details:
                                st.markdown("**💬 Детали диалога:**")
                                for i, detail in enumerate(report.dialog_details, 1):
                                    with st.expander(f"Вопрос {i}: {detail.get('question', 'Неизвестный вопрос')[:50]}..."):
                                        st.markdown(f"**❓ Вопрос:** {detail.get('question', '')}")
                                        st.markdown(f"**💬 Ответ:** {detail.get('answer', 'Нет ответа')}")
                                        if detail.get('score'):
                                            st.markdown(f"**📊 Оценка:** {detail.get('score')}/10")
                                        if detail.get('comment'):
                                            st.markdown(f"**💭 Комментарий:** {detail.get('comment')}")
                        
                        with col2:
                            st.markdown(f"**📊 Статистика:**")
                            st.metric("Всего вопросов", report.total_questions)
                            st.metric("Отвечено", report.answered_questions)
                            
                            if report.total_questions > 0:
                                completion_rate = (report.answered_questions / report.total_questions) * 100
                                st.metric("Полнота ответов", f"{completion_rate:.0f}%")
                    
                    tab_idx += 1
                
                # Таб решения
                if report.final_decision:
                    with tabs[tab_idx]:
                        decision_color = {
                            'hired': 'success',
                            'rejected': 'error',
                            'on_hold': 'warning'
                        }.get(report.final_decision, 'info')
                        
                        decision_emoji = {
                            'hired': '✅',
                            'rejected': '❌',
                            'on_hold': '⏸️'
                        }.get(report.final_decision, '❓')
                        
                        decision_text = {
                            'hired': 'Принят',
                            'rejected': 'Отклонен',
                            'on_hold': 'На паузе'
                        }.get(report.final_decision, report.final_decision)
                        
                        col1, col2 = st.columns([2, 1])
                        
                        with col1:
                            if decision_color == 'success':
                                st.success(f"{decision_emoji} **Решение:** {decision_text}")
                            elif decision_color == 'error':
                                st.error(f"{decision_emoji} **Решение:** {decision_text}")
                            elif decision_color == 'warning':
                                st.warning(f"{decision_emoji} **Решение:** {decision_text}")
                            else:
                                st.info(f"{decision_emoji} **Решение:** {decision_text}")
                            
                            if report.decision_reason:
                                st.markdown("**💭 Обоснование:**")
                                st.info(report.decision_reason)
                            
                            if report.decided_by:
                                st.markdown(f"**👤 Принял решение:** {report.decided_by}")
                            
                            if report.decision_date:
                                st.markdown(f"**📅 Дата:** {report.decision_date.strftime('%d.%m.%Y %H:%M')}")
                        
                        with col2:
                            if report.overall_score:
                                st.metric("Итоговый балл", f"{report.overall_score}/10")
                            
                            if report.salary_offer and report.final_decision == 'hired':
                                st.metric("Предложение", f"{report.salary_offer:,} ₽")
        
        # Контактная информация
        st.markdown("## 📞 Контактная информация")
        contact_col1, contact_col2 = st.columns(2)
        
        with contact_col1:
            if report.email:
                st.markdown(f"**📧 Email:** {report.email}")
            st.markdown(f"**💬 Способ связи:** {report.preferred_contact}")
        
        with contact_col2:
            st.markdown(f"**📄 Файл CV:** {report.filename}")
            st.markdown(f"**🔗 Request ID:** `{report.request_id}`")
        
        # Экспорт отчета
        st.markdown("---")
        col1, col2, col3 = st.columns([1, 1, 2])
        
        with col1:
            if st.button("📊 Экспорт JSON"):
                report_json = {
                    'candidate_info': {
                        'id': report.candidate_id,
                        'name': report.candidate_name,
                        'email': report.email,
                        'contact': report.preferred_contact,
                        'vacancy': report.vacancy_title
                    },
                    'ratings': rating_data,
                    'process_status': status_data,
                    'generated_at': datetime.now().isoformat()
                }
                
                st.download_button(
                    "💾 Скачать JSON",
                    data=json.dumps(report_json, ensure_ascii=False, indent=2),
                    file_name=f"report_{report.candidate_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json"
                )
        
        with col2:
            if st.button("📝 Краткий отчет"):
                summary_report = f"""
# Отчет по кандидату: {report.candidate_name}

**Вакансия:** {report.vacancy_title}  
**ID кандидата:** {report.candidate_id}  
**Общий рейтинг:** {rating_data['total_score']}/10 - {rating_data['rating']}

## Прогресс процесса
{status_data['current_stage']} ({status_data['completed_stages']}/{status_data['total_stages']} этапов завершено)

## Оценки
- Анализ CV: {report.cv_score}/10 {'✅' if report.cv_score else '❌'}
- Интервью: {report.interview_score}/10 {'✅' if report.interview_score else '❌'}
- Итоговое решение: {report.final_decision or 'Не принято'}

**Сгенерировано:** {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
                """
                
                st.download_button(
                    "💾 Скачать MD",
                    data=summary_report,
                    file_name=f"brief_report_{report.candidate_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                    mime="text/markdown"
                )
    
    def render_no_data_state(self):
        """Отрисовка состояния когда нет данных"""
        st.markdown("""
        <div style="text-align: center; padding: 60px 20px; color: #6c757d;">
            <h2>🔍 Найти кандидата</h2>
            <p style="font-size: 18px; margin-bottom: 30px;">
                Введите ID кандидата в боковой панели для получения подробного отчета
            </p>
        </div>
        """, unsafe_allow_html=True)
    
    def run(self):
        """Запуск приложения"""
        self.render_header()
        self.render_sidebar()
        
        # Основной контент
        if st.session_state.report_data:
            self.render_candidate_report(st.session_state.report_data)
        else:
            self.render_no_data_state()
        
        # Подвал
        st.markdown("---")
        st.markdown("""
        <div style="text-align: center; color: #6c757d; padding: 20px;">
            <p>📊 HR Analytics Dashboard | Block 4: Final Report Generator</p>
            <p style="font-size: 12px;">Powered by Streamlit & PostgreSQL</p>
        </div>
        """, unsafe_allow_html=True)


def main():
    """Главная функция приложения"""
    app = StreamlitReportApp()
    app.run()


if __name__ == "__main__":
    main()
