import os
import asyncio
import uuid  # Импортируем модуль uuid
from telegram.ext import (
    ApplicationBuilder, MessageHandler, filters, ContextTypes,
    CallbackQueryHandler, CommandHandler
)
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
import logging
from dm2 import (
    process_audio_initial, process_audio_improved,
    process_reference_audio, synthesize_speech
)
from asyncio import Queue

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Замените на токен вашего бота
TELEGRAM_TOKEN = ''  # ⚠️ Убедитесь, что токен не доступен публично

# Рабочая директория
WORKING_DIR = r'D:\prdja'

# Определяем этапы разговора
EDIT_TEXT, SET_PARAMETER = range(2)

# Инициализируем очередь для синтеза
synthesis_queue = Queue()

async def voice_or_audio_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_reference_audio'):
        # Обрабатываем сообщение как референсное аудио
        await receive_reference_audio(update, context)
    else:
        # Обрабатываем сообщение как голосовое для распознавания речи
        await voice_message_handler(update, context)

async def voice_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'edit_text':
        # Запрашиваем новый текст у пользователя
        await query.edit_message_reply_markup(reply_markup=None)  # Убираем кнопки
        await query.message.reply_text("Пожалуйста, отправьте новый текст для замены.")
        context.user_data['awaiting_edit_text'] = True
    elif query.data == 'synthesize_speech':
        # Добавляем запрос в очередь
        user_id = query.from_user.id
        chat_id = query.message.chat_id
        transcription = context.user_data.get('transcription')
        if transcription is None:
            await query.message.reply_text("Нет текста для синтеза речи.")
            return

        # Проверяем, есть ли у пользователя референсное аудио
        reference_audio = context.user_data.get('reference_audio')

        # Генерируем уникальный ID для запроса
        request_id = uuid.uuid4()

        # Добавляем запрос в очередь
        await synthesis_queue.put({
            'request_id': str(request_id),
            'user_id': user_id,
            'chat_id': chat_id,
            'transcription': transcription,
            'reference_audio': reference_audio,
            'tts_settings': context.user_data.get('tts_settings', {})
        })

        position_in_queue = synthesis_queue.qsize()
        await query.message.reply_text(f"Ваш запрос добавлен в очередь на синтез речи. Позиция в очереди: {position_in_queue}")
        logger.info(f"Пользователь {user_id} добавлен в очередь на синтез речи с ID {request_id}.")

        # Запускаем обработку очереди, если она не запущена
        if not context.bot_data.get('synthesis_queue_running'):
            context.bot_data['synthesis_queue_running'] = True
            asyncio.create_task(process_synthesis_queue(context))
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
    elif query.data == 'set_speed':
        # Предлагаем варианты скорости
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
        await query.message.reply_text("Скорость синтеза речи:\nМедленная (0.8) - медленнее стандартной скорости.\nНормальная (1.0) - стандартная скорость.\nБыстрая (1.2) - быстрее стандартной скорости.", reply_markup=reply_markup)
    elif query.data.startswith('speed_'):
        try:
            speed = float(query.data.split('_')[1])
            context.user_data.setdefault('tts_settings', {})['speed'] = speed
            await query.message.reply_text(f"Скорость установлена на {speed}.")
            logger.info(f"Пользователь {query.from_user.id} установил скорость на {speed}.")
        except ValueError:
            await query.message.reply_text("Ошибка при установке скорости.")
    elif query.data == 'set_repetition_penalty':
        # Предлагаем варианты коэффициента повторений
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
        await query.message.reply_text("Коэффициент повторений:\nНизкий (1.5) - меньше повторений.\nСредний (2.0) - стандартный коэффициент.\nВысокий (2.5) - больше повторений.", reply_markup=reply_markup)
    elif query.data.startswith('repetition_penalty_'):
        try:
            repetition_penalty = float(query.data.split('_')[2])
            context.user_data.setdefault('tts_settings', {})['repetition_penalty'] = repetition_penalty
            await query.message.reply_text(f"Коэффициент повторений установлен на {repetition_penalty}.")
            logger.info(f"Пользователь {query.from_user.id} установил коэффициент повторений на {repetition_penalty}.")
        except ValueError:
            await query.message.reply_text("Ошибка при установке коэффициента повторений.")
    elif query.data == 'set_length_penalty':
        # Предлагаем варианты коэффициента длины
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
        await query.message.reply_text("Коэффициент длины:\nНизкий (0.8) - короткие фразы.\nСредний (1.0) - стандартный коэффициент.\nВысокий (1.2) - длинные фразы.", reply_markup=reply_markup)
    elif query.data.startswith('length_penalty_'):
        try:
            length_penalty = float(query.data.split('_')[2])
            context.user_data.setdefault('tts_settings', {})['length_penalty'] = length_penalty
            await query.message.reply_text(f"Коэффициент длины установлен на {length_penalty}.")
            logger.info(f"Пользователь {query.from_user.id} установил коэффициент длины на {length_penalty}.")
        except ValueError:
            await query.message.reply_text("Ошибка при установке коэффициента длины.")
    elif query.data == 'set_temperature':
        # Предлагаем варианты температуры
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
        await query.message.reply_text("Температура генерации:\nНизкая (0.5) - более детерминированный и стабильный звук.\nСредняя (0.7) - сбалансированный звук.\nВысокая (0.9) - более разнообразный и креативный звук.", reply_markup=reply_markup)
    elif query.data.startswith('temperature_'):
        try:
            temperature = float(query.data.split('_')[1])
            context.user_data.setdefault('tts_settings', {})['temperature'] = temperature
            await query.message.reply_text(f"Температура установлена на {temperature}.")
            logger.info(f"Пользователь {query.from_user.id} установил температуру на {temperature}.")
        except ValueError:
            await query.message.reply_text("Ошибка при установке температуры.")
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

