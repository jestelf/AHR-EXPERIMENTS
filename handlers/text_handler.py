# handlers/text_handler.py

from telegram import Update
from telegram.ext import ContextTypes
from utils.logger import get_logger
from processing import process_text_transcription
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = get_logger()

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает текстовые сообщения:
    - Предобрабатывает текст
    - Отправляет транскрипцию пользователю
    - Добавляет кнопки для дальнейших действий
    """
    if context.user_data.get('awaiting_edit_text'):
        await receive_new_text(update, context)
    else:
        # Обработка обычного текстового сообщения как новой транскрипции
        try:
            new_text = update.message.text.strip()
            if not new_text:
                await update.message.reply_text("Пожалуйста, отправьте непустое текстовое сообщение.")
                return

            # Предобработка текста: добавление пунктуации и капитализация
            punctuated_text = process_text_transcription(new_text)

            # Отправляем обработанный текст пользователю
            sent_message = await update.message.reply_text(punctuated_text)
            logger.info("Транскрипция из текстового сообщения отправлена пользователю.")

            # Сохраняем идентификаторы сообщения и чата в контексте пользователя
            context.user_data['chat_id'] = update.effective_chat.id
            context.user_data['message_id'] = sent_message.message_id

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

            # Обновляем сообщение с транскрипцией и добавляем кнопки
            await context.bot.edit_message_text(
                chat_id=context.user_data['chat_id'],
                message_id=context.user_data['message_id'],
                text=punctuated_text,
                reply_markup=reply_markup
            )
            logger.info("Сообщение обновлено с транскрипцией из текстового сообщения.")

            # Сохраняем транскрипцию
            context.user_data['transcription'] = punctuated_text

        except Exception as e:
            logger.error(f"Произошла ошибка при обработке текстового сообщения: {str(e)}")
            await update.message.reply_text(f"Произошла ошибка при обработке текста: {str(e)}")

async def receive_new_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает новый текст, отправленный пользователем для редактирования транскрипции.
    """
    new_text = update.message.text
    chat_id = context.user_data.get('chat_id')
    message_id = context.user_data.get('message_id')

    if not chat_id or not message_id:
        await update.message.reply_text("Не удалось найти сообщение для редактирования.")
        return

    # Предобработка нового текста: добавление пунктуации и капитализация
    punctuated_text = process_text_transcription(new_text)

    # Обновляем сообщение с новым текстом и кнопками
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

    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=punctuated_text,
        reply_markup=reply_markup
    )
    context.user_data['transcription'] = punctuated_text
    context.user_data['awaiting_edit_text'] = False
    logger.info("Сообщение обновлено с новым текстом от пользователя.")
