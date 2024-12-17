import os
import uuid
import logging
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from TTS.tts.models.xtts import Xtts
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.vits import Vits
from TTS.tts.configs.vits_config import VitsConfig
from scipy.io.wavfile import write
import torch
from pydub import AudioSegment

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Пути к XTTS2 и VITS2 моделям
WORKING_DIR = r"D:\prdja"
XTTS2_CONFIG_PATH = os.path.join(WORKING_DIR, "XTTS-v2", "config.json")
XTTS2_CHECKPOINT_PATH = os.path.join(WORKING_DIR, "XTTS-v2")
VITS2_CONFIG_PATH = os.path.join(WORKING_DIR, "vits2_ru_natasha", "config.json")
VITS2_CHECKPOINT_PATH = os.path.join(WORKING_DIR, "vits2_ru_natasha", "G_138000.pth")

# Глобальные переменные для моделей
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
xtts_model, vits2_model = None, None

# Загрузка XTTS2
def load_xtts2_model():
    global xtts_model, xtts_config
    try:
        xtts_config = XttsConfig()
        xtts_config.load_json(XTTS2_CONFIG_PATH)
        xtts_model = Xtts.init_from_config(xtts_config)
        xtts_model.load_checkpoint(xtts_config, checkpoint_dir=XTTS2_CHECKPOINT_PATH, eval=True)
        xtts_model = xtts_model.to(device)
        logger.info("XTTS2 загружена.")
    except Exception as e:
        logger.error(f"Ошибка загрузки XTTS2: {e}")


# Загрузка VITS2
def load_vits2_model():
    global vits2_model
    try:
        vits2_config = VitsConfig()
        vits2_config.load_json(VITS2_CONFIG_PATH)
        vits2_model = Vits.init_from_config(vits2_config)
        vits2_model.load_checkpoint(vits2_config, checkpoint_path=VITS2_CHECKPOINT_PATH, eval=True)
        vits2_model = vits2_model.to(device)
        logger.info("VITS2 загружена.")
    except Exception as e:
        logger.error(f"Ошибка загрузки VITS2: {e}")

def synthesize_xtts2(text, reference_audio):
    try:
        outputs = xtts_model.synthesize(
            text=text,
            config=xtts_model.config,  # Добавляем конфиг модели
            speaker_wav=reference_audio,
            language="ru"
        )
        audio = outputs["wav"]
        if isinstance(audio, torch.Tensor):  # Проверяем, если это тензор
            audio = audio.cpu().numpy()

        audio_path = os.path.join(WORKING_DIR, f"xtts_output_{uuid.uuid4()}.wav")
        write(audio_path, 24000, audio)
        logger.info(f"XTTS2 синтезирован и сохранён: {audio_path}")
        return audio_path
    except Exception as e:
        logger.error(f"Ошибка XTTS2 синтеза: {e}")
        return None



def add_emotion_vits2(input_audio, emotion):
    try:
        # Конвертируем входное аудио в подходящий формат
        audio = AudioSegment.from_file(input_audio).set_frame_rate(22050).set_channels(1)
        temp_path = os.path.join(WORKING_DIR, f"temp_{uuid.uuid4()}.wav")
        audio.export(temp_path, format="wav")

        # Вызываем inference для VITS2 без параметра speaker_id
        with torch.no_grad():
            output_audio = vits2_model.infer(
                reference_audio=temp_path,  # Путь к референсному аудио
                speed=1.0                   # Можно дополнительно регулировать скорость
            )

        # Сохраняем результат синтеза
        output_path = os.path.join(WORKING_DIR, f"vits_output_{uuid.uuid4()}.wav")
        write(output_path, 22050, output_audio)
        logger.info(f"VITS2 обработало аудио с эмоцией '{emotion}' и сохранило: {output_path}")

        os.remove(temp_path)  # Удаляем временный файл
        return output_path
    except Exception as e:
        logger.error(f"Ошибка добавления эмоции через VITS2: {e}")
        return None



# Функция запуска синтеза
def run_synthesis():
    text = text_input.get("1.0", "end").strip()
    emotion = emotion_var.get()
    reference_audio = ref_audio_path.get()

    if not text or not reference_audio:
        messagebox.showerror("Ошибка", "Заполните текст и выберите референс-аудио.")
        return

    xtts_output = synthesize_xtts2(text, reference_audio)
    if xtts_output:
        final_output = add_emotion_vits2(xtts_output, emotion)
        if final_output:
            messagebox.showinfo("Успех", f"Файл с эмоцией сохранён: {final_output}")
        else:
            messagebox.showerror("Ошибка", "Не удалось добавить эмоцию.")
    else:
        messagebox.showerror("Ошибка", "Не удалось синтезировать XTTS2.")

# Графический интерфейс
root = tk.Tk()
root.title("Синтез речи XTTS2 + VITS2")
root.geometry("500x400")

# Выбор референсного аудио
ref_audio_path = tk.StringVar()

def choose_audio():
    file_path = filedialog.askopenfilename(filetypes=[("Audio Files", "*.wav *.mp3")])
    if file_path:
        ref_audio_path.set(file_path)

tk.Label(root, text="Выберите аудиофайл референса:").pack(pady=5)
tk.Entry(root, textvariable=ref_audio_path, width=50).pack(pady=5)
tk.Button(root, text="Обзор", command=choose_audio).pack(pady=5)

# Ввод текста
tk.Label(root, text="Введите текст для синтеза:").pack(pady=5)
text_input = tk.Text(root, height=5, width=50)
text_input.pack(pady=5)

# Выбор эмоции
tk.Label(root, text="Выберите эмоцию:").pack(pady=5)
emotion_var = tk.StringVar(value="neutral")
emotions = ["neutral", "happy", "sad", "angry"]
emotion_menu = ttk.Combobox(root, textvariable=emotion_var, values=emotions, state="readonly")
emotion_menu.pack(pady=5)

# Кнопка запуска
tk.Button(root, text="Синтезировать", command=run_synthesis).pack(pady=20)

# Загрузка моделей при старте
load_xtts2_model()
load_vits2_model()

root.mainloop()
