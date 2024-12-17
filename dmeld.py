import sys
import os
import wave
import json
from vosk import Model, KaldiRecognizer, SetLogLevel
from pydub import AudioSegment
import logging
from deepmultilingualpunctuation import PunctuationModel
from razdel import sentenize
import torch

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
SECOND_PUNC_MODEL_PATH = os.path.join(WORKING_DIR, 'model','snakers4-silero-models-6b0bb8a')
# Глобальные переменные для моделей
small_model = None
large_model = None
punctuation_model = None

def load_models():
    global small_model, large_model, punctuation_model
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

    #Загрузка второй модели для восстановления пунктуации
    try:
        model, example_texts, languages, punct, apply_te = torch.hub.load(repo_or_dir='snakers4/silero-models',
                                                                  model='silero_te')
        logger.info("silero_punctuation_model успешно загружена")
    except Exception as e:
        logger.error(f"Ошибка загрузки второй пунктуационной модели: {str(e)}")

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
    global apply_te
    if punctuation_model is None:
        logger.error("PunctuationModel не загружена.")
        return text  # Возвращаем исходный текст без изменений
    try:
        punctuated_text = punctuation_model.restore_punctuation(text)
        punctuated_text = apply_te(punctuated_text, lan='ru')
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
    wav_path = os.path.join(WORKING_DIR, 'voice.wav')
    convert_ogg_to_wav(ogg_path, wav_path)

    # Распознаём речь с помощью маленькой модели
    initial_transcript = transcribe_audio(wav_path, small_model)
    logger.info(f"Первичный распознанный текст: {initial_transcript}")

    # Добавляем пунктуацию и корректируем регистр с помощью PunctuationModel
    punctuated_initial_text = recase_punctuate(initial_transcript)

    # Капитализируем каждое начало предложения
    punctuated_initial_text = capitalize_sentences(punctuated_initial_text)

    return punctuated_initial_text

def process_audio_improved(ogg_path):
    if not os.path.isfile(ogg_path):
        logger.error(f"Файл {ogg_path} не найден.")
        return None

    # Конвертируем OGG в WAV (можно пропустить, если уже конвертировано)
    wav_path = os.path.join(WORKING_DIR, 'voice.wav')
    if not os.path.isfile(wav_path):
        convert_ogg_to_wav(ogg_path, wav_path)

    # Распознаём речь с помощью большой модели
    improved_transcript = transcribe_audio(wav_path, large_model)
    logger.info(f"Улучшенный распознанный текст: {improved_transcript}")

    # Добавляем пунктуацию и корректируем регистр с помощью PunctuationModel
    punctuated_improved_text = recase_punctuate(improved_transcript)

    # Капитализируем каждое начало предложения
    punctuated_improved_text = capitalize_sentences(punctuated_improved_text)

    return punctuated_improved_text

# Загружаем модели при импорте модуля
load_models()
