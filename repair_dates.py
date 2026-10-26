import re
from datetime import date

MONTHS = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
    "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
    "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}


def to_iso(value):
    if not isinstance(value, str):
        return ""
    value = " ".join(value.split()).lower()
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", value)
    if match:
        year, month, day = map(int, match.groups())
    else:
        match = re.fullmatch(r"(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{4})", value)
        if match:
            day, month, year = map(int, match.groups())
        else:
            match = re.fullmatch(r"(\d{1,2})(?:\s*/\s*|\s+)([a-z]+)(?:\s*/\s*|\s+)(\d{4})", value)
            if not match:
                return ""
            day, month_name, year = match.groups()
            day, year = int(day), int(year)
            month = MONTHS.get(month_name)
            if month is None:
                return ""
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return ""


def repair_records(records):
    if not isinstance(records, list) or any(not isinstance(r, dict) for r in records):
        raise ValueError("L'archivio deve essere un array di oggetti")
    repaired = 0
    for record in records:
        if record.get("published"):
            continue
        fields = record.get("campi")
        fields = fields if isinstance(fields, dict) else {}
        candidates = [record.get("noticeDate"), fields.get("data pubblicazione")]
        for candidate in candidates:
            parsed = to_iso(candidate)
            if parsed:
                record["published"] = parsed
                repaired += 1
                break
    return repaired


def main():
    import json
    import os
    from pathlib import Path

    path = Path("data.json")
    with path.open(encoding="utf-8") as stream:
        records = json.load(stream)
    repaired = repair_records(records)
    if repaired:
        records.sort(key=lambda r: r.get("published") or "", reverse=True)
        temporary = path.with_suffix(".json.tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(records, stream, ensure_ascii=False, separators=(",", ":"))
            stream.write("\n")
        os.replace(temporary, path)
    print(f"Date recuperate dai dati locali: {repaired}")
    print(f"Schede ancora senza data: {sum(not r.get('published') for r in records)}")
    print("Nessuna nuova verifica della fonte: stato Ultimo controllo invariato.")


if __name__ == "__main__":
    main()