async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_edit_text'):
        await receive_new_text(update, context)
    elif context.user_data.get('awaiting_parameter'):
        await receive_parameter_value(update, context)
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

            # Отправляем сообщение с кнопками
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

async def receive_parameter_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    param = context.user_data.get('awaiting_parameter')
    value = update.message.text
    try:
        value = float(value)
        if param == 'speed':
            context.user_data.setdefault('tts_settings', {})['speed'] = value
        elif param == 'repetition_penalty':
            context.user_data.setdefault('tts_settings', {})['repetition_penalty'] = value
        elif param == 'length_penalty':
            context.user_data.setdefault('tts_settings', {})['length_penalty'] = value
        elif param == 'temperature':
            context.user_data.setdefault('tts_settings', {})['temperature'] = value
        await update.message.reply_text(f"Параметр '{param}' установлен на {value}.")
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите числовое значение.")
    context.user_data['awaiting_parameter'] = None

async def receive_reference_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Действие отменено.")
    context.user_data.clear()

async def process_synthesis_queue(context: ContextTypes.DEFAULT_TYPE):
    while not synthesis_queue.empty():
        request = await synthesis_queue.get()
        user_id = request['user_id']
        chat_id = request['chat_id']
        transcription = request['transcription']
        reference_audio = request['reference_audio']
        tts_settings = request['tts_settings']

        # Информируем пользователя о начале синтеза
        await context.bot.send_message(chat_id=chat_id, text="Синтез речи начался, пожалуйста, подождите...")

        # Синтезируем три варианта речи с разными параметрами
        # Например, один с дефолтными параметрами, один с увеличенной скоростью, один с уменьшенной скоростью
        synthesis_variations = [
            {'speed': tts_settings.get('speed', 1.0), 'repetition_penalty': tts_settings.get('repetition_penalty', 2.0),
             'length_penalty': tts_settings.get('length_penalty', 1.0), 'temperature': tts_settings.get('temperature', 0.7)},
            {'speed': tts_settings.get('speed', 1.0) * 1.2, 'repetition_penalty': tts_settings.get('repetition_penalty', 2.0),
             'length_penalty': tts_settings.get('length_penalty', 1.0), 'temperature': tts_settings.get('temperature', 0.7)},
            {'speed': tts_settings.get('speed', 1.0) * 0.8, 'repetition_penalty': tts_settings.get('repetition_penalty', 2.0),
             'length_penalty': tts_settings.get('length_penalty', 1.0), 'temperature': tts_settings.get('temperature', 0.7)},
        ]

        audio_paths = []
        for idx, variation in enumerate(synthesis_variations):
            audio_path = synthesize_speech(transcription, reference_audio, variation)
            if audio_path is not None:
                audio_paths.append(audio_path)
            else:
                await context.bot.send_message(chat_id=chat_id, text=f"Произошла ошибка при синтезе речи варианта {idx + 1}.")
                logger.error(f"Ошибка синтеза речи для пользователя {user_id}, вариант {idx + 1}.")

        if audio_paths:
            try:
                # Отправляем три аудио пользователю
                for idx, audio_path in enumerate(audio_paths, start=1):
                    with open(audio_path, 'rb') as audio_file:
                        await context.bot.send_audio(chat_id=chat_id, audio=audio_file, caption=f"Вариант {idx}")
                    logger.info(f"Аудиофайл варианта {idx} для пользователя {user_id} отправлен.")

                    # Удаляем синтезированный аудиофайл
                    os.remove(audio_path)
                    logger.info(f"Синтезированный аудиофайл {audio_path} удален.")
            except Exception as e:
                logger.error(f"Ошибка отправки аудио пользователю {user_id}: {str(e)}")
                await context.bot.send_message(chat_id=chat_id, text="Произошла ошибка при отправке синтезированных аудио.")
        else:
            await context.bot.send_message(chat_id=chat_id, text="Произошла ошибка при синтезе речи.")
            logger.error(f"Ошибка синтеза речи для пользователя {user_id}.")

        synthesis_queue.task_done()

        # Обновляем позиции в очереди для остальных пользователей
        await update_queue_positions(context)

    context.bot_data['synthesis_queue_running'] = False

