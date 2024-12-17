# handlers/button_handler.py

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram import Update
from telegram.ext import ContextTypes
from utils.logger import get_logger
from handlers.synthesis_handler import add_synthesis_request
from handlers.reference_handler import receive_reference_audio
from processing import process_text_transcription
import asyncio

logger = get_logger()

async def handle_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает нажатия на кнопки:
    - Редактирование текста
    - Синтез речи
    - Настройки синтеза
    - Загрузка референсного аудио
    """
    query = update.callback_query
    await query.answer()

    if query.data == 'edit_text':
        # Запрашиваем новый текст у пользователя
        await query.edit_message_reply_markup(reply_markup=None)  # Убираем кнопки
        await query.message.reply_text("Пожалуйста, отправьте новый текст для замены.")
        context.user_data['awaiting_edit_text'] = True
    elif query.data == 'synthesize_speech':
        # Добавляем запрос в очередь
        transcription = context.user_data.get('transcription')
        if transcription is None:
            await query.message.reply_text("Нет текста для синтеза речи.")
            return

        # Проверяем, есть ли у пользователя референсное аудио
        reference_audio = context.user_data.get('reference_audio')

        # Добавляем запрос в очередь
        await add_synthesis_request(context, query, transcription, reference_audio)
    elif query.data == 'upload_reference':
        await query.message.reply_text("Пожалуйста, отправьте аудиофайл для использования в качестве референсного аудио.")
        context.user_data['awaiting_reference_audio'] = True
    elif query.data == 'synthesis_settings':
        # Предлагаем параметры для изменения
        keyboard = [
            [
                InlineKeyboardButton("Скорость (1.0)", callback_data='set_speed'),
            ],
            [
                InlineKeyboardButton("Коэффициент повторений (2.0)", callback_data='set_repetition_penalty'),
            ],
            [
                InlineKeyboardButton("Коэффициент длины (1.0)", callback_data='set_length_penalty'),
            ],
            [
                InlineKeyboardButton("Температура (0.7)", callback_data='set_temperature'),
            ],
            [
                InlineKeyboardButton("Назад", callback_data='back_to_main')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text("Настройки синтеза речи. Нажмите на параметр для изменения:", reply_markup=reply_markup)
    elif query.data.startswith('set_speed'):
        await set_speed(update, context)
    elif query.data.startswith('set_repetition_penalty'):
        await set_repetition_penalty(update, context)
    elif query.data.startswith('set_length_penalty'):
        await set_length_penalty(update, context)
    elif query.data.startswith('set_temperature'):
        await set_temperature(update, context)
    elif query.data == 'back_to_main':
        # Возвращаемся в главное меню
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
        await query.message.reply_text("Возвращаемся в главное меню.", reply_markup=reply_markup)

async def set_speed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает настройку скорости синтеза речи.
    """
    query = update.callback_query
    keyboard = [
        [
            InlineKeyboardButton("Медленная (0.8)", callback_data='speed_0.8'),
            InlineKeyboardButton("Нормальная (1.0)", callback_data='speed_1.0'),
        ],
        [
            InlineKeyboardButton("Быстрая (1.2)", callback_data='speed_1.2'),
            InlineKeyboardButton("Назад", callback_data='synthesis_settings')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text(
        "Скорость синтеза речи:\n"
        "Медленная (0.8) - медленнее стандартной скорости.\n"
        "Нормальная (1.0) - стандартная скорость.\n"
        "Быстрая (1.2) - быстрее стандартной скорости.",
        reply_markup=reply_markup
    )

async def set_repetition_penalty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает настройку коэффициента повторений.
    """
    query = update.callback_query
    keyboard = [
        [
            InlineKeyboardButton("Низкий (1.5)", callback_data='repetition_penalty_1.5'),
            InlineKeyboardButton("Средний (2.0)", callback_data='repetition_penalty_2.0'),
        ],
        [
            InlineKeyboardButton("Высокий (2.5)", callback_data='repetition_penalty_2.5'),
            InlineKeyboardButton("Назад", callback_data='synthesis_settings')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text(
        "Коэффициент повторений:\n"
        "Низкий (1.5) - меньше повторений.\n"
        "Средний (2.0) - стандартный коэффициент.\n"
        "Высокий (2.5) - больше повторений.",
        reply_markup=reply_markup
    )

async def set_length_penalty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает настройку коэффициента длины.
    """
    query = update.callback_query
    keyboard = [
        [
            InlineKeyboardButton("Низкий (0.8)", callback_data='length_penalty_0.8'),
            InlineKeyboardButton("Средний (1.0)", callback_data='length_penalty_1.0'),
        ],
        [
            InlineKeyboardButton("Высокий (1.2)", callback_data='length_penalty_1.2'),
            InlineKeyboardButton("Назад", callback_data='synthesis_settings')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text(
        "Коэффициент длины:\n"
        "Низкий (0.8) - короткие фразы.\n"
        "Средний (1.0) - стандартный коэффициент.\n"
        "Высокий (1.2) - длинные фразы.",
        reply_markup=reply_markup
    )

async def set_temperature(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает настройку температуры генерации речи.
    """
    query = update.callback_query
    keyboard = [
        [
            InlineKeyboardButton("Низкая (0.5)", callback_data='temperature_0.5'),
            InlineKeyboardButton("Средняя (0.7)", callback_data='temperature_0.7'),
        ],
        [
            InlineKeyboardButton("Высокая (0.9)", callback_data='temperature_0.9'),
            InlineKeyboardButton("Назад", callback_data='synthesis_settings')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text(
        "Температура генерации:\n"
        "Низкая (0.5) - более детерминированный и стабильный звук.\n"
        "Средняя (0.7) - сбалансированный звук.\n"
        "Высокая (0.9) - более разнообразный и креативный звук.",
        reply_markup=reply_markup
    )
