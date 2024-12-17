# api_server.py

from fastapi import FastAPI, UploadFile, File, Form
from typing import Optional
import uvicorn
import logging

app = FastAPI()

# Настройка логирования
logging.basicConfig(
    filename='received_data.log',
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.post("/receive_data/")
async def receive_data(
    function_name: str = Form(...),
    data: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None)
):
    """
    Эндпоинт для приема данных от бота.
    """
    log_entry = f"Function: {function_name}, Data: {data}"
    logger.info(log_entry)
    print(log_entry)  # Также выводим в консоль

    if file:
        file_location = f"received_files/{file.filename}"
        with open(file_location, "wb") as f:
            f.write(await file.read())
        logger.info(f"Received file: {file.filename}, saved to {file_location}")
        print(f"Received file: {file.filename}, saved to {file_location}")

    return {"status": "success"}

if __name__ == "__main__":
    # Создайте директорию для файлов, если её нет
    import os
    if not os.path.exists("received_files"):
        os.makedirs("received_files")

    uvicorn.run(app, host="0.0.0.0", port=8000)
