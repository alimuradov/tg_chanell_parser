import os
import requests
import urllib.parse

YANDEX_API_TOKEN = os.getenv('YANDEX_API_TOKEN')
BASE_DISK_URL = 'https://cloud-api.yandex.net/v1/disk'

HEADERS = {
    'Authorization': f'OAuth {YANDEX_API_TOKEN}'
}


def get_file_link(file_path):
    # Путь на диске
    filename = os.path.basename(file_path)
    yandex_path = f"AbdulliniApp/{filename}"
    encoded_path = urllib.parse.quote(yandex_path)

    # Шаг 1: Запросить URL для загрузки
    upload_url = f"{BASE_DISK_URL}/resources/upload?path={encoded_path}&overwrite=true"
    resp = requests.get(upload_url, headers=HEADERS)
    if resp.status_code != 200:
        raise Exception(f"Ошибка получения upload URL: {resp.status_code} {resp.text}")

    href = resp.json().get('href')
    if not href:
        raise Exception("Не удалось получить ссылку загрузки")

    # Шаг 2: Загрузить файл
    with open(file_path, 'rb') as f:
        upload_resp = requests.put(href, files={'file': f} if 'file' in href else None, data=f if 'file' not in href else None)
    if upload_resp.status_code not in (201, 202):
        raise Exception(f"Ошибка загрузки файла: {upload_resp.status_code} {upload_resp.text}")

    # Шаг 3: Сделать файл публичным
    publish_url = f"{BASE_DISK_URL}/resources/publish?path={encoded_path}"
    pub_resp = requests.put(publish_url, headers=HEADERS)
    if pub_resp.status_code not in (200, 202):
        raise Exception(f"Ошибка публикации файла: {pub_resp.status_code} {pub_resp.text}")

    # Шаг 4: Получить публичную ссылку
    meta_url = f"{BASE_DISK_URL}/resources?path={encoded_path}&fields=public_url"
    meta_resp = requests.get(meta_url, headers=HEADERS)
    if meta_resp.status_code != 200:
        raise Exception(f"Ошибка получения метаданных: {meta_resp.status_code} {meta_resp.text}")

    public_url = meta_resp.json().get('public_url')
    if not public_url:
        raise Exception("Публичная ссылка не найдена")
    return public_url
