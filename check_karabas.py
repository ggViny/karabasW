import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse

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

        if isinstance(data, list):
            return data

    except Exception as e:
        print(f"Не вдалося прочитати events.json: {e}")

    return []


def save_events(events):
    with open(EVENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)


def clean_text(text):
    return re.sub(r"\s+", " ", text or "").strip()


def absolute_url(href):
    return urljoin(BASE_URL, href)


def is_event_url(url):
    parsed = urlparse(url)

    if parsed.netloc != "wien.karabas.co":
        return False

    path = parsed.path.rstrip("/")

    if not path.startswith("/uk/"):
        return False

    slug = path[len("/uk/"):]

    if not slug:
        return False

    # Службові сторінки, які не є подіями
    excluded = {
        "kontserty",
        "teatry",
        "news",
        "contact",
        "about",
        "promoter",
        "logo",
        "offerta",
        "september",
        "october",
        "november",
        "december",
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
    }

    if slug in excluded:
        return False

    # Сторінки покупки квитків не є самими подіями
    if slug.endswith("/order"):
        return False

    if "/order/" in path:
        return False

    # Сторінки місяців
    if re.fullmatch(
        r"(september|october|november|december|january|february|"
        r"march|april|may|june|july|august)-\d{4}",
        slug,
        re.IGNORECASE,
    ):
        return False

    return True


def parse_event_page(url):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30,
        )
        response.raise_for_status()

    except Exception as e:
        print(f"Не вдалося відкрити {url}: {e}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    # -------------------------
    # Назва
    # -------------------------

    title = ""

    og_title = soup.find("meta", property="og:title")

    if og_title and og_title.get("content"):
        title = clean_text(og_title["content"])

    if not title:
        h1 = soup.find("h1")

        if h1:
            title = clean_text(h1.get_text(" ", strip=True))

    if not title and soup.title:
        title = clean_text(soup.title.get_text())

    # -------------------------
    # Постер
    # -------------------------

    image = ""

    og_image = soup.find("meta", property="og:image")

    if og_image and og_image.get("content"):
        image = absolute_url(og_image["content"])

    if not image:
        img = soup.find("img")

        if img and img.get("src"):
            image = absolute_url(img["src"])

    # -------------------------
    # Весь текст сторінки
    # -------------------------

    page_text = clean_text(
        soup.get_text(" ", strip=True)
    )

    # -------------------------
    # Дата і час
    #
    # Формат сайту:
    # 12/11/2026 20:00
    # -------------------------

    event_date = ""
    event_time = ""

    date_match = re.search(
        r"\b(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2})\b",
        page_text,
    )

    if date_match:
        event_date = date_match.group(1)
        event_time = date_match.group(2)

    # -------------------------
    # Місце
    #
    # На картці сайту:
    # Wien, Szene Wien
    # -------------------------

    venue = ""

    venue_match = re.search(
        r"\bWien,\s+(.+?)(?:\s+\d+\s*-\s*\d+\s*EUR|\s+\d+\s*EUR|\s*$)",
        page_text,
        re.IGNORECASE,
    )

    if venue_match:
        venue = clean_text(venue_match.group(1))

    # Спроба знайти місце окремо,
    # якщо попередній спосіб не спрацював
    if not venue:
        known_venues = [
            "Szene Wien",
            "Arena Wien",
            "Theater Akzent",
            "Das MuTh",
            "The Comedy Pub",
        ]

        for known_venue in known_venues:
            if known_venue.lower() in page_text.lower():
                venue = known_venue
                break

    # -------------------------
    # Якщо сторінка не схожа
    # на подію — пропускаємо
    # -------------------------

    if not title:
        return None

    if not event_date:
        print(f"Не знайдено дату: {url}")
        return None

    event_id = url.rstrip("/").split("/")[-1]

    return {
        "id": event_id,
        "title": title,
        "url": url,
        "image": image,
        "date": event_date,
        "time": event_time,
        "venue": venue,
    }


def extract_events():
    print("Завантаження KARABAS Wien...")

    try:
        response = requests.get(
            START_URL,
            headers=HEADERS,
            timeout=30,
        )
        response.raise_for_status()

    except Exception as e:
        print(f"Помилка завантаження KARABAS: {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    event_urls = set()

    # Збираємо всі посилання
    for link in soup.find_all("a", href=True):
        href = link.get("href", "").strip()

        if not href:
            continue

        url = absolute_url(href)

        if is_event_url(url):
            event_urls.add(url.rstrip("/"))

    print(f"Знайдено посилань на можливі події: {len(event_urls)}")

    events = []

    for url in sorted(event_urls):
        event = parse_event_page(url)

        if event:
            events.append(event)

            print(
                f"EVENT: {event['date']} {event['time']} | "
                f"{event['title']} | {event['venue']}"
            )

    return events


def main():
    print("Перевірка KARABAS Wien...")

    old_events = load_events()
    found_events = extract_events()

    current_time = now_utc()

    old_by_id = {
        event.get("id"): event
        for event in old_events
        if event.get("id")
    }

    new_events = []

    # -------------------------
    # Додаємо нові події
    # -------------------------

    for event in found_events:
        event_id = event["id"]

        if event_id in old_by_id:
            # Зберігаємо старі дані,
            # але оновлюємо інформацію про подію
            old_event = old_by_id[event_id]

            old_event.update({
                "title": event["title"],
                "url": event["url"],
                "image": event["image"],
                "date": event["date"],
                "time": event["time"],
                "venue": event["venue"],
            })

        else:
            event["first_seen"] = current_time.isoformat()

            # ⭐ За замовчуванням подія не закріплена
            event["keep"] = False

            # Через 2 дні прибираємо
            event["expires_at"] = (
                current_time + timedelta(days=2)
            ).isoformat()

            old_by_id[event_id] = event
            new_events.append(event)

    # -------------------------
    # Видаляємо прострочені
    # -------------------------

    active_events = []

    for event in old_by_id.values():

        # ⭐ Закріплені залишаються назавжди
        if event.get("keep") is True:
            active_events.append(event)
            continue

        expires_at = event.get("expires_at")

        if not expires_at:
            active_events.append(event)
            continue

        try:
            expires = datetime.fromisoformat(expires_at)

            if expires > current_time:
                active_events.append(event)

        except Exception:
            # Якщо дата пошкоджена —
            # не видаляємо подію
            active_events.append(event)

    # Новіші зверху
    active_events.sort(
        key=lambda x: x.get("first_seen", ""),
        reverse=True,
    )

    save_events(active_events)

    print()
    print("========== РЕЗУЛЬТАТ ==========")
    print(f"Знайдено подій: {len(found_events)}")
    print(f"Нових подій: {len(new_events)}")
    print(f"Активних подій: {len(active_events)}")
    print("events.json оновлено.")
    print("================================")


if __name__ == "__main__":
    main()
