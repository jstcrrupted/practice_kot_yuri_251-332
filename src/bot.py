import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, BotCommand
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from openai import AsyncOpenAI

from config import (
    TELEGRAM_TOKEN,
    OPENAI_API_KEY,
    GPT_MODEL,
    MAX_TOKENS,
    TEMPERATURE,
    MAX_HISTORY_LENGTH,
)

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Инициализация OpenAI клиента
client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# Хранилище истории диалогов
user_histories: dict[int, list[dict]] = {}


# ========================
# Состояния FSM
# ========================
class UserState(StatesGroup):
    chatting = State()
    waiting_system_prompt = State()


# ========================
# Вспомогательные функции
# ========================
def get_user_history(user_id: int) -> list[dict]:
    """Получить историю диалога пользователя."""
    if user_id not in user_histories:
        user_histories[user_id] = []
    return user_histories[user_id]


def add_to_history(user_id: int, role: str, content: str):
    """Добавить сообщение в историю."""
    history = get_user_history(user_id)
    history.append({"role": role, "content": content})

    # Ограничиваем длину истории
    if len(history) > MAX_HISTORY_LENGTH * 2:
        user_histories[user_id] = history[-MAX_HISTORY_LENGTH * 2:]


def clear_history(user_id: int):
    """Очистить историю диалога."""
    user_histories[user_id] = []


async def ask_gpt(
    user_id: int,
    user_message: str,
    system_prompt: str = "Ты полезный ассистент. Отвечай на русском языке.",
) -> str:
    """Отправить запрос к GPT и получить ответ."""
    try:
        add_to_history(user_id, "user", user_message)

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(get_user_history(user_id))

        response = await client.chat.completions.create(
            model=GPT_MODEL,
            messages=messages,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
        )

        assistant_message = response.choices[0].message.content
        add_to_history(user_id, "assistant", assistant_message)

        return assistant_message

    except Exception as e:
        logger.error(f"Ошибка при запросе к GPT: {e}")
        # Удаляем последнее сообщение пользователя из истории при ошибке
        history = get_user_history(user_id)
        if history and history[-1]["role"] == "user":
            history.pop()
        raise


# ========================
# Клавиатуры
# ========================
def get_main_keyboard():
    """Главная клавиатура."""
    keyboard = types.ReplyKeyboardMarkup(
        keyboard=[
            [
                types.KeyboardButton(text="🆕 Новый диалог"),
                types.KeyboardButton(text="⚙️ Системный промпт"),
            ],
            [
                types.KeyboardButton(text="📊 Статистика"),
                types.KeyboardButton(text="❓ Помощь"),
            ],
        ],
        resize_keyboard=True,
    )
    return keyboard


def get_cancel_keyboard():
    """Клавиатура отмены."""
    keyboard = types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
    )
    return keyboard


# ========================
# Хранилище системных промптов
# ========================
user_system_prompts: dict[int, str] = {}
DEFAULT_SYSTEM_PROMPT = "Ты полезный ассистент. Отвечай на русском языке."


def get_system_prompt(user_id: int) -> str:
    """Получить системный промпт пользователя."""
    return user_system_prompts.get(user_id, DEFAULT_SYSTEM_PROMPT)


