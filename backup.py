import csv
import logging
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

# Настройка кодировки стандартного вывода для Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("spotify-backup")

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

try:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials
except ImportError:
    logger.error(
        "Библиотека 'spotipy' не установлена. "
        "Установите необходимые зависимости командой: pip install -r requirements.txt"
    )
    sys.exit(1)

CSV_COLUMNS = [
    "Artist(s)",
    "Track Name",
    "Album",
    "Release Date",
    "ISRC",
    "Spotify URL",
    "Spotify URI",
    "Added At",
]

DEFAULT_OUTPUT_PATH = os.path.join("backups", "playlist.csv")


def clean_playlist_id(raw_id: str) -> str:
    """
    Извлекает чистый идентификатор плейлиста из различных форматов:
    - Чистый ID: '37i9dQZF1DXcBWIGoYBM5M'
    - Ссылка: 'https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=...'
    - Региональная ссылка: 'https://open.spotify.com/intl-ru/playlist/37i9dQZF1DXcBWIGoYBM5M'
    - Мобильная ссылка: 'https://spotify.link/...'
    - URI: 'spotify:playlist:37i9dQZF1DXcBWIGoYBM5M'
    - Ссылка в кавычках: '"https://open.spotify.com/playlist/..."'
    """
    # Удаляем пробелы и возможные случайные кавычки вокруг значения
    raw_id = raw_id.strip().strip('"').strip("'").strip()

    # Если передана сокращенная мобильная ссылка вида spotify.link
    if "spotify.link" in raw_id or "spotify.app.link" in raw_id:
        try:
            import urllib.request

            req = urllib.request.Request(
                raw_id,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                raw_id = response.geturl()
        except Exception as exc:
            logger.warning("Не удалось развернуть короткую ссылку %s: %s", raw_id, exc)

    # Ищем playlist/<id> или playlist:<id>
    url_match = re.search(r"playlist[/:]([a-zA-Z0-9]+)", raw_id)
    if url_match:
        return url_match.group(1)

    # Проверка старого формата URI spotify:user:...:playlist:...
    if ":playlist:" in raw_id:
        return raw_id.split(":playlist:")[-1].split("?")[0].strip()

    # Очистка query-параметров и слэшей
    clean = raw_id.split("?")[0].strip().rstrip("/")
    if "/" in clean:
        clean = clean.split("/")[-1]

    return clean


def validate_environment() -> Tuple[str, str, str]:
    """
    Проверяет наличие обязательных переменных окружения.
    Возвращает (client_id, client_secret, playlist_id).
    """
    client_id = (
        os.getenv("SPOTIFY_CLIENT_ID")
        or os.getenv("CLIENTID")
        or os.getenv("CLIENDID")
        or os.getenv("CLIENT_ID")
        or ""
    ).strip()
    client_secret = (
        os.getenv("SPOTIFY_CLIENT_SECRET")
        or os.getenv("CLIENTSECRET")
        or os.getenv("CLIENT_SECRET")
        or ""
    ).strip()
    raw_playlist_id = (
        os.getenv("SPOTIFY_PLAYLIST_ID")
        or os.getenv("PLAYLISTID")
        or os.getenv("PLAYLIST_ID")
        or ""
    ).strip()

    missing = []
    if not client_id:
        missing.append("SPOTIFY_CLIENT_ID / CLIENTID")
    if not client_secret:
        missing.append("SPOTIFY_CLIENT_SECRET / CLIENTSECRET")
    if not raw_playlist_id:
        missing.append("SPOTIFY_PLAYLIST_ID / PLAYLISTID")

    if missing:
        logger.error(
            "Отсутствуют обязательные переменные окружения: %s. "
            "Убедитесь, что они указаны в .env файле или GitHub Secrets.",
            ", ".join(missing),
        )
        sys.exit(1)

    playlist_id = clean_playlist_id(raw_playlist_id)
    return client_id, client_secret, playlist_id


def init_spotify_client(client_id: str, client_secret: str) -> spotipy.Spotify:
    """Инициализирует клиент Spotipy с авторизацией Client Credentials."""
    try:
        auth_manager = SpotifyClientCredentials(
            client_id=client_id,
            client_secret=client_secret,
        )
        sp = spotipy.Spotify(
            auth_manager=auth_manager,
            requests_timeout=15,
            retries=3,
        )
        return sp
    except Exception as exc:
        logger.error("Ошибка при инициализации Spotify клиента: %s", exc)
        sys.exit(1)


def parse_track_item(item: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """
    Парсит отдельный элемент ответа playlist_items.
    Корректно обрабатывает:
    - Удалённые/недоступные треки (track is None)
    - Локальные файлы (track.is_local == True)
    - Треки с несколькими артистами
    """
    if not item or not isinstance(item, dict):
        return None

    track = item.get("track")
    if not track or not isinstance(track, dict):
        # Трек удален или недоступен в регионе
        return None

    # Исполнители (может быть несколько)
    raw_artists = track.get("artists")
    artists_list = raw_artists if isinstance(raw_artists, list) else []
    artist_names = [
        artist.get("name", "").strip()
        for artist in artists_list
        if isinstance(artist, dict) and artist.get("name")
    ]
    artists_str = ", ".join(artist_names) if artist_names else "Unknown Artist"

    # Название трека
    track_name = track.get("name") or "Unknown Track"

    # Альбом и дата релиза
    raw_album = track.get("album")
    album_data = raw_album if isinstance(raw_album, dict) else {}
    album_name = album_data.get("name") or ""
    release_date = album_data.get("release_date") or ""

    # ISRC (международный стандартный номер аудиозаписи)
    raw_ids = track.get("external_ids")
    external_ids = raw_ids if isinstance(raw_ids, dict) else {}
    isrc = external_ids.get("isrc") or ""

    # Внешняя ссылка и URI
    raw_urls = track.get("external_urls")
    external_urls = raw_urls if isinstance(raw_urls, dict) else {}
    spotify_url = external_urls.get("spotify") or ""
    spotify_uri = track.get("uri") or ""

    # Дата добавления в плейлист
    added_at = item.get("added_at") or ""

    # Если трек локальный, укажем это в URI/URL при отсутствии ссылки
    if track.get("is_local"):
        if not spotify_url:
            spotify_url = "local-file"

    return {
        "Artist(s)": artists_str,
        "Track Name": track_name,
        "Album": album_name,
        "Release Date": release_date,
        "ISRC": isrc,
        "Spotify URL": spotify_url,
        "Spotify URI": spotify_uri,
        "Added At": added_at,
    }


def fetch_all_tracks(sp: spotipy.Spotify, playlist_id: str) -> List[Dict[str, str]]:
    """
    Выполняет полную пагинацию по плейлисту Spotify и собирает все треки.
    """
    logger.info("Запрашиваем треки из плейлиста ID: %s...", playlist_id)

    parsed_tracks: List[Dict[str, str]] = []
    total_items_fetched = 0
    skipped_items = 0
    offset = 0
    limit = 100

    try:
        response = sp.playlist_items(
            playlist_id=playlist_id,
            limit=limit,
            offset=offset,
            additional_types=("track",),
        )
    except Exception as exc:
        logger.error("Не удалось получить плейлист '%s': %s", playlist_id, exc)
        sys.exit(1)

    playlist_total = response.get("total", "неизвестно") if response else "неизвестно"
    logger.info("Общее количество треков по данным Spotify API: %s", playlist_total)

    while response:
        items = response.get("items") or []
        batch_count = len(items)
        total_items_fetched += batch_count

        for item in items:
            parsed = parse_track_item(item)
            if parsed:
                parsed_tracks.append(parsed)
            else:
                skipped_items += 1

        logger.info(
            "Обработано %d элементов (всего успешно спарсено: %d, пропущено: %d)",
            total_items_fetched,
            len(parsed_tracks),
            skipped_items,
        )

        if response.get("next"):
            try:
                response = sp.next(response)
            except Exception as exc:
                logger.error(
                    "Ошибка при переходе на следующую страницу пагинации: %s. "
                    "Прерываем процесс, чтобы не перезаписать бэкап неполными данными.",
                    exc,
                )
                sys.exit(1)
        else:
            break

    logger.info(
        "Пагинация завершена. Всего получено записей: %d, валидных треков: %d, пропущено: %d",
        total_items_fetched,
        len(parsed_tracks),
        skipped_items,
    )

    if isinstance(playlist_total, int) and playlist_total > 0 and len(parsed_tracks) == 0:
        logger.error(
            "Spotify вернул total=%d треков, но ни один трек не был успешно спарсен. "
            "Отмена сохранения во избежание перезаписи бэкапа пустыми данными.",
            playlist_total,
        )
        sys.exit(1)

    return parsed_tracks


def save_to_csv(tracks: List[Dict[str, str]], output_path: str = DEFAULT_OUTPUT_PATH) -> None:
    """
    Сохраняет список треков в CSV файл в кодировке utf-8-sig.
    """
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    try:
        with open(output_path, mode="w", newline="", encoding="utf-8-sig") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(tracks)
        logger.info("Успешно сохранено %d треков в файл: '%s'", len(tracks), output_path)
    except Exception as exc:
        logger.error("Ошибка при сохранении в CSV '%s': %s", output_path, exc)
        sys.exit(1)


def main() -> None:
    start_time = time.time()
    logger.info("=== Запуск резервного копирования плейлиста Spotify ===")

    client_id, client_secret, playlist_id = validate_environment()
    sp = init_spotify_client(client_id, client_secret)

    tracks = fetch_all_tracks(sp, playlist_id)
    save_to_csv(tracks, DEFAULT_OUTPUT_PATH)

    elapsed_time = time.time() - start_time
    logger.info("=== Резервное копирование завершено за %.2f сек ===", elapsed_time)


if __name__ == "__main__":
    main()
