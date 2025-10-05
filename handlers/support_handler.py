"""
Обработчик службы заботы для отправки сообщений в группу поддержки.
"""

import logging

from aiogram import Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import BOT_TOKEN

logger = logging.getLogger(__name__)

# ID группы поддержки и темы
SUPPORT_GROUP_ID = -1003100527167  # ID группы (отрицательный для супергрупп)
SUPPORT_TOPIC_ID = 8  # ID темы в группе

# Создаем бота для отправки сообщений
bot = Bot(token=BOT_TOKEN)


def escape_markdown(text: str) -> str:
    """Экранирует специальные символы для Markdown"""
    return (text.replace('*', '\\*')
                .replace('_', '\\_')
                .replace('[', '\\[')
                .replace(']', '\\]')
                .replace('`', '\\`'))


class SupportForm(StatesGroup):
    waiting_for_message = State()


async def handle_support_message(message: Message, state: FSMContext):
    """
    Обработчик сообщений для службы поддержки.
    Пользователь может отправить текстовое сообщение или прикрепить файл.
    """
    user = message.from_user
    if not user:
        await message.answer("❌ Ошибка: пользователь не найден")
        return
    
    # Формируем информацию о пользователе
    user_info = f"👤 **Пользователь:** @{user.username or 'без username'}\n"
    user_info += f"🆔 **ID:** {user.id}\n"
    if user.first_name:
        user_info += f"📝 **Имя:** {user.first_name}"
        if user.last_name:
            user_info += f" {user.last_name}"
        user_info += "\n"
    
    # Формируем сообщение для группы поддержки
    support_message = f"🆘 **Новое обращение в службу поддержки**\n\n{user_info}\n"
    
    try:
        # Если есть текст
        if message.text:
            escaped_text = escape_markdown(message.text)
            support_message += f"💬 **Сообщение:**\n{escaped_text}"
        
        # Если есть файл/фото/документ
        if message.photo:
            support_message += "\n📷 **Прикреплено фото**"
            # Отправляем сообщение с текстом
            await bot.send_message(
                chat_id=SUPPORT_GROUP_ID,
                message_thread_id=SUPPORT_TOPIC_ID,
                text=support_message,
                parse_mode="Markdown"
            )
            # Отправляем фото отдельно
            await bot.send_photo(
                chat_id=SUPPORT_GROUP_ID,
                message_thread_id=SUPPORT_TOPIC_ID,
                photo=message.photo[-1].file_id,
                caption=f"📷 Фото от пользователя {user.id}"
            )
            
        elif message.document:
            doc_name = message.document.file_name or 'без названия'
            support_message += f"\n📄 **Прикреплен документ:** {doc_name}"
            # Отправляем сообщение с текстом
            await bot.send_message(
                chat_id=SUPPORT_GROUP_ID,
                message_thread_id=SUPPORT_TOPIC_ID,
                text=support_message,
                parse_mode="Markdown"
            )
            # Отправляем документ отдельно
            await bot.send_document(
                chat_id=SUPPORT_GROUP_ID,
                message_thread_id=SUPPORT_TOPIC_ID,
                document=message.document.file_id,
                caption=f"📄 Документ от пользователя {user.id}"
            )
            
        elif message.video:
            support_message += "\n🎥 **Прикреплено видео**"
            # Отправляем сообщение с текстом
            await bot.send_message(
                chat_id=SUPPORT_GROUP_ID,
                message_thread_id=SUPPORT_TOPIC_ID,
                text=support_message,
                parse_mode="Markdown"
            )
            # Отправляем видео отдельно
            await bot.send_video(
                chat_id=SUPPORT_GROUP_ID,
                message_thread_id=SUPPORT_TOPIC_ID,
                video=message.video.file_id,
                caption=f"🎥 Видео от пользователя {user.id}"
            )
            
        elif message.voice:
            support_message += "\n🎤 **Прикреплено голосовое сообщение**"
            # Отправляем сообщение с текстом
            await bot.send_message(
                chat_id=SUPPORT_GROUP_ID,
                message_thread_id=SUPPORT_TOPIC_ID,
                text=support_message,
                parse_mode="Markdown"
            )
            # Отправляем голосовое сообщение отдельно
            await bot.send_voice(
                chat_id=SUPPORT_GROUP_ID,
                message_thread_id=SUPPORT_TOPIC_ID,
                voice=message.voice.file_id,
                caption=f"🎤 Голосовое сообщение от пользователя {user.id}"
            )
            
        else:
            # Только текст
            await bot.send_message(
                chat_id=SUPPORT_GROUP_ID,
                message_thread_id=SUPPORT_TOPIC_ID,
                text=support_message,
                parse_mode="Markdown"
            )
        
        # Отправляем подтверждение пользователю
        await message.answer(
            "✅ **Сообщение отправлено в службу поддержки!**\n\n"
            "Мы получили ваше обращение и ответим в течение 24 часов.\n\n"
            "Для быстрой помощи:\n"
            "📧 Email: support@astro-bot.ru\n"
            "💬 Telegram: @astro_support",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🏠 Главное меню",
                            callback_data="back_to_menu"
                        )
                    ]
                ]
            ),
            parse_mode="Markdown"
        )
        
        # Сбрасываем состояние
        await state.clear()
        
        logger.info(f"Сообщение поддержки отправлено от пользователя {user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения в поддержку от пользователя {user.id}: {e}")
        await message.answer(
            "❌ Произошла ошибка при отправке сообщения в службу поддержки.\n\n"
            "Попробуйте позже или обратитесь напрямую:\n"
            "📧 Email: support@astro-bot.ru\n"
            "💬 Telegram: @astro_support"
        )


async def start_support_conversation(message: Message, state: FSMContext):
    """
    Начинает диалог с службой поддержки.
    """
    try:
        await state.set_state(SupportForm.waiting_for_message)
        logger.info("Support conversation started successfully")
        
        await message.answer(
            "🆘 **Служба заботы**\n\n"
            "Опишите вашу проблему или задайте вопрос.\n"
            "Вы можете:\n"
            "• Написать текстовое сообщение\n"
            "• Прикрепить фото или скриншот\n"
            "• Отправить документ\n"
            "• Записать голосовое сообщение\n\n"
            "Ваше сообщение будет отправлено в службу поддержки, "
            "и мы ответим в течение 24 часов.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="❌ Отмена",
                            callback_data="cancel_support"
                        )
                    ]
                ]
            ),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error in start_support_conversation: {e}")
        await message.answer(
            "❌ Произошла ошибка при отправке сообщения в службу поддержки.\n\n"
            "Попробуйте позже или обратитесь напрямую:\n"
            "📧 Email: support@astro-bot.ru\n"
            "💬 Telegram: @astro_support"
        )


async def cancel_support(message: Message, state: FSMContext):
    """
    Отменяет отправку сообщения в поддержку.
    """
    await state.clear()
    
    await message.answer(
        "❌ Отправка сообщения в службу поддержки отменена.\n\n"
        "Если у вас есть вопросы, вы всегда можете обратиться:\n"
        "📧 Email: support@astro-bot.ru\n"
        "💬 Telegram: @astro_support"
    )
