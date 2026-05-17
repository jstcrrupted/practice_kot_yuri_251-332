import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Настройки GPT
GPT_MODEL = "gpt-3.5-turbo"
MAX_TOKENS = 1000
TEMPERATURE = 0.7

# Максимальная длина истории диалога
MAX_HISTORY_LENGTH = 10
