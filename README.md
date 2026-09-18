# Spotify Playlist Autonomous Backup 🎵🔄

Полностью автономный ежедневный бэкап вашего плейлиста Spotify в этот Git-репозиторий с использованием **GitHub Actions** и **Python** (`spotipy`).

Данные сохраняются в файл `backups/playlist.csv` в кодировке `utf-8-sig` (с BOM для корректного отображения спецсимволов и кириллицы в Microsoft Excel).

---

## 📋 Экспортируемые колонки

| Колонка | Описание |
|---|---|
| `Artist(s)` | Имя исполнителя (или список через запятую, если их несколько) |
| `Track Name` | Название композиции |
| `Album` | Название альбома |
| `Release Date` | Дата релиза альбома/трека |
| `ISRC` | Международный стандартный номер аудиозаписи (если доступен) |
| `Spotify URL` | Прямая веб-ссылка на трек |
| `Spotify URI` | Внутренний URI трека в Spotify |
| `Added At` | Дата и время добавления трека в плейлист (UTC) |

---

## 🚀 Пошаговая инструкция по настройке

### Шаг 1. Получение ключей Spotify (Client ID и Client Secret)

1. Перейдите на [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) и авторизуйтесь под своим аккаунтом.
2. Нажмите кнопку **Create app**.
3. Заполните обязательные поля:
   - **App name**: например, `Spotify Backup Bot`
   - **App description**: например, `Automated playlist backup`
   - **Redirect URIs**: укажите `http://localhost:8888/callback` (для Client Credentials flow он не используется, но Spotify требует заполнить это поле).
   - Отметьте чекбокс согласия с условиями использования (**Developer Terms of Service**) и нажмите **Save**.
4. На странице созданного приложения перейдите в **Settings**:
   - Скопируйте значение **Client ID**.
   - Нажмите **View client secret** и скопируйте **Client Secret**.

---

### Шаг 2. Как получить ID плейлиста

1. Откройте приложение Spotify (десктоп, веб или мобильное).
2. Откройте нужный плейлист, нажмите на иконку с тремя точками `...` -> **Share** -> **Copy link to playlist**.
3. Скопированная ссылка имеет вид:
   ```text
   https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=1234567890abcdef
   ```
   - Идентификатор плейлиста — это строка между `/playlist/` и знаком `?`:
     `37i9dQZF1DXcBWIGoYBM5M`.
   - *Примечание:* скрипт `backup.py` умеет автоматически извлекать чистый ID как из полной ссылки, так и из URI вида `spotify:playlist:37i9dQZF1DXcBWIGoYBM5M`.

> ⚠️ **Важно:** Плейлист должен быть **публичным** (Public) либо доступен по ссылке, так как режим Client Credentials не авторизует конкретного пользователя, а получает доступ к общедоступным ресурсам Spotify.

---

### Шаг 3. Добавление секретов в GitHub Actions

1. Перейдите в ваш GitHub-репозиторий.
2. Откройте вкладку **Settings** -> в боковом меню выберите **Secrets and variables** -> **Actions**.
3. В блоке **Repository secrets** нажмите кнопку **New repository secret** и добавьте 3 переменные:

| Имя секрета | Значение |
|---|---|
| `SPOTIFY_CLIENT_ID` | Ваш Client ID из Шага 1 |
| `SPOTIFY_CLIENT_SECRET` | Ваш Client Secret из Шага 1 |
| `SPOTIFY_PLAYLIST_ID` | ID или ссылка на плейлист из Шага 2 |

---

### Шаг 4. Настройка прав для GitHub Actions (Permissions)

По умолчанию GitHub Actions не может коммитить изменения в репозиторий. Чтобы разрешить сохранение CSV-файла:

1. Перейдите в **Settings** -> боковое меню **Actions** -> **General**.
2. Прокрутите страницу вниз до раздела **Workflow permissions**.
3. Выберите пункт **Read and write permissions**.
4. Нажмите кнопку **Save**.

---

## ⚙️ Как работает автоматизация

- **Расписание (Cron):** Workflow запускается автоматически каждый день в `04:00 UTC` (`07:00 МСК`).
- **Умный коммит:** Если за прошедшие сутки треки в плейлисте не изменились, коммит не создается и push не выполняется.
- **Ручной запуск (Тестирование):**
  1. Перейдите во вкладку **Actions** в репозитории.
  2. В левой колонке выберите workflow **Spotify Playlist Backup**.
  3. Нажмите кнопку справа **Run workflow** -> выберите ветку `main` -> нажмите зеленую кнопку **Run workflow**.

---

## 💻 Локальный запуск (опционально)

Для тестирования скрипта на локальном компьютере:

1. Клонируйте репозиторий и создайте виртуальное окружение:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux / macOS:
   source .venv/bin/activate
   ```

2. Установите зависимости:
   ```bash
   pip install -r requirements.txt
   ```

3. Создайте файл `.env` на основе примера:
   ```bash
   # Windows (PowerShell):
   Copy-Item .env.example .env
   # Linux / macOS:
   cp .env.example .env
   ```

4. Заполните `.env` вашими реальными значениями:
   ```env
   SPOTIFY_CLIENT_ID=ваш_client_id
   SPOTIFY_CLIENT_SECRET=ваш_client_secret
   SPOTIFY_PLAYLIST_ID=ваш_playlist_id
   ```

5. Запустите скрипт:
   ```bash
   python backup.py
   ```
   Файл будет сохранён в `backups/playlist.csv`.
