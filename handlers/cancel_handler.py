# handlers/cancel_handler.py

from telegram import Update
from telegram.ext import ContextTypes
from utils.logger import get_logger

logger = get_logger()

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик команды /cancel, отменяющий текущие действия пользователя.
    """
    await update.message.reply_text("Действие отменено.")
    context.user_data.clear()
    logger.info(f"Пользователь {update.effective_user.id} отменил действие.")
