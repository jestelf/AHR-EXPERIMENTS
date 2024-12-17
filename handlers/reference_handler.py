# handlers/reference_handler.py

import os
import uuid
from telegram import Update
from telegram.ext import ContextTypes
from utils.logger import get_logger
from processing import process_reference_audio
from config import WORKING_DIR

logger = get_logger()

async def receive_reference_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает загрузку референсного аудио:
    - Скачивает аудиофайл
    - Обрабатывает его
    - Сохраняет путь к обработанному референсному аудио в контексте пользователя
    """
    # Проверяем, ожидает ли бот референсное аудио
    if not context.user_data.get('awaiting_reference_audio'):
        await update.message.reply_text("Пожалуйста, используйте кнопки для взаимодействия или отправьте голосовое сообщение.")
        return

    # Обработка референсного аудио
    audio_file = update.message.audio or update.message.voice
    if not audio_file:
        await update.message.reply_text("Пожалуйста, отправьте аудиофайл.")
        return

    try:
        # Скачиваем файл
        file = await context.bot.get_file(audio_file.file_id)
        file_extension = file.file_path.split('.')[-1]
        unique_id = uuid.uuid4()
        file_path = os.path.join(WORKING_DIR, f'reference_{update.effective_user.id}_{unique_id}.{file_extension}')
        await file.download_to_drive(custom_path=file_path)
        logger.info(f"Референсное аудио скачано: {file_path}")

        # Обрабатываем референсное аудио
        ref_audio_path = process_reference_audio(file_path)
        if ref_audio_path is not None:
            context.user_data['reference_audio'] = ref_audio_path
            await update.message.reply_text("Референсное аудио успешно загружено и обработано.")
        else:
            await update.message.reply_text("Произошла ошибка при обработке референсного аудио.")
    except Exception as e:
        logger.error(f"Ошибка при загрузке референсного аудио: {str(e)}")
        await update.message.reply_text("Произошла ошибка при загрузке аудио.")
    finally:
        context.user_data['awaiting_reference_audio'] = False
