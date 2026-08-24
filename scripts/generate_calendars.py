import os
import urllib.request
from pathlib import Path


# ============================================================
# KONFIGURATION
# ============================================================

CALENDARS = {
    "fuechse": {
        "name": "Füchse Berlin",
        "secret": "CALOVO_FUECHSE_URL",
    },
    "sc-magdeburg": {
        "name": "SC Magdeburg",
        "secret": "CALOVO_SCM_URL",
    },
    "thw-kiel": {
        "name": "THW Kiel",
        "secret": "CALOVO_THW_URL",
    },
    "sg-flensburg-handewitt": {
        "name": "SG Flensburg-Handewitt",
        "secret": "CALOVO_SG_URL",
    },
}


OUTPUT_DIR = Path("calendars")


# ============================================================
# EUROPA/BERLIN ZEITZONE
# ============================================================

VTIMEZONE = [
    "BEGIN:VTIMEZONE",
    "TZID:Europe/Berlin",
    "X-LIC-LOCATION:Europe/Berlin",

    "BEGIN:STANDARD",
    "DTSTART:20261025T030000",
    "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU",
    "TZOFFSETFROM:+0200",
    "TZOFFSETTO:+0100",
    "TZNAME:CET",
    "END:STANDARD",

    "BEGIN:DAYLIGHT",
    "DTSTART:20260329T020000",
    "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU",
    "TZOFFSETFROM:+0100",
    "TZOFFSETTO:+0200",
    "TZNAME:CEST",
    "END:DAYLIGHT",

    "END:VTIMEZONE",
]


# ============================================================
# FEED HERUNTERLADEN
# ============================================================

def download_feed(url):
    """Lädt einen Calovo-ICS-Feed herunter."""

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "HBL-WebCal-Updater/1.0"
        },
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read()

    # UTF-8 mit oder ohne BOM akzeptieren
    return data.decode("utf-8-sig")


# ============================================================
# ICS ZEILEN ENTFALTEN
# ============================================================

def unfold_ics(text):
    """
    Entfernt iCalendar-Folding.

    Nach RFC 5545 müssen gefaltete Zeilen vor der Verarbeitung
    wieder zusammengeführt werden.
    """

    text = text.replace("\r\n", "\n").replace("\r", "\n")

    lines = text.split("\n")

    unfolded = []

    for line in lines:
        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)

    return unfolded


# ============================================================
# VEVENTS EXTRAHIEREN
# ============================================================

def extract_events(text):
    """Extrahiert ausschließlich VEVENT-Blöcke aus dem Quellfeed."""

    lines = unfold_ics(text)

    events = []
    current_event = None

    for line in lines:

        if line.upper() == "BEGIN:VEVENT":
            current_event = ["BEGIN:VEVENT"]
            continue

        if line.upper() == "END:VEVENT":
            if current_event is not None:
                current_event.append("END:VEVENT")
                events.append(current_event)

            current_event = None
            continue

        if current_event is not None:
            current_event.append(line)

    return events


# ============================================================
# EVENT BEREINIGEN
# ============================================================

def clean_event(event):
    """
    Entfernt Calovo-spezifische Inhalte und bereitet das Event
    für unseren eigenen Kalender auf.

    Die Erinnerungen werden später in build_calendar()
    eingefügt.
    """

    cleaned = []

    for line in event:

        upper = line.upper()

        # Calovo-Werbetext entfernen
        if upper.startswith("DESCRIPTION:"):
            continue

        # Calovo-Link entfernen
        if upper.startswith("URL:"):
            continue

        # Calovo-Präfix beim Veranstaltungsort entfernen
        if upper.startswith("LOCATION:"):
            prefix, value = line.split(":", 1)

            if value.lower().startswith("calovo.de |"):
                value = value.split("|", 1)[1].strip()

            line = f"{prefix}:{value}"

        cleaned.append(line)

    return cleaned


# ============================================================
# REMINDER
# ============================================================

def add_alarms(lines):
    """
    Fügt zwei Erinnerungen vor END:VEVENT ein:

    - 6 Stunden vorher
    - 1 Stunde vorher
    """

    if not lines:
        return lines

    if lines[-1].upper() != "END:VEVENT":
        return lines

    # END:VEVENT entfernen
    lines = lines[:-1]

    lines.extend([
        "BEGIN:VALARM",
        "ACTION:DISPLAY",
        "DESCRIPTION:Spiel beginnt in 6 Stunden",
        "TRIGGER:-PT6H",
        "END:VALARM",

        "BEGIN:VALARM",
        "ACTION:DISPLAY",
        "DESCRIPTION:Spiel beginnt in 1 Stunde",
        "TRIGGER:-PT1H",
        "END:VALARM",

        "END:VEVENT",
    ])

    return lines


# ============================================================
# KALENDER ERZEUGEN
# ============================================================

def build_calendar(name, events):
    """Erzeugt einen vollständigen iCalendar-Feed."""

    calendar = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//MrMace17//HBL WebCal 2026-27//DE",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{name} - Pflichtspiele 2026/27",
        "X-WR-TIMEZONE:Europe/Berlin",
    ]

    calendar.extend(VTIMEZONE)

    for event in events:

        cleaned = clean_event(event)

        cleaned = add_alarms(cleaned)

        calendar.extend(cleaned)

    calendar.append("END:VCALENDAR")

    return calendar


# ============================================================
# KALENDER SPEICHERN
# ============================================================

def save_calendar(filename, lines):
    """Speichert den Kalender mit CRLF-Zeilenenden."""

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    output_file = OUTPUT_DIR / filename

    content = "\r\n".join(lines) + "\r\n"

    output_file.write_text(
        content,
        encoding="utf-8",
        newline=""
    )

    return output_file


# ============================================================
# EINEN VEREIN VERARBEITEN
# ============================================================

def generate_calendar(slug, config):
    """Lädt einen Vereinsfeed und erzeugt daraus unseren Kalender."""

    secret_name = config["secret"]
    name = config["name"]

    url = os.environ.get(secret_name)

    if not url:
        raise RuntimeError(
            f"GitHub Secret {secret_name} wurde nicht gefunden."
        )

    print(f"========================================")
    print(f"Verarbeite: {name}")
    print(f"========================================")

    print("Lade Calovo-Feed herunter...")

    feed = download_feed(url)

    print(f"Feed geladen: {len(feed)} Zeichen")

    events = extract_events(feed)

    print(f"Gefundene Spiele: {len(events)}")

    if not events:
        raise RuntimeError(
            f"Keine VEVENTs im Feed von {name} gefunden."
        )

    calendar = build_calendar(name, events)

    filename = f"{slug}.ics"

    output_file = save_calendar(filename, calendar)

    print(f"Kalender geschrieben: {output_file}")
    print(f"Reminder: 6 Stunden + 1 Stunde")


# ============================================================
# HAUPTPROGRAMM
# ============================================================

def main():

    print("========================================")
    print("HBL WebCal Generator 2026/27")
    print("========================================")

    for slug, config in CALENDARS.items():
        generate_calendar(slug, config)

    print("")
    print("========================================")
    print("Alle Kalender erfolgreich erzeugt.")
    print("========================================")


if __name__ == "__main__":
    main()
