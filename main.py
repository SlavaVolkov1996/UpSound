import re
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from yandex_music import Client

# Конфигурация
import os
from dotenv import load_dotenv

env_loaded = load_dotenv()
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
YANDEX_MUSIC_TOKEN = os.getenv('YANDEX_MUSIC_TOKEN')

# Инициализация клиента Яндекс.Музыки
yandex_client = Client(YANDEX_MUSIC_TOKEN)


def extract_track_id(url: str) -> str:
    """Извлекает ID трека из URL Яндекс.Музыки"""
    patterns = [
        r'track/(\d+)',
        r'album/\d+/track/(\d+)',
        r'playlists/\d+/\d+\?trackId=(\d+)'
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def format_duration(seconds: int) -> str:
    """Форматирует длительность трека"""
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes}:{seconds:02d}"


def get_track_info(track_id: str) -> str:
    """Получает информацию о треке из Яндекс.Музыки"""
    try:
        # Получаем трек
        track = yandex_client.tracks([track_id])[0]

        # Получаем информацию
        title = track.title
        artists = ", ".join(artist.name for artist in track.artists)
        duration = format_duration(track.duration_ms // 1000)
        album = track.albums[0].title if track.albums else "Неизвестный альбом"

        # Форматируем ответ
        info = f"<b>Название {title}</b>\n"
        info += f"<b>Исполнитель:</b> {artists}\n"
        # info += f"💿 <b>Альбом:</b> {album}\n"
        info += f"<b>Длительность:</b> {duration}\n"

        # Добавляем ссылку на обложку если есть
        # if track.cover_uri:
        #     cover_url = f"https://{track.cover_uri.replace('%%', '400x400')}"
        #     info += f"\n🖼 Обложка: {cover_url}"

        return info

    except Exception as e:
        return f"❌ Ошибка при получении информации: {str(e)}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    welcome_text = (
        "👋 Привет! Я помогу получить информацию о треках Яндекс.Музыки.\n\n"
        "Просто отправь мне ссылку на трек, например:\n"
        "• https://music.yandex.ru/track/12345678\n"
        "• https://music.yandex.ru/album/1234567/track/12345678"
    )
    await update.message.reply_text(welcome_text)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    message_text = update.message.text

    # Проверяем, является ли сообщение ссылкой
    if "yandex" in message_text.lower() and "music" in message_text.lower():
        await update.message.reply_text("Обрабатываю ссылку...")

        # Извлекаем ID трека
        track_id = extract_track_id(message_text)

        if track_id:
            # Получаем информацию о треке
            track_info = get_track_info(track_id)
            await update.message.reply_html(track_info)
        else:
            await update.message.reply_text("❌ Не удалось извлечь ID трека из ссылки.")
    else:
        await update.message.reply_text(
            "📎 Отправьте мне ссылку на трек из Яндекс.Музыки.\n"
            "Используйте /start для справки."
        )


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    print(f"Ошибка: {context.error}")
    if update and update.message:
        await update.message.reply_text("⚠️ Произошла ошибка. Попробуйте позже.")


def main():
    """Основная функция запуска бота"""
    # Создаем приложение
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Регистрируем обработчик ошибок
    application.add_error_handler(error_handler)

    # Запускаем бота
    print("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()  # Простой вызов без asyncio.run()