# ========================
# Обработчики команд
# ========================
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start."""
    await state.set_state(UserState.chatting)
    user_name = message.from_user.first_name

    await message.answer(
        f"👋 Привет, {user_name}!\n\n"
        "Я — бот с интеграцией GPT. Просто напиши мне что-нибудь, "
        "и я постараюсь помочь!\n\n"
        "📌 Доступные команды:\n"
        "/new — начать новый диалог\n"
        "/help — помощь\n"
        "/stats — статистика\n"
        "/system — изменить системный промпт",
        reply_markup=get_main_keyboard(),
    )


@dp.message(Command("help"))
@dp.message(F.text == "❓ Помощь")
async def cmd_help(message: Message):
    """Обработчик команды /help."""
    await message.answer(
        "🤖 <b>Как пользоваться ботом:</b>\n\n"
        "1. Просто напишите сообщение — бот ответит с помощью GPT\n"
        "2. Бот помнит контекст диалога\n"
        "3. Используйте <b>Новый диалог</b> для сброса контекста\n\n"
        "📋 <b>Команды:</b>\n"
        "/start — перезапустить бота\n"
        "/new — начать новый диалог\n"
        "/system — изменить системный промпт\n"
        "/stats — показать статистику\n"
        "/help — эта справка\n\n"
        "⚙️ <b>Системный промпт</b> — инструкция для ИИ о его роли и поведении",
        parse_mode="HTML",
        reply_markup=get_main_keyboard(),
    )


@dp.message(Command("new"))
@dp.message(F.text == "🆕 Новый диалог")
async def cmd_new_dialog(message: Message, state: FSMContext):
    """Начать новый диалог."""
    await state.set_state(UserState.chatting)
    clear_history(message.from_user.id)
    await message.answer(
        "🆕 Новый диалог начат! История очищена.\n"
        "Можете задать новый вопрос.",
        reply_markup=get_main_keyboard(),
    )


@dp.message(Command("stats"))
@dp.message(F.text == "📊 Статистика")
async def cmd_stats(message: Message):
    """Показать статистику."""
    user_id = message.from_user.id
    history = get_user_history(user_id)
    messages_count = len(history)
    user_messages = sum(1 for m in history if m["role"] == "user")
    system_prompt = get_system_prompt(user_id)

    await message.answer(
        f"📊 <b>Статистика диалога:</b>\n\n"
        f"💬 Всего сообщений: {messages_count}\n"
        f"👤 Ваших сообщений: {user_messages}\n"
        f"🤖 Ответов ИИ: {messages_count - user_messages}\n\n"
        f"⚙️ Текущий системный промпт:\n"
        f"<i>{system_prompt}</i>",
        parse_mode="HTML",
        reply_markup=get_main_keyboard(),
    )


@dp.message(Command("system"))
@dp.message(F.text == "⚙️ Системный промпт")
async def cmd_system(message: Message, state: FSMContext):
    """Изменить системный промпт."""
    current_prompt = get_system_prompt(message.from_user.id)
    await state.set_state(UserState.waiting_system_prompt)
    await message.answer(
        f"⚙️ <b>Изменение системного промпта</b>\n\n"
        f"Текущий промпт:\n<i>{current_prompt}</i>\n\n"
        "Введите новый системный промпт или нажмите отмену:",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard(),
    )


@dp.message(UserState.waiting_system_prompt, F.text == "❌ Отмена")
async def cancel_system_prompt(message: Message, state: FSMContext):
    """Отмена изменения промпта."""
    await state.set_state(UserState.chatting)
    await message.answer(
        "❌ Изменение отменено.",
        reply_markup=get_main_keyboard(),
    )


@dp.message(UserState.waiting_system_prompt)
async def set_system_prompt(message: Message, state: FSMContext):
    """Установить новый системный промпт."""
    user_id = message.from_user.id
    new_prompt = message.text.strip()

    if len(new_prompt) < 5:
        await message.answer("❗ Промпт слишком короткий. Попробуйте ещё раз:")
        return

    user_system_prompts[user_id] = new_prompt
    clear_history(user_id)  # Сбрасываем историю при смене промпта
    await state.set_state(UserState.chatting)

    await message.answer(
        f"✅ Системный промпт обновлён!\n\n"
        f"<i>{new_prompt}</i>\n\n"
        "История диалога сброшена. Можете начать новый разговор.",
        parse_mode="HTML",
        reply_markup=get_main_keyboard(),
    )


# ========================
# Основной обработчик сообщений
# ========================
@dp.message(UserState.chatting)
@dp.message(F.text & ~F.text.startswith("/"))
async def handle_message(message: Message, state: FSMContext):
    """Обработчик обычных сообщений — отправка в GPT."""
    user_id = message.from_user.id
    user_text = message.text.strip()

    if not user_text:
        await message.answer("❗ Пожалуйста, введите текстовое сообщение.")
        return

    # Показываем индикатор печати
    await bot.send_chat_action(message.chat.id, "typing")

    try:
        system_prompt = get_system_prompt(user_id)
        response = await ask_gpt(user_id, user_text, system_prompt)

        # Разбиваем длинные сообщения
        if len(response) > 4096:
            for i in range(0, len(response), 4096):
                await message.answer(response[i : i + 4096])
        else:
            await message.answer(response)

    except Exception as e:
        logger.error(f"Ошибка для пользователя {user_id}: {e}")
        await message.answer(
            "❌ Произошла ошибка при обращении к ИИ.\n"
            "Попробуйте ещё раз или начните новый диалог.",
            reply_markup=get_main_keyboard(),
        )


# ========================
# Запуск бота
# ========================
async def set_commands():
    """Установить команды бота."""
    commands = [
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="new", description="Начать новый диалог"),
        BotCommand(command="system", description="Изменить системный промпт"),
        BotCommand(command="stats", description="Статистика диалога"),
        BotCommand(command="help", description="Помощь"),
    ]
    await bot.set_my_commands(commands)


async def main():
    """Основная функция запуска."""
    logger.info("Запуск бота...")
    await set_commands()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
