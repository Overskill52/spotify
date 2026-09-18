import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

# Мокаем spotipy в sys.modules, если библиотека еще не установлена в окружении
if "spotipy" not in sys.modules:
    mock_spotipy = MagicMock()
    mock_spotipy_oauth2 = MagicMock()
    mock_spotipy.oauth2 = mock_spotipy_oauth2
    sys.modules["spotipy"] = mock_spotipy
    sys.modules["spotipy.oauth2"] = mock_spotipy_oauth2

from backup import (
    CSV_COLUMNS,
    clean_playlist_id,
    fetch_all_tracks,
    parse_track_item,
    save_to_csv,
)


class TestSpotifyBackup(unittest.TestCase):
    def test_clean_playlist_id(self):
        # 1. Обычный ID
        self.assertEqual(clean_playlist_id("37i9dQZF1DXcBWIGoYBM5M"), "37i9dQZF1DXcBWIGoYBM5M")

        # 2. Ссылка с query параметрами
        self.assertEqual(
            clean_playlist_id("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=abcdef123456"),
            "37i9dQZF1DXcBWIGoYBM5M",
        )

        # 3. Spotify URI
        self.assertEqual(
            clean_playlist_id("spotify:playlist:37i9dQZF1DXcBWIGoYBM5M"),
            "37i9dQZF1DXcBWIGoYBM5M",
        )

        # 4. Ссылка с пробелами
        self.assertEqual(
            clean_playlist_id("  https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M  "),
            "37i9dQZF1DXcBWIGoYBM5M",
        )

        # 5. Региональная ссылка с префиксом языка (например, intl-ru)
        self.assertEqual(
            clean_playlist_id("https://open.spotify.com/intl-ru/playlist/37i9dQZF1DXcBWIGoYBM5M?si=abcdef"),
            "37i9dQZF1DXcBWIGoYBM5M",
        )

    def test_parse_track_item_normal(self):
        raw_item = {
            "added_at": "2023-01-15T12:00:00Z",
            "track": {
                "name": "Starboy",
                "artists": [{"name": "The Weeknd"}, {"name": "Daft Punk"}],
                "album": {
                    "name": "Starboy",
                    "release_date": "2016-11-25",
                },
                "external_ids": {"isrc": "USUM71607007"},
                "external_urls": {"spotify": "https://open.spotify.com/track/7MXVkk9YM5IZvgfqWviFva"},
                "uri": "spotify:track:7MXVkk9YM5IZvgfqWviFva",
                "is_local": False,
            },
        }
        parsed = parse_track_item(raw_item)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["Artist(s)"], "The Weeknd, Daft Punk")
        self.assertEqual(parsed["Track Name"], "Starboy")
        self.assertEqual(parsed["Album"], "Starboy")
        self.assertEqual(parsed["Release Date"], "2016-11-25")
        self.assertEqual(parsed["ISRC"], "USUM71607007")
        self.assertEqual(parsed["Spotify URL"], "https://open.spotify.com/track/7MXVkk9YM5IZvgfqWviFva")
        self.assertEqual(parsed["Spotify URI"], "spotify:track:7MXVkk9YM5IZvgfqWviFva")
        self.assertEqual(parsed["Added At"], "2023-01-15T12:00:00Z")

    def test_parse_track_item_edge_cases(self):
        # 1. Удаленный / недоступный трек (track is None)
        self.assertIsNone(parse_track_item({"added_at": "2023-01-01T00:00:00Z", "track": None}))

        # 2. Невалидная структура элемента
        self.assertIsNone(parse_track_item({}))
        self.assertIsNone(parse_track_item(None))

        # 3. Локальный файл (отсутствуют внешние id и url)
        local_item = {
            "added_at": "2023-02-01T10:00:00Z",
            "track": {
                "name": "My Local Recording",
                "artists": [{"name": "Local Band"}],
                "album": {"name": "Demo"},
                "is_local": True,
                "uri": "spotify:local:Local+Band:Demo:My+Local+Recording:180",
            },
        }
        parsed_local = parse_track_item(local_item)
        self.assertIsNotNone(parsed_local)
        self.assertEqual(parsed_local["Artist(s)"], "Local Band")
        self.assertEqual(parsed_local["Track Name"], "My Local Recording")
        self.assertEqual(parsed_local["ISRC"], "")
        self.assertEqual(parsed_local["Spotify URL"], "local-file")

        # 4. Трек без исполнителя или с пустыми полями
        empty_track_item = {
            "added_at": "",
            "track": {
                "name": "",
                "artists": [],
            },
        }
        parsed_empty = parse_track_item(empty_track_item)
        self.assertIsNotNone(parsed_empty)
        self.assertEqual(parsed_empty["Artist(s)"], "Unknown Artist")
        self.assertEqual(parsed_empty["Track Name"], "Unknown Track")

    def test_save_to_csv_utf8_sig(self):
        tracks = [
            {
                "Artist(s)": "Кино, Виктор Цой",
                "Track Name": "Группа крови",
                "Album": "Группа крови",
                "Release Date": "1988",
                "ISRC": "RUAAA0000001",
                "Spotify URL": "https://open.spotify.com/track/test",
                "Spotify URI": "spotify:track:test",
                "Added At": "2023-05-10T14:30:00Z",
            }
        ]

        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
            tmp_path = tmp.name

        try:
            save_to_csv(tracks, tmp_path)

            # Проверяем наличие UTF-8 BOM (\xef\xbb\xbf)
            with open(tmp_path, "rb") as f:
                raw_bytes = f.read()
                self.assertTrue(raw_bytes.startswith(b"\xef\xbb\xbf"))

            # Проверяем чтение с utf-8-sig
            with open(tmp_path, "r", encoding="utf-8-sig") as f:
                content = f.read()
                self.assertIn("Кино, Виктор Цой", content)
                self.assertIn("Группа крови", content)
                for col in CSV_COLUMNS:
                    self.assertIn(col, content)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_fetch_all_tracks_pagination(self):
        mock_sp = MagicMock()

        # Первая страница (2 трека, есть next)
        page1 = {
            "total": 3,
            "next": "https://api.spotify.com/v1/playlists/test/tracks?offset=2&limit=2",
            "items": [
                {
                    "added_at": "2023-01-01T00:00:00Z",
                    "track": {"name": "Track 1", "artists": [{"name": "Artist 1"}]},
                },
                {
                    "added_at": "2023-01-02T00:00:00Z",
                    "track": {"name": "Track 2", "artists": [{"name": "Artist 2"}]},
                },
            ],
        }

        # Вторая страница (1 трек, next is None)
        page2 = {
            "total": 3,
            "next": None,
            "items": [
                {
                    "added_at": "2023-01-03T00:00:00Z",
                    "track": {"name": "Track 3", "artists": [{"name": "Artist 3"}]},
                }
            ],
        }

        mock_sp.playlist_items.return_value = page1
        mock_sp.next.return_value = page2

        results = fetch_all_tracks(mock_sp, "test_playlist_id")
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0]["Track Name"], "Track 1")
        self.assertEqual(results[2]["Track Name"], "Track 3")
        mock_sp.playlist_items.assert_called_once()
        mock_sp.next.assert_called_once_with(page1)

    def test_fetch_all_tracks_pagination_error_exits(self):
        mock_sp = MagicMock()
        page1 = {
            "total": 5,
            "next": "https://api.spotify.com/v1/playlists/test/tracks?offset=2&limit=2",
            "items": [
                {
                    "added_at": "2023-01-01T00:00:00Z",
                    "track": {"name": "Track 1", "artists": [{"name": "Artist 1"}]},
                }
            ],
        }
        mock_sp.playlist_items.return_value = page1
        mock_sp.next.side_effect = RuntimeError("Network timeout on Spotify API")

        with self.assertRaises(SystemExit) as ctx:
            fetch_all_tracks(mock_sp, "test_playlist_id")
        self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