async def update_queue_positions(context: ContextTypes.DEFAULT_TYPE):
    # Обновление позиций в очереди для пользователей
    queue_list = list(synthesis_queue._queue)
    for idx, request in enumerate(queue_list):
        user_id = request['user_id']
        chat_id = request['chat_id']
        position = idx + 1
        try:
            await context.bot.send_message(chat_id=chat_id, text=f"Ваша позиция в очереди на синтез речи: {position}")
        except Exception as e:
            logger.error(f"Ошибка отправки обновления очереди пользователю {user_id}: {str(e)}")

def process_text_transcription(text):
    """
    Обрабатывает текстовую транскрипцию: добавляет пунктуацию и капитализирует предложения.
    """
    try:
        # Добавляем пунктуацию и корректируем регистр с помощью PunctuationModel
        from dm2 import punctuation_model  # Импортируем модель из dm2
        if punctuation_model is None:
            logger.error("PunctuationModel не загружена.")
            punctuated_text = text
        else:
            punctuated_text = punctuation_model.restore_punctuation(text)
            logger.info("Пунктуация и регистр добавлены.")

        # Капитализируем каждое начало предложения
        from dm2 import capitalize_sentences
        punctuated_text = capitalize_sentences(punctuated_text)

        return punctuated_text
    except Exception as e:
        logger.error(f"Ошибка при обработке текстовой транскрипции: {str(e)}")
        return text  # Возвращаем исходный текст в случае ошибки

def main():
    # Создаём приложение бота
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Обработчик кнопок
    application.add_handler(CallbackQueryHandler(button_handler))

    # Обработчик текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))

    # Обработчик голосовых и аудио сообщений
    application.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, voice_or_audio_message_handler))

    # Обработчик для отмены
    application.add_handler(CommandHandler('cancel', cancel))

    # Запускаем бота
    logger.info("Бот запущен и ожидает сообщений...")
    application.run_polling()

if __name__ == '__main__':
    main()
import sys
import os
import wave
import json
import uuid  # Импортируем модуль uuid
from vosk import Model, KaldiRecognizer, SetLogLevel
from pydub import AudioSegment
import logging
from deepmultilingualpunctuation import PunctuationModel
from razdel import sentenize
import torch
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts
from scipy.io.wavfile import write
import re

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Уровень логирования Vosk
SetLogLevel(0)

# Путь к рабочей директории
WORKING_DIR = r'D:\prdja'

# Абсолютные пути к моделям
VOSK_MODEL_PATH = os.path.join(WORKING_DIR, 'model', 'vosk-model-ru-0.42')
SMALL_VOSK_MODEL_PATH = os.path.join(WORKING_DIR, 'model', 'vosk-model-small-ru-0.22')

# Пути к моделям синтеза речи
CONFIG_PATH = os.path.join(WORKING_DIR, 'XTTS-v2', 'config.json')
CHECKPOINT_PATH = os.path.join(WORKING_DIR, 'XTTS-v2')
VOCAB_PATH = os.path.join(WORKING_DIR, 'XTTS-v2', 'vocab.json')
SPEAKER_PATH = os.path.join(WORKING_DIR, 'XTTS-v2', 'speakers_xtts.pth')

# Глобальные переменные для моделей
small_model = None
large_model = None
punctuation_model = None
tts_model = None
tts_config = None
device = None

