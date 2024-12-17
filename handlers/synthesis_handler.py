# handlers/synthesis_handler.py

import asyncio
import os
from utils.logger import get_logger
from processing import synthesize_speech
from telegram import InputFile
from config import WORKING_DIR

logger = get_logger()

# Инициализируем очередь для синтеза
synthesis_queue = asyncio.Queue()

async def add_synthesis_request(context, query, transcription, reference_audio):
    """
    Добавляет запрос на синтез речи в очередь и информирует пользователя о позиции в очереди.
    """
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    request_id = uuid.uuid4()

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

async def process_synthesis_queue(context):
    """
    Обрабатывает очередь запросов на синтез речи.
    """
    while not synthesis_queue.empty():
        request = await synthesis_queue.get()
        user_id = request['user_id']
        chat_id = request['chat_id']
        transcription = request['transcription']
        reference_audio = request['reference_audio']
        tts_settings = request['tts_settings']

        # Информируем пользователя о начале синтеза
        await context.bot.send_message(chat_id=chat_id, text="Синтез речи начался, пожалуйста, подождите...")

        audio_paths = []
        variations = [
            {
                'speed': tts_settings.get('speed', 1.0),
                'repetition_penalty': tts_settings.get('repetition_penalty', 2.0),
                'length_penalty': tts_settings.get('length_penalty', 1.0),
                'temperature': tts_settings.get('temperature', 0.7)
            },
            {
                'speed': min(tts_settings.get('speed', 1.0) + 0.1, 2.0),
                'repetition_penalty': tts_settings.get('repetition_penalty', 2.0),
                'length_penalty': tts_settings.get('length_penalty', 1.0),
                'temperature': min(tts_settings.get('temperature', 0.7) + 0.05, 1.0)
            },
            {
                'speed': max(tts_settings.get('speed', 1.0) - 0.1, 0.5),
                'repetition_penalty': tts_settings.get('repetition_penalty', 2.0),
                'length_penalty': tts_settings.get('length_penalty', 1.0),
                'temperature': max(tts_settings.get('temperature', 0.7) - 0.05, 0.5)
            },
        ]

        for idx, variation in enumerate(variations, start=1):
            audio_path = synthesize_speech(transcription, reference_audio, variation)
            if audio_path:
                audio_paths.append((audio_path, idx))
            else:
                await context.bot.send_message(chat_id=chat_id, text=f"Произошла ошибка при синтезе речи варианта {idx}.")
                logger.error(f"Ошибка синтеза речи для пользователя {user_id}, вариант {idx}.")

        if audio_paths:
            try:
                for path, idx in audio_paths:
                    with open(path, 'rb') as audio_file:
                        await context.bot.send_audio(chat_id=chat_id, audio=InputFile(audio_file), caption=f"Вариант {idx}")
                    logger.info(f"Аудиофайл варианта {idx} для пользователя {user_id} отправлен.")

                    # Удаляем синтезированный аудиофайл
                    os.remove(path)
                    logger.info(f"Синтезированный аудиофайл {path} удален.")
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

async def update_queue_positions(context):
    """
    Обновляет позиции в очереди для всех пользователей.
    """
    queue_list = list(synthesis_queue._queue)
    for idx, request in enumerate(queue_list):
        user_id = request['user_id']
        chat_id = request['chat_id']
        position = idx + 1
        try:
            await context.bot.send_message(chat_id=chat_id, text=f"Ваша позиция в очереди на синтез речи: {position}")
        except Exception as e:
            logger.error(f"Ошибка отправки обновления очереди пользователю {user_id}: {str(e)}")
