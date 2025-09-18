"""
Обработчики кнопок и callback-функций для бота.
"""

from .recommendations_handler import handle_get_recommendations
from .ask_question_handler import handle_ask_question

__all__ = [
    "handle_get_recommendations",
    "handle_ask_question"
]