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
    return re.sub(r"\s+", " ", text or "").strip()


def extract_events():
    html = requests.get(
        START_URL,
        headers=HEADERS,
        timeout=30,
    )
    html.raise_for_status()

    soup = BeautifulSoup(html.text, "html.parser")

    print("=== ПОСИЛАННЯ KARABAS ===")

    links = soup.find_all("a", href=True)

    for link in links:
        href = link.get("href", "").strip()
        text = clean_text(link.get_text(" ", strip=True))

        if href:
            print(f"LINK: {href} | TEXT: {text}")

    print(f"Всього посилань: {len(links)}")
    print("=== КІНЕЦЬ ПОСИЛАНЬ ===")

    return []


def main():
    print("Перевірка KARABAS Wien...")

    old_events = load_events()

    found_events = extract_events()

    current_time = now_utc()

    new_events = []

    old_ids = {
        event.get("id")
        for event in old_events
        if event.get("id")
    }

    for event in found_events:
        if event["id"] not in old_ids:
            event["first_seen"] = current_time.isoformat()
            event["keep"] = False
            event["expires_at"] = (
                current_time + timedelta(days=2)
            ).isoformat()

            new_events.append(event)

    all_events = old_events + new_events

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
