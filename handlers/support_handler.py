"""
НОВЫЙ обработчик службы заботы для отправки сообщений в группу поддержки.
Простой и надёжный код без лишних сложностей.
"""

import logging

from aiogram import Bot
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import BOT_TOKEN

logger = logging.getLogger(__name__)

# ID группы поддержки и темы
SUPPORT_GROUP_ID = -1003100527167  # ID группы (отрицательный для супергрупп)
SUPPORT_TOPIC_ID = 8  # ID темы в группе

# Создаем бота для отправки сообщений
bot = Bot(token=BOT_TOKEN)


class SupportForm(StatesGroup):
    waiting_for_message = State()


async def handle_support_message(message: Message, state: FSMContext):
    """
    НОВЫЙ простой обработчик сообщений для службы поддержки.
    """
    logger.info("=== SUPPORT MESSAGE HANDLER STARTED ===")
    
    try:
        user = message.from_user
        if not user:
            logger.error("User not found in message")
            await message.answer("Ошибка: пользователь не найден")
            return
        
        logger.info(f"Processing support message from user {user.id}")
        
        # Простое сообщение БЕЗ Markdown
        support_text = "🆘 НОВОЕ ОБРАЩЕНИЕ В ПОДДЕРЖКУ\n\n"
        support_text += f"Пользователь: @{user.username or 'без username'}\n"
        support_text += f"ID: {user.id}\n"
        
        if user.first_name:
            name = user.first_name
            if user.last_name:
                name += f" {user.last_name}"
            support_text += f"Имя: {name}\n"
        
        if message.text:
            support_text += f"\nСООБЩЕНИЕ:\n{message.text}"
        
        # Отправляем в группу БЕЗ parse_mode
        logger.info(f"Sending message to group {SUPPORT_GROUP_ID}")
        await bot.send_message(
            chat_id=SUPPORT_GROUP_ID,
            message_thread_id=SUPPORT_TOPIC_ID,
            text=support_text
        )
        logger.info("Message sent to support group successfully")
        
        # Если есть медиа - отправляем отдельно
        if message.photo:
            await bot.send_photo(
                chat_id=SUPPORT_GROUP_ID,
                message_thread_id=SUPPORT_TOPIC_ID,
                photo=message.photo[-1].file_id,
                caption=f"Фото от пользователя {user.id}"
            )
        
        # Отвечаем пользователю
        await message.answer(
            "💫 Принято, спасибо за запрос!\n"
            "Вернусь с ответом в ближайшее время 🐈‍⬛",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🪐 Купить разборы планет",
                            callback_data="buy_analysis"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🔥 Персональные прогнозы",
                            callback_data="personal_forecasts"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🏠 Главное меню",
                            callback_data="back_to_menu"
                        )
                    ]
                ]
            )
        )
        
        # Сбрасываем состояние
        await state.clear()
        logger.info("Support message handling completed successfully")
        
    except Exception as e:
        logger.error(f"ERROR in handle_support_message: {e}")
        await message.answer(
            "❌ Произошла ошибка при отправке сообщения в службу поддержки.\n\n"
            "Попробуйте позже или обратитесь напрямую:\n"
            "📧 Email: support@astro-bot.ru\n"
            "💬 Telegram: @astro_support"
        )


async def start_support_conversation(message: Message, state: FSMContext):
    """
    НОВАЯ простая функция для начала диалога с поддержкой.
    """
    logger.info("=== START SUPPORT CONVERSATION ===")
    
    try:
        logger.info("Setting support state...")
        await state.set_state(SupportForm.waiting_for_message)
        
        logger.info("Sending support message to user...")
        await message.answer(
            "С удовольствием ответим на любые вопросы 🪄\n"
            "👇🏼 Опиши ситуацию <b>сообщением прямо в этот чат</b>",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="↩️ Вернуться в главное меню",
                            callback_data="back_to_menu"
                        )
                    ]
                ]
            ),
            parse_mode="HTML"
        )
        
        logger.info("Support conversation started successfully!")
        
    except Exception as e:
        logger.error(f"ERROR in start_support_conversation: {e}")
        await message.answer(
            "❌ Произошла ошибка.\n\n"
            "Попробуйте позже или обратитесь напрямую:\n"
            "📧 Email: support@astro-bot.ru\n"
            "💬 Telegram: @astro_support"
        )


async def cancel_support(callback_query: CallbackQuery, state: FSMContext):
    """
    НОВАЯ простая функция для отмены поддержки.
    """
    logger.info("=== CANCEL SUPPORT ===")
    
    try:
        logger.info("Clearing state...")
        await state.clear()
        
        logger.info("Updating message...")
        if callback_query.message:
            await callback_query.message.edit_text(
                "❌ Обращение в службу поддержки отменено.",
                reply_markup=None
            )
        
        logger.info("Answering callback...")
        await callback_query.answer()
        
        logger.info("Support cancelled successfully!")
        
    except Exception as e:
        logger.error(f"ERROR in cancel_support: {e}")
        await callback_query.answer("❌ Ошибка при отмене.", show_alert=True)
