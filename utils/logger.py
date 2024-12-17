# utils/logger.py

import logging
from config import LOGGING_PATH

# Настройка логирования
logging.basicConfig(
    filename=LOGGING_PATH,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def get_logger():
    return logger
