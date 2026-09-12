import json
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://wien.karabas.co"
EVENTS_FILE = Path("events.json")

EVENT_LIST_URLS = [
    "https://wien.karabas.co/uk/kontserty/",
    "https://wien.karabas.co/uk/teatry/",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
    )
}


def now_utc():
    return datetime.now(timezone.utc)


def load_events():
    if not EVENTS_FILE.exists():
        return []

    try:
        with open(EVENTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def save_events(events):
    with open(EVENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)


def clean_text(text):
    return " ".join((text or "").split())


def make_id(url):
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def get_page(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()
    return response.text


def extract_image(soup):
    image = soup.find(
        "meta",
        attrs={"property": "og:image"}
    )

    if image and image.get("content"):
        return urljoin(BASE_URL, image["content"])

    image = soup.find("img")

    if image and image.get("src"):
        return urljoin(BASE_URL, image["src"])

    return ""


def extract_event_details(url):
    html = get_page(url)
    soup = BeautifulSoup(html, "html.parser")

    title = ""

    og_title = soup.find(
        "meta",
        attrs={"property": "og:title"}
    )

    if og_title and og_title.get("content"):
        title = clean_text(og_title["content"])

    if not title and soup.find("h1"):
        title = clean_text(soup.find("h1").get_text())

    page_text = clean_text(
        soup.get_text(" ", strip=True)
    )

    image_url = extract_image(soup)

    # Шукаємо дату/час у тексті сторінки.
    event_date = ""
    event_time = ""

    # Український формат, наприклад:
    # 12 листопада 2026, 20:00
    import re

    date_match = re.search(
        r"(\d{1,2}\s+[а-яА-ЯіїєґІЇЄҐ]+\s+\d{4})\s*,\s*(\d{1,2}:\d{2})",
        page_text
    )

    if date_match:
        event_date = date_match.group(1)
        event_time = date_match.group(2)

    # Шукаємо Wien + місце проведення.
    venue = ""

    lines = [
        clean_text(x)
        for x in soup.stripped_strings
    ]

    for i, line in enumerate(lines):
        if line == "Wien" and i + 1 < len(lines):
            venue = lines[i + 1]
            break

    return {
        "title": title,
        "image": image_url,
        "date": event_date,
        "time": event_time,
        "venue": venue,
        "raw_text": page_text[:5000],
    }


def extract_events():
    events = []
    seen_urls = set()

    for list_url in EVENT_LIST_URLS:
        print(f"Перевіряю: {list_url}")

        html = get_page(list_url)
        soup = BeautifulSoup(html, "html.parser")

        # На сторінці списку подій шукаємо посилання,
        # що ведуть на wien.karabas.co/uk/...,
        # але не на самі розділи.
        for link in soup.find_all("a", href=True):
            href = link.get("href", "").strip()

            if not href:
                continue

            url = urljoin(BASE_URL, href).split("#")[0]

            if not url.startswith(BASE_URL + "/uk/"):
                continue

            if url.rstrip("/") in [
                BASE_URL + "/uk",
                BASE_URL + "/uk/kontserty",
                BASE_URL + "/uk/teatry",
            ]:
                continue

            if url in seen_urls:
                continue

            title_from_link = clean_text(
                link.get_text(" ", strip=True)
            )

            # Кнопки "КУПИТИ", міста та інше відкидаємо.
            if title_from_link.upper() in [
                "КУПИТИ",
                "КУПИТЬ",
                "BUY",
            ]:
                continue

            try:
                details = extract_event_details(url)

                if not details["title"]:
                    continue

                # Подія повинна мати дату.
                if not details["date"]:
                    continue

                seen_urls.add(url)

                event = {
                    "id": make_id(url),
                    "title": details["title"],
                    "url": url,
                    "image": details["image"],
                    "date": details["date"],
                    "time": details["time"],
                    "venue": details["venue"],
                    "raw_text": details["raw_text"],
                }

                events.append(event)

                print(
                    f"  Знайдено: {event['title']} | "
                    f"{event['date']} {event['time']}"
                )

            except Exception as e:
                print(f"  Помилка {url}: {e}")

    return events


def main():
    print("=== Перевірка KARABAS Wien ===")

    old_events = load_events()
    old_by_id = {
        event.get("id"): event
        for event in old_events
        if event.get("id")
    }

    found_events = extract_events()

    current_time = now_utc()

    all_events = []

    for event in found_events:
        event_id = event["id"]

        if event_id in old_by_id:
            old = old_by_id[event_id]

            # Зберігаємо інформацію про перше виявлення.
            event["first_seen"] = old.get(
                "first_seen",
                current_time.isoformat()
            )

            event["keep"] = old.get("keep", False)

            event["expires_at"] = old.get(
                "expires_at",
                (
                    current_time + timedelta(days=2)
                ).isoformat()
            )

        else:
            event["first_seen"] = current_time.isoformat()
            event["keep"] = False
            event["expires_at"] = (
                current_time + timedelta(days=2)
            ).isoformat()

            print(
                f"  🆕 НОВА ПОДІЯ: {event['title']}"
            )

        all_events.append(event)

    # Додаємо закріплені старі події,
    # навіть якщо вони тимчасово не показуються
    # у списку KARABAS.
    found_ids = {
        event["id"]
        for event in found_events
    }

    for old in old_events:
        if (
            old.get("keep") is True
            and old.get("id") not in found_ids
        ):
            all_events.append(old)

    # Видаляємо незакріплені події після 2 днів.
    cleaned_events = []

    for event in all_events:
        if event.get("keep") is True:
            cleaned_events.append(event)
            continue

        expires_at = event.get("expires_at")

        if not expires_at:
            cleaned_events.append(event)
            continue

        try:
            expires = datetime.fromisoformat(expires_at)

            if expires > current_time:
                cleaned_events.append(event)

        except Exception:
            cleaned_events.append(event)

    save_events(cleaned_events)

    print()
    print(f"Знайдено подій: {len(found_events)}")
    print(f"Активних подій: {len(cleaned_events)}")
    print(f"Файл: {EVENTS_FILE}")


if __name__ == "__main__":
    main()
