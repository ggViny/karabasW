import json
import re
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://wien.karabas.co"
START_URL = "https://wien.karabas.co/uk/"

EVENTS_FILE = Path("events.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
    )
}


def now_utc():
    return datetime.now(timezone.utc)


def iso_now():
    return now_utc().isoformat()


def load_events():
    if not EVENTS_FILE.exists():
        return []

    try:
        with open(EVENTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_events(events):
    with open(EVENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)


def clean_text(text):
    return re.sub(r"\s+", " ", text or "").strip()


def make_id(url, title):
    value = f"{url}|{title}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def get_page(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()
    return response.text


def extract_events():
    html = get_page(START_URL)
    soup = BeautifulSoup(html, "html.parser")

    events = []

    # Знаходимо всі посилання на сторінки подій.
    links = soup.find_all("a", href=True)

    seen_urls = set()

    for link in links:
        href = link.get("href", "").strip()

        if not href:
            continue

        url = urljoin(BASE_URL, href)

        # Беремо тільки сторінки цього домену.
        if not url.startswith(BASE_URL):
            continue

        # Не беремо службові сторінки.
        if any(
            x in url
            for x in [
                "/uk/",
                "/en/",
                "/de/",
                "/login",
                "/search",
                "/help",
            ]
        ):
            continue

        # Поки що беремо URL, що виглядають як сторінки подій.
        if url.rstrip("/") == BASE_URL:
            continue

        if url in seen_urls:
            continue

        title = clean_text(link.get_text(" ", strip=True))

        # Посилання без назви не цікаві.
        if len(title) < 3:
            continue

        seen_urls.add(url)

        try:
            event_html = get_page(url)
            event_soup = BeautifulSoup(event_html, "html.parser")

            page_text = clean_text(event_soup.get_text(" ", strip=True))

            # Шукаємо зображення.
            image_url = ""

            image = event_soup.find(
                "meta",
                attrs={"property": "og:image"}
            )

            if image and image.get("content"):
                image_url = urljoin(BASE_URL, image["content"])

            if not image_url:
                image = event_soup.find("img")

                if image and image.get("src"):
                    image_url = urljoin(BASE_URL, image["src"])

            # Назву беремо з og:title, якщо є.
            og_title = event_soup.find(
                "meta",
                attrs={"property": "og:title"}
            )

            event_title = title

            if og_title and og_title.get("content"):
                event_title = clean_text(og_title["content"])

            event_id = make_id(url, event_title)

            events.append(
                {
                    "id": event_id,
                    "title": event_title,
                    "url": url,
                    "image": image_url,
                    "raw_text": page_text[:5000],
                }
            )

        except Exception as e:
            print(f"Не вдалося прочитати {url}: {e}")

    return events


def main():
    print("Перевірка KARABAS Wien...")

    old_events = load_events()
    old_ids = {event["id"] for event in old_events}

    found_events = extract_events()

    current_time = now_utc()

    new_events = []

    for event in found_events:

        if event["id"] not in old_ids:

            event["first_seen"] = current_time.isoformat()
            event["keep"] = False
            event["expires_at"] = (
                current_time + timedelta(days=2)
            ).isoformat()

            new_events.append(event)

    # Додаємо нові події.
    all_events = old_events + new_events

    # Видаляємо старі НЕзбережені події.
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

    print(f"Знайдено подій: {len(found_events)}")
    print(f"Нових подій: {len(new_events)}")
    print(f"Активних подій: {len(cleaned_events)}")


if __name__ == "__main__":
    main()
