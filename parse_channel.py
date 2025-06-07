import os
import shutil
from telethon.sync import TelegramClient
from telethon.tl.functions.messages import GetHistoryRequest
from datetime import datetime
import pytz
import requests
import json

from utils.yandex_disk import get_file_link

# 🔐 Конфигурация
api_id = int(os.getenv('API_ID'))
api_hash = os.getenv('API_HASH')
channel_username = os.getenv('TG_CHANNEL')
n8n_webhook_url = os.getenv('N8N_WEBHOOK_URL')

# 📁 Лог уже обработанных постов
parsed_log_path = "parsed_posts.json"
parsed_ids = {}
if os.path.exists(parsed_log_path):
    with open(parsed_log_path, "r", encoding="utf-8") as f:
        try:
            parsed_data = json.load(f)
            # Если это старый формат (просто список), оборачиваем в словарь
            if isinstance(parsed_data, list):
                parsed_ids[channel_username] = parsed_data
            elif isinstance(parsed_data, dict):
                parsed_ids = parsed_data
        except json.JSONDecodeError:
            print("⚠️ Файл parsed_posts.json поврежден или пуст, создаем заново.")
        
channel_parsed_ids = set(parsed_ids.get(channel_username, []))        

# 📅 Ограничение по дате
date_cutoff = datetime(2025, 5, 19)
date_cutoff = pytz.utc.localize(date_cutoff)

# 📁 Папка для временных файлов
base_files_path = "./files"
os.makedirs(base_files_path, exist_ok=True)

# 📡 Основной процесс
with TelegramClient('session_name', api_id, api_hash) as client:
    channel = client.get_entity(channel_username)
    offset_id = 0
    limit = 100
    total_count_limit = 0  # 0 = без ограничения
    all_new_ids = []

    while True:
        history = client(GetHistoryRequest(
            peer=channel,
            limit=limit,
            offset_date=None,
            offset_id=offset_id,
            max_id=0,
            min_id=0,
            add_offset=0,
            hash=0
        ))

        messages = history.messages
        if not messages:
            break

        grouped_albums = {}

        for msg in messages:
            if msg.grouped_id:
                grouped_albums.setdefault(msg.grouped_id, []).append(msg)
            else:
                grouped_albums[msg.id] = [msg]

        for group_id, group_msgs in grouped_albums.items():
            first_msg = group_msgs[0]
            if first_msg.id in channel_parsed_ids:
                continue

            if first_msg.date < date_cutoff:
                continue

            post_folder = os.path.join(base_files_path, f"post_{first_msg.id}")
            os.makedirs(post_folder, exist_ok=True)

            photo_paths = []
            video_paths = []
            message_text = ""

            for msg in group_msgs:
                if msg.message and not message_text:
                    message_text = msg.message

                # Фото
                if msg.media and msg.photo:
                    filename = f"photo_{msg.id}.jpg"
                    full_path = os.path.join(post_folder, filename)
                    try:
                        client.download_media(msg, file=full_path)
                        photo_paths.append(full_path)
                        print(f"📸 Скачано фото: {filename}")
                    except Exception as e:
                        print(f"❌ Ошибка скачивания фото {msg.id}: {e}")

                # Видео
                elif msg.media and getattr(msg.media, 'document', None):
                    mime_type = msg.media.document.mime_type
                    if mime_type and mime_type.startswith("video/"):
                        filename = f"video_{msg.id}.mp4"
                        full_path = os.path.join(post_folder, filename)
                        try:
                            client.download_media(msg, file=full_path)
                            video_paths.append(full_path)
                            print(f"🎞️ Скачано видео: {filename}")
                        except Exception as e:
                            print(f"❌ Ошибка скачивания видео {msg.id}: {e}")

            # ☁️ Загрузка файлов на Яндекс.Диск
            photo_links = []
            video_links = []

            for file_path in photo_paths:
                try:
                    link = get_file_link(file_path)
                    photo_links.append(link)
                    print(f"☁️ Фото на Диске: {link}")
                except Exception as e:
                    print(f"❌ Ошибка загрузки фото: {e}")

            for file_path in video_paths:
                try:
                    link = get_file_link(file_path)
                    video_links.append(link)
                    print(f"☁️ Видео на Диске: {link}")
                except Exception as e:
                    print(f"❌ Ошибка загрузки видео: {e}")

            # 📤 Отправка в Webhook
            data = {
                'id': first_msg.id,
                'text': message_text or "",
                'date': first_msg.date.isoformat(),
                'link': f"https://t.me/{channel_username}/{first_msg.id}",
                'photos': photo_links,
                'videos': video_links
            }

            headers = {'Content-Type': 'application/json'}
            try:
                response = requests.post(n8n_webhook_url, json=data, headers=headers)
                print(f"📬 Ответ от Webhook: {response.status_code}")
                print("📝 Тело ответа:", response.json())
            except Exception as e:
                print(f"❌ Ошибка отправки в webhook: {e}")

            # 🧹 Очистка
            shutil.rmtree(post_folder)
            all_new_ids.append(first_msg.id)

        offset_id = messages[-1].id

    # 💾 Сохраняем ID уже обработанных постов
    channel_parsed_ids.update(all_new_ids)
    parsed_ids[channel_username] = list(channel_parsed_ids)

    with open(parsed_log_path, "w", encoding="utf-8") as f:
        json.dump(parsed_ids, f, ensure_ascii=False, indent=2)

    print(f"✅ Обработано и сохранено {len(all_new_ids)} новых постов.")