def load_models():
    global small_model, large_model, punctuation_model, tts_model, tts_config, device
    # Загружаем модели Vosk
    try:
        small_model = Model(SMALL_VOSK_MODEL_PATH)
        large_model = Model(VOSK_MODEL_PATH)
        logger.info("Обе модели Vosk загружены.")
    except Exception as e:
        logger.error(f"Ошибка загрузки моделей Vosk: {str(e)}")
        sys.exit(1)

    # Инициализируем модель для восстановления пунктуации
    try:
        punctuation_model = PunctuationModel()
        logger.info("PunctuationModel загружена.")
    except Exception as e:
        logger.error(f"Ошибка загрузки PunctuationModel: {str(e)}")
        punctuation_model = None  # Если модель не загрузилась, устанавливаем None

    # Загружаем модель синтеза речи
    try:
        tts_config = XttsConfig()
        tts_config.load_json(CONFIG_PATH)

        tts_model = Xtts.init_from_config(tts_config)
        tts_model.load_checkpoint(tts_config, checkpoint_dir=CHECKPOINT_PATH, eval=True)

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        tts_model = tts_model.to(device)
        logger.info("Модель синтеза речи загружена.")
    except Exception as e:
        logger.error(f"Ошибка загрузки модели синтеза речи: {str(e)}")
        tts_model = None

def convert_ogg_to_wav(ogg_path, wav_path):
    try:
        audio = AudioSegment.from_file(ogg_path)
        audio = audio.set_channels(1).set_frame_rate(16000).set_sample_width(2)
        audio.export(wav_path, format="wav")
        logger.info(f"Конвертировано в WAV: {wav_path}")

        # Проверка свойств WAV-файла
        with wave.open(wav_path, "rb") as wf:
            channels = wf.getnchannels()
            framerate = wf.getframerate()
            sampwidth = wf.getsampwidth()
            logger.info(f"Свойства WAV-файла - Каналы: {channels}, Частота: {framerate} Гц, Глубина бит: {sampwidth * 8} бит")
    except Exception as e:
        logger.error(f"Ошибка конвертации аудио: {str(e)}")
        sys.exit(1)

def transcribe_audio(wav_path, model):
    try:
        wf = wave.open(wav_path, "rb")
    except Exception as e:
        logger.error(f"Не удалось открыть WAV-файл: {str(e)}")
        sys.exit(1)

    if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getframerate() != 16000:
        logger.error("Аудио должно быть в формате mono WAV с частотой 16000 Гц.")
        wf.close()
        sys.exit(1)

    rec = KaldiRecognizer(model, wf.getframerate())
    rec.SetWords(True)
    transcript = ""

    while True:
        data = wf.readframes(4000)
        if len(data) == 0:
            break
        if rec.AcceptWaveform(data):
            result = rec.Result()
            result_dict = json.loads(result)
            transcript += result_dict.get("text", "") + " "

    # Последний фрагмент
    final_result = rec.FinalResult()
    final_dict = json.loads(final_result)
    transcript += final_dict.get("text", "")
    wf.close()
    logger.info("Распознавание речи завершено.")
    return transcript.strip()

def recase_punctuate(text):
    if punctuation_model is None:
        logger.error("PunctuationModel не загружена.")
        return text  # Возвращаем исходный текст без изменений
    try:
        punctuated_text = punctuation_model.restore_punctuation(text)
        logger.info("Пунктуация и регистр добавлены.")
        return punctuated_text
    except Exception as e:
        logger.error(f"Ошибка при восстановлении пунктуации: {str(e)}")
        return text

def capitalize_sentences(text):
    try:
        sentences = [_.text for _ in sentenize(text)]
        capitalized_sentences = [s.capitalize() for s in sentences]
        return ' '.join(capitalized_sentences)
    except Exception as e:
        logger.error(f"Ошибка при капитализации предложений: {str(e)}")
        return text

def process_audio_initial(ogg_path):
    if not os.path.isfile(ogg_path):
        logger.error(f"Файл {ogg_path} не найден.")
        return None

    # Конвертируем OGG в WAV
    wav_path = os.path.join(WORKING_DIR, f'voice_initial_{uuid.uuid4()}.wav')  # Уникальное имя файла
    convert_ogg_to_wav(ogg_path, wav_path)

    # Распознаём речь с помощью маленькой модели
    initial_transcript = transcribe_audio(wav_path, small_model)
    logger.info(f"Первичный распознанный текст: {initial_transcript}")

    # Добавляем пунктуацию и корректируем регистр с помощью PunctuationModel
    punctuated_initial_text = recase_punctuate(initial_transcript)

    # Капитализируем каждое начало предложения
    punctuated_initial_text = capitalize_sentences(punctuated_initial_text)

    # Удаляем временный файл
    try:
        os.remove(wav_path)
        logger.info(f"Временный файл {wav_path} удален.")
    except Exception as e:
        logger.error(f"Ошибка удаления временного файла {wav_path}: {str(e)}")

    return punctuated_initial_text

