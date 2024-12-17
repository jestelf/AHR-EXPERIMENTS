import os
from telegram.ext import (
    ApplicationBuilder, MessageHandler, filters, ContextTypes,
    CallbackQueryHandler, ConversationHandler, CommandHandler
)
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
import logging
from dm1 import process_audio_initial, process_audio_improved

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Замените на токен вашего бота
TELEGRAM_TOKEN = ''  # Замените на реальный токен

# Рабочая директория
WORKING_DIR = r'D:\prdja'

# Определяем этапы разговора
EDIT_TEXT = range(1)

async def voice_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Получаем голосовое сообщение
        voice = update.message.voice

        # Скачиваем файл голосового сообщения
        file = await context.bot.get_file(voice.file_id)
        file_path = os.path.join(WORKING_DIR, 'voice.ogg')
        await file.download_to_drive(custom_path=file_path)
        logger.info(f"Скачан файл: {file_path}")

        # Обрабатываем аудио файл с маленькой моделью
        initial_output = process_audio_initial(file_path)

        if initial_output is None:
            await update.message.reply_text("Произошла ошибка при обработке аудио.")
            return

        # Отправляем первичную транскрипцию пользователю
        initial_message = "Первичная транскрипция:\n"
        initial_message += initial_output

        sent_message = await update.message.reply_text(initial_message)
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
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Обновляем сообщение с улучшенной транскрипцией и добавляем кнопки
        improved_message = "Улучшенная транскрипция:\n"
        improved_message += improved_output

        await context.bot.edit_message_text(
            chat_id=context.user_data['chat_id'],
            message_id=context.user_data['message_id'],
            text=improved_message,
            reply_markup=reply_markup
        )
        logger.info("Сообщение обновлено с улучшенной транскрипцией.")

        # Сохраняем улучшенный текст в контексте пользователя
        context.user_data['transcription'] = improved_output

    except Exception as e:
        logger.error(f"Произошла ошибка: {str(e)}")
        await update.message.reply_text(f"Произошла ошибка: {str(e)}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'edit_text':
        # Запрашиваем новый текст у пользователя
        await query.edit_message_reply_markup(reply_markup=None)  # Убираем кнопки
        await query.message.reply_text("Пожалуйста, отправьте новый текст для замены.")
        return EDIT_TEXT
    elif query.data == 'synthesize_speech':
        # Заглушка для синтеза речи
        await query.message.reply_text("Синтез речи пока не реализован.")
        logger.info("Синтез речи вызван (заглушка).")

async def edit_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_text = update.message.text
    chat_id = context.user_data.get('chat_id')
    message_id = context.user_data.get('message_id')

    if not chat_id or not message_id:
        await update.message.reply_text("Не удалось найти сообщение для редактирования.")
        return ConversationHandler.END

    # Обновляем сообщение с новым текстом и кнопками
    keyboard = [
        [
            InlineKeyboardButton("Редактировать текст", callback_data='edit_text'),
            InlineKeyboardButton("Синтезировать речь", callback_data='synthesize_speech'),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=new_text,
        reply_markup=reply_markup
    )
    logger.info("Сообщение обновлено с новым текстом от пользователя.")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Редактирование отменено.")
    return ConversationHandler.END

def main():
    # Создаём приложение бота
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Обрабатываем голосовые сообщения
    voice_handler = MessageHandler(filters.VOICE, voice_message_handler)

    # Обработчик кнопок
    callback_query_handler = CallbackQueryHandler(button_handler)  # Изменено имя переменной

    # Обработчик для редактирования текста (ConversationHandler)
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, edit_text)],
        states={
            EDIT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_text)]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        allow_reentry=True
    )

    application.add_handler(voice_handler)
    application.add_handler(callback_query_handler)  # Изменено имя переменной
    application.add_handler(conv_handler)

    # Запускаем бота
    logger.info("Бот запущен и ожидает сообщений...")
    application.run_polling()

if __name__ == '__main__':
    main()
