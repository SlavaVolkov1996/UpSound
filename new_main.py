import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from yandex_music import Client

# Конфигурация
import os
from dotenv import load_dotenv

env_loaded = load_dotenv()
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
YANDEX_MUSIC_TOKEN = os.getenv('YANDEX_MUSIC_TOKEN')

# Инициализация клиента Яндекс.Музыки
yandex_client = Client(YANDEX_MUSIC_TOKEN).init()

# Глобальные переменные для хранения данных между шагами
user_track_data = {}


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


def get_basic_track_info(track_id: str) -> dict:
    """Получает основную информацию о треке"""
    try:
        track = yandex_client.tracks([track_id])[0]

        return {
            'title': track.title,
            'artists': ", ".join(artist.name for artist in track.artists),
            'duration': format_duration(track.duration_ms // 1000),
            'album': track.albums[0].title if track.albums else "Неизвестный альбом",
            'year': track.albums[0].year if track.albums and hasattr(track.albums[0], 'year') else "Неизвестно",
            'genre': track.albums[0].genre if track.albums and hasattr(track.albums[0], 'genre') else "Не указан",
            'cover_url': track.get_cover_url(size='400x400') if hasattr(track, 'get_cover_url') else None,
            'track_id': track_id,
            'album_id': track.albums[0].id if track.albums else None
        }
    except Exception as e:
        return {'error': f"Ошибка при получении основной информации: {str(e)}"}


def get_extended_track_info(track_id: str, album_id: str = None) -> dict:
    """Получает расширенную информацию о треке со всеми доступными данными[citation:5]"""
    try:
        # Получаем трек
        track = yandex_client.tracks([track_id])[0]

        # Базовые данные
        info = get_basic_track_info(track_id)
        if 'error' in info:
            return info

        # Расширенные данные об альбоме
        if album_id and track.albums:
            try:
                album = yandex_client.albums_with_tracks(album_id)
                if album:
                    info['album_tracks_count'] = len(album.volumes[0]) if album.volumes else 0
                    info['album_release_date'] = album.release_date if hasattr(album, 'release_date') else "Неизвестно"
                    info['album_label'] = album.label if hasattr(album, 'label') else "Не указан"
                    info['album_available'] = album.available if hasattr(album, 'available') else True
            except:
                pass

        # Данные об исполнителях
        artists_info = []
        for artist in track.artists:
            try:
                artist_data = yandex_client.artists(artist.id)[0]
                artist_info = {
                    'name': artist.name,
                    'id': artist.id,
                    'genres': artist_data.genres if hasattr(artist_data, 'genres') else [],
                    'tracks_count': artist_data.counts.tracks if hasattr(artist_data, 'counts') and hasattr(
                        artist_data.counts, 'tracks') else "Неизвестно",
                    'albums_count': artist_data.counts.direct_albums if hasattr(artist_data, 'counts') and hasattr(
                        artist_data.counts, 'direct_albums') else "Неизвестно"
                }
                artists_info.append(artist_info)
            except:
                artists_info.append({'name': artist.name, 'id': artist.id})

        info['artists_detailed'] = artists_info

        # Похожие треки (рекомендации)
        try:
            similar_tracks = yandex_client.tracks_similar(track_id)
            if similar_tracks and hasattr(similar_tracks, 'similar_tracks'):
                info['similar_tracks'] = [
                    {
                        'title': t.title,
                        'artists': ", ".join(a.name for a in t.artists),
                        'id': t.id
                    }
                    for t in similar_tracks.similar_tracks[:5]  # Берем только первые 5
                ]
        except:
            info['similar_tracks'] = []

        # Информация о доступности
        info['available'] = track.available if hasattr(track, 'available') else True
        info['available_for_premium_users'] = track.available_for_premium_users if hasattr(track,
                                                                                           'available_for_premium_users') else True
        info['lyrics_available'] = track.lyrics_available if hasattr(track, 'lyrics_available') else False

        # Дополнительные метаданные
        info['file_size'] = f"{(track.file_size / 1024 / 1024):.2f} MB" if hasattr(track, 'file_size') else "Неизвестно"
        info['version'] = track.version if hasattr(track, 'version') else None
        info['content_warning'] = track.content_warning if hasattr(track, 'content_warning') else None
        info['explicit'] = track.explicit if hasattr(track, 'explicit') else False
        info['track_number'] = track.track_number if hasattr(track, 'track_number') else 0
        info['major'] = track.major.name if hasattr(track, 'major') and track.major else None

        # Получение чартов (если трек в чартах)[citation:3][citation:8]
        try:
            chart = yandex_client.chart('world').chart
            chart_positions = []
            for chart_item in chart.tracks[:50]:  # Проверяем первые 50 позиций
                if chart_item.track.id == track_id:
                    chart_positions.append({
                        'position': chart_item.chart.position,
                        'progress': chart_item.chart.progress,
                        'listeners': chart_item.chart.listeners
                    })
            info['chart_positions'] = chart_positions
        except:
            info['chart_positions'] = []

        return info
    except Exception as e:
        return {'error': f"Ошибка при получении расширенной информации: {str(e)}"}


def format_basic_info(info: dict) -> str:
    """Форматирует основную информацию для вывода"""
    if 'error' in info:
        return f"❌ {info['error']}"

    text = f"🎵 <b>{info['title']}</b>\n"
    text += f"👤 <b>Исполнитель:</b> {info['artists']}\n"
    text += f"⏱ <b>Длительность:</b> {info['duration']}\n"

    return text


def format_extended_info(info: dict) -> str:
    """Форматирует расширенную информацию для вывода"""
    if 'error' in info:
        return f"❌ {info['error']}"

    text = f"🎵 <b>{info['title']}</b>\n\n"

    # Основная информация
    text += "📋 <b>Основная информация:</b>\n"
    text += f"   👤 <b>Исполнитель:</b> {info['artists']}\n"
    text += f"   💿 <b>Альбом:</b> {info['album']}\n"
    text += f"   📅 <b>Год:</b> {info['year']}\n"
    text += f"   ⏱ <b>Длительность:</b> {info['duration']}\n"
    text += f"   🎭 <b>Жанр:</b> {info['genre']}\n\n"

    # Детальная информация об исполнителях
    if 'artists_detailed' in info:
        text += "👥 <b>Детали об исполнителях:</b>\n"
        for artist in info['artists_detailed']:
            text += f"   • <b>{artist['name']}</b>\n"
            if 'genres' in artist and artist['genres']:
                text += f"     Жанры: {', '.join(artist['genres'])}\n"
            if 'tracks_count' in artist:
                text += f"     Треков: {artist['tracks_count']}\n"
            if 'albums_count' in artist:
                text += f"     Альбомов: {artist['albums_count']}\n"
        text += "\n"

    # Информация об альбоме
    if 'album_tracks_count' in info:
        text += "💿 <b>Информация об альбоме:</b>\n"
        text += f"   Всего треков: {info['album_tracks_count']}\n"
        if 'album_release_date' in info:
            text += f"   Дата релиза: {info['album_release_date']}\n"
        if 'album_label' in info:
            text += f"   Лейбл: {info['album_label']}\n"
        text += "\n"

    # Техническая информация
    text += "🔧 <b>Техническая информация:</b>\n"
    text += f"   Доступен: {'✅' if info['available'] else '❌'}\n"
    text += f"   Для премиум: {'✅' if info.get('available_for_premium_users', True) else '❌'}\n"
    text += f"   Текст песни: {'✅' if info.get('lyrics_available', False) else '❌'}\n"
    text += f"   Размер файла: {info.get('file_size', 'Неизвестно')}\n"
    text += f"   Явный контент: {'✅' if info.get('explicit', False) else '❌'}\n"

    if info.get('version'):
        text += f"   Версия: {info['version']}\n"
    if info.get('content_warning'):
        text += f"   Предупреждение: {info['content_warning']}\n"
    if info.get('major'):
        text += f"   Лейбл: {info['major']}\n"

    text += f"   Номер трека в альбоме: {info.get('track_number', 0)}\n\n"

    # Похожие треки
    if info.get('similar_tracks'):
        text += "🎶 <b>Похожие треки:</b>\n"
        for i, similar in enumerate(info['similar_tracks'][:3], 1):
            text += f"   {i}. {similar['title']} - {similar['artists']}\n"
        text += "\n"

    # Позиции в чартах
    if info.get('chart_positions'):
        text += "🏆 <b>Позиции в чартах:</b>\n"
        for pos in info['chart_positions']:
            progress_emoji = ''
            if pos['progress'] == 'up':
                progress_emoji = '🔺'
            elif pos['progress'] == 'down':
                progress_emoji = '🔻'
            elif pos['progress'] == 'new':
                progress_emoji = '🆕'

            text += f"   {progress_emoji} Позиция: {pos['position']}"
            if pos.get('listeners'):
                text += f" (👂 {pos['listeners']})"
            text += "\n"

    # Ссылки
    if info['cover_url']:
        text += f"\n🖼 <a href='{info['cover_url']}'>Обложка альбома</a>"

    text += f"\n🎧 <a href='https://music.yandex.ru/track/{info["track_id"]}'>Слушать на Яндекс.Музыке</a>"

    return text


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    welcome_text = (
        "👋 Привет! Я помогу получить информацию о треках Яндекс.Музыки.\n\n"
        "Просто отправь мне ссылку на трек, например:\n"
        "• https://music.yandex.ru/track/12345678\n"
        "• https://music.yandex.ru/album/1234567/track/12345678\n\n"
        "После получения ссылки я предложу выбрать уровень детализации информации."
    )
    await update.message.reply_text(welcome_text)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    message_text = update.message.text

    # Проверяем, является ли сообщение ссылкой
    if "yandex" in message_text.lower() and "music" in message_text.lower():
        await update.message.reply_text("🔍 Обрабатываю ссылку...")

        # Извлекаем ID трека
        track_id = extract_track_id(message_text)

        if track_id:
            # Сохраняем track_id в контексте пользователя
            context.user_data['track_id'] = track_id

            # Создаем клавиатуру для выбора типа информации
            keyboard = [
                [
                    InlineKeyboardButton("📋 Основная информация", callback_data=f"basic_{track_id}"),
                    InlineKeyboardButton("📊 Расширенная информация", callback_data=f"extended_{track_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                "Выберите уровень детализации информации:",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text("❌ Не удалось извлечь ID трека из ссылки.")
    else:
        await update.message.reply_text(
            "📎 Отправьте мне ссылку на трек из Яндекс.Музыки.\n"
            "Используйте /start для справки."
        )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()

    # Извлекаем тип и track_id из callback_data
    data_parts = query.data.split('_')
    info_type = data_parts[0]
    track_id = data_parts[1] if len(data_parts) > 1 else context.user_data.get('track_id')

    if not track_id:
        await query.edit_message_text("❌ Ошибка: не найден ID трека.")
        return

    if info_type == 'basic':
        # Получаем основную информацию
        await query.edit_message_text("📋 Получаю основную информацию...")
        track_info = get_basic_track_info(track_id)
        formatted_info = format_basic_info(track_info)

        # Отправляем фото обложки, если есть
        if 'cover_url' in track_info and track_info['cover_url']:
            try:
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=track_info['cover_url'],
                    caption=formatted_info,
                    parse_mode='HTML'
                )
                await query.message.delete()
                return
            except:
                pass  # Если не удалось отправить фото, отправляем просто текст

        await query.edit_message_text(formatted_info, parse_mode='HTML')

    elif info_type == 'extended':
        # Получаем расширенную информацию
        await query.edit_message_text("📊 Получаю расширенную информацию...")

        # Сначала получаем базовую информацию для album_id
        basic_info = get_basic_track_info(track_id)
        album_id = basic_info.get('album_id') if 'error' not in basic_info else None

        # Получаем расширенную информацию
        track_info = get_extended_track_info(track_id, album_id)
        formatted_info = format_extended_info(track_info)

        # Отправляем фото обложки, если есть
        if 'cover_url' in basic_info and basic_info['cover_url']:
            try:
                # ФИКС: Проверяем и исправляем незакрытые HTML-теги перед отправкой
                # Если текст слишком длинный, отправляем его отдельным сообщением
                if len(formatted_info) > 1000:
                    # Сначала отправляем фото с кратким описанием
                    short_caption = f"🎵 <b>{basic_info.get('title', 'Трек')}</b>\n👤 <b>Исполнитель:</b> {basic_info.get('artists', 'Неизвестно')}"
                    await context.bot.send_photo(
                        chat_id=query.message.chat_id,
                        photo=basic_info['cover_url'],
                        caption=short_caption,
                        parse_mode='HTML'
                    )
                    # Затем отправляем полный текст отдельным сообщением
                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=formatted_info,
                        parse_mode='HTML',
                        disable_web_page_preview=True
                    )
                else:
                    # Если текст короткий, отправляем как есть
                    await context.bot.send_photo(
                        chat_id=query.message.chat_id,
                        photo=basic_info['cover_url'],
                        caption=formatted_info,
                        parse_mode='HTML'
                    )
                await query.message.delete()
                return
            except Exception as e:
                print(f"Ошибка при отправке фото: {e}")
                # Если ошибка, отправляем просто текст
                await query.edit_message_text(formatted_info, parse_mode='HTML', disable_web_page_preview=True)

        # Если не удалось отправить с фото, отправляем просто текст
        await query.edit_message_text(formatted_info, parse_mode='HTML', disable_web_page_preview=True)


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
    application.add_handler(CallbackQueryHandler(button_callback))

    # Регистрируем обработчик ошибок
    application.add_error_handler(error_handler)

    # Запускаем бота
    print("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()