def process_audio_improved(ogg_path):
    if not os.path.isfile(ogg_path):
        logger.error(f"Файл {ogg_path} не найден.")
        return None

    # Конвертируем OGG в WAV (можно пропустить, если уже конвертировано)
    wav_path = os.path.join(WORKING_DIR, f'voice_improved_{uuid.uuid4()}.wav')  # Уникальное имя файла
    convert_ogg_to_wav(ogg_path, wav_path)

    # Распознаём речь с помощью большой модели
    improved_transcript = transcribe_audio(wav_path, large_model)
    logger.info(f"Улучшенный распознанный текст: {improved_transcript}")

    # Добавляем пунктуацию и корректируем регистр с помощью PunctuationModel
    punctuated_improved_text = recase_punctuate(improved_transcript)

    # Капитализируем каждое начало предложения
    punctuated_improved_text = capitalize_sentences(punctuated_improved_text)

    # Удаляем временный файл
    try:
        os.remove(wav_path)
        logger.info(f"Временный файл {wav_path} удален.")
    except Exception as e:
        logger.error(f"Ошибка удаления временного файла {wav_path}: {str(e)}")

    return punctuated_improved_text

def process_reference_audio(audio_path):
    try:
        audio = AudioSegment.from_file(audio_path)
        # Обрезаем до 15 секунд, если аудио длиннее
        if len(audio) > 15000:
            audio = audio[:15000]
        # Приводим аудио к нужному формату
        audio = audio.set_channels(1).set_frame_rate(16000).set_sample_width(2)
        # Сохраняем обработанное аудио с уникальным именем
        ref_audio_path = os.path.join(WORKING_DIR, f'reference_{uuid.uuid4()}.wav')
        audio.export(ref_audio_path, format='wav')
        logger.info(f"Референсное аудио обработано и сохранено: {ref_audio_path}")
        return ref_audio_path
    except Exception as e:
        logger.error(f"Ошибка обработки референсного аудио: {str(e)}")
        return None

def preprocess_text(text):
    try:
        # Добавляем пробел после знаков препинания, если его нет
        text = re.sub(r'([.,!?])([^\s])', r'\1 \2', text)
        # Разбиваем текст на предложения
        sentences = re.split(r'(?<=[.!?])\s', text)
        # Капитализируем каждое предложение
        sentences = [s.capitalize() for s in sentences]
        # Объединяем обратно
        processed_text = ' '.join(sentences)
        return processed_text
    except Exception as e:
        logger.error(f"Ошибка при обработке текста для синтеза: {str(e)}")
        return text

def synthesize_speech(text, reference_audio=None, tts_settings=None):
    if tts_model is None:
        logger.error("Модель синтеза речи не загружена.")
        return None

    if tts_settings is None:
        tts_settings = {
            'language': 'ru',
            'speed': 1.0,
            'repetition_penalty': 2.0,
            'length_penalty': 1.0,
            'temperature': 0.7,
            'enable_text_splitting': True
        }

    # Предобработка текста
    processed_text = preprocess_text(text)

    try:
        # Если reference_audio равен None, передаем None или пропускаем параметр speaker_wav
        outputs = tts_model.synthesize(
            text=processed_text,
            config=tts_config,
            speaker_wav=reference_audio if reference_audio else None,
            language=tts_settings.get('language', 'ru'),
            speed=tts_settings.get('speed', 1.0),
            repetition_penalty=tts_settings.get('repetition_penalty', 2.0),
            length_penalty=tts_settings.get('length_penalty', 1.0),
            temperature=tts_settings.get('temperature', 0.7),
            enable_text_splitting=tts_settings.get('enable_text_splitting', True)
        )

        # Извлекаем аудио
        audio = outputs["wav"]
        if isinstance(audio, torch.Tensor):
            audio = audio.cpu().numpy()

        # Сохраняем аудио с уникальным именем
        output_path = os.path.join(WORKING_DIR, f'output_{uuid.uuid4()}.wav')
        write(output_path, 24000, audio)
        logger.info(f"Аудиофайл синтезирован и сохранён: {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Ошибка синтеза речи: {str(e)}")
        return None

# Загружаем модели при импорте модуля
load_models()