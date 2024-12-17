# handlers/voice_handler.py

import os
import uuid
from telegram import Update
from telegram.ext import ContextTypes
from utils.logger import get_logger
from processing import process_audio_initial, process_audio_improved
from config import WORKING_DIR
from handlers.reference_handler import receive_reference_audio  # Импортируем обработчик референсного аудио

logger = get_logger()

async def voice_or_audio_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик сообщений, содержащих голосовые или аудио файлы.
    Решает, обрабатывать ли сообщение как референсное аудио или как обычное голосовое сообщение.
    """
    if context.user_data.get('awaiting_reference_audio'):
        # Обрабатываем сообщение как референсное аудио
        await receive_reference_audio(update, context)
    else:
        # Обрабатываем сообщение как голосовое для распознавания речи
        await handle_voice_message(update, context)

async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает голосовые или аудио сообщения:
    - Скачивает аудиофайл
    - Распознаёт речь с помощью маленькой модели
    - Отправляет транскрипцию пользователю
    - Распознаёт речь с помощью большой модели
    - Обновляет сообщение с улучшенной транскрипцией и добавляет кнопки
    """
    try:
        # Получаем голосовое сообщение или аудио
        voice = update.message.voice or update.message.audio

        if not voice:
            await update.message.reply_text("Пожалуйста, отправьте голосовое сообщение или аудиофайл.")
            return

        # Скачиваем файл голосового сообщения
        file = await context.bot.get_file(voice.file_id)
        file_extension = file.file_path.split('.')[-1]
        unique_id = uuid.uuid4()
        file_path = os.path.join(WORKING_DIR, f'voice_{update.effective_user.id}_{unique_id}.{file_extension}')
        await file.download_to_drive(custom_path=file_path)
        logger.info(f"Скачан файл: {file_path}")

        # Обрабатываем аудио файл с маленькой моделью
        initial_output = process_audio_initial(file_path)

        if initial_output is None:
            await update.message.reply_text("Произошла ошибка при обработке аудио.")
            return

        # Отправляем первичную транскрипцию пользователю
        sent_message = await update.message.reply_text(initial_output)
        logger.info("Первичная транскрипция отправлена пользователю.")

        # Сохраняем идентификаторы сообщения и чата в контексте пользователя
        context.user_data['chat_id'] = update.effective_chat.id
        context.user_data['message_id'] = sent_message.message_id

        # Обрабатываем аудио файл с большой моделью
        improved_output = process_audio_improved(file_path)

        if improved_output is None:
            await context.bot.edit_message_text(
                chat_id=context.user_data['chat_id'],
                message_id=context.user_data['message_id'],
                text="Произошла ошибка при улучшенной обработке аудио."
            )
            return

        # Кнопки
        keyboard = [
            [
                InlineKeyboardButton("Редактировать текст", callback_data='edit_text'),
                InlineKeyboardButton("Синтезировать речь", callback_data='synthesize_speech'),
            ],
            [
                InlineKeyboardButton("Настройки синтеза", callback_data='synthesis_settings'),
                InlineKeyboardButton("Загрузить референсное аудио", callback_data='upload_reference'),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Обновляем сообщение с улучшенной транскрипцией и добавляем кнопки
        await context.bot.edit_message_text(
            chat_id=context.user_data['chat_id'],
            message_id=context.user_data['message_id'],
            text=improved_output,
            reply_markup=reply_markup
        )
        logger.info("Сообщение обновлено с улучшенной транскрипцией.")

        # Сохраняем улучшенный текст в контексте пользователя
        context.user_data['transcription'] = improved_output

    except Exception as e:
        logger.error(f"Произошла ошибка: {str(e)}")
        await update.message.reply_text(f"Произошла ошибка: {str(e)}")
