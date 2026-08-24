#!/usr/bin/env python3

import os
import re
import urllib.request
from datetime import date

SOURCES = {
    "fuechse": ("CALOVO_FUECHSE_URL", "Füchse Berlin"),
    "sc-magdeburg": ("CALOVO_SCM_URL", "SC Magdeburg"),
    "thw-kiel": ("CALOVO_THW_URL", "THW Kiel"),
    "sg-flensburg-handewitt": (
        "CALOVO_SG_URL",
        "SG Flensburg-Handewitt",
    ),
}

# Saison 2026/27
SEASON_START = date(2026, 7, 1)
SEASON_END = date(2027, 7, 1)

# Offensichtliche Nicht-Pflichtspiele ausschließen.
EXCLUDE_KEYWORDS = (
    "testspiel",
    "freundschaftsspiel",
    "freundschaft",
    "vorbereitung",
    "warm-up",
    "warmup",
)


def unfold(text):
    """Führt gefaltete ICS-Zeilen wieder zusammen."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    result = []

    for line in lines:
        if line.startswith((" ", "\t")) and result:
            result[-1] += line[1:]
        else:
            result.append(line)

    return result


def prop_value(event, name):
    """Liest den Wert einer ICS-Eigenschaft."""
    prefix = name.upper()

    for line in event:
        upper = line.upper()

        if upper.startswith(prefix + ":") or upper.startswith(prefix + ";"):
            if ":" in line:
                return line.split(":", 1)[1]

    return ""


def dtstart_date(event):
    """Ermittelt das Datum aus DTSTART."""
    value = prop_value(event, "DTSTART")
    match = re.match(r"(\d{8})", value)

    if not match:
        return None

    raw = match.group(1)

    return date(
        int(raw[:4]),
        int(raw[4:6]),
        int(raw[6:8]),
    )


def is_excluded(event):
    """Erkennt offensichtliche Test-/Freundschaftsspiele."""
    summary = prop_value(event, "SUMMARY").lower()
    description = prop_value(event, "DESCRIPTION").lower()

    text = f"{summary} {description}"

    return any(
        keyword in text
        for keyword in EXCLUDE_KEYWORDS
    )


def clean_event(event):
    """Bereinigt Calovo-spezifische Inhalte."""
    cleaned = []

    for line in event:
        # Calovo-Werbetext entfernen
        if line.upper().startswith("DESCRIPTION:"):
            continue

        # Calovo-Zusatz aus dem Spielort entfernen
        if line.upper().startswith("LOCATION:"):
            prefix, value = line.split(":", 1)

            if value.lower().startswith("calovo.de | "):
                value = value[12:]

            line = f"{prefix}:{value}"

        cleaned.append(line)

    return cleaned


def fetch(url):
    """Lädt einen ICS-Feed."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "HBL-WebCal/1.0"
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=30,
    ) as response:
        return response.read().decode("utf-8-sig")


def parse_events(text):
    """Zerlegt einen ICS-Kalender in einzelne VEVENTs."""
    lines = unfold(text)

    events = []
    current = None

    for line in lines:
        if line == "BEGIN:VEVENT":
            current = [line]

        elif line == "END:VEVENT" and current is not None:
            current.append(line)
            events.append(current)
            current = None

        elif current is not None:
            current.append(line)

    return events


def build_calendar(name, events):
    """Erzeugt einen sauberen ICS-Kalender."""

    header = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//MrMace17//HBL WebCal 2026-27//DE",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{name} – Pflichtspiele 2026/27",
        "X-WR-TIMEZONE:Europe/Berlin",
    ]

    body = []

    for event in events:
        body.extend(
    clean_event(event)
)

    return "\r\n".join(
        header
        + body
        + ["END:VCALENDAR", ""]
    )


def main():
    os.makedirs(
        "calendars",
        exist_ok=True,
    )

    for filename, (
        secret_name,
        club_name,
    ) in SOURCES.items():

        url = os.environ.get(secret_name)

        if not url:
            raise RuntimeError(
                f"Secret {secret_name} fehlt."
            )

        raw = fetch(url)

        selected = []
        seen_uids = set()

        for event in parse_events(raw):

            start = dtstart_date(event)

            # Nur Saison 2026/27
            if (
                start is None
                or not (
                    SEASON_START
                    <= start
                    < SEASON_END
                )
            ):
                continue

            # Offensichtliche Testspiele etc. entfernen
            if is_excluded(event):
                continue

            uid = prop_value(
                event,
                "UID",
            )

            if not uid:
                raise RuntimeError(
                    "Event ohne UID im Feed von "
                    f"{club_name}: "
                    f"{prop_value(event, 'SUMMARY')}"
                )

            # Doppelte Termine vermeiden
            if uid in seen_uids:
                continue

            seen_uids.add(uid)
            selected.append(event)

        # Chronologisch sortieren
        selected.sort(
            key=lambda event:
            prop_value(event, "DTSTART")
        )

        output = build_calendar(
            club_name,
            selected,
        )

        path = (
            f"calendars/{filename}.ics"
        )

        with open(
            path,
            "w",
            encoding="utf-8",
            newline="",
        ) as file:
            file.write(output)

        print(
            f"{club_name}: "
            f"{len(selected)} Pflichtspiele "
            f"für 2026/27 → {path}"
        )


if __name__ == "__main__":
    main()
