"""
write_status.py - registra in status.json l'esito dell'ultimo controllo.

Gira nel workflow subito dopo lo scraper, che scrive il proprio log in
scraper.log. Il file status.json contiene:
  lastRunAt      quando e' finita l'ultima esecuzione (UTC)
  lastSuccessAt  quando l'ultimo controllo e' stato completo (UTC)
  outcome        "ok" oppure "partial"
  records        numero di richiami in data.json

Un controllo e' "partial" se nel log compaiono blocchi, fonti saltate o schede
rimaste per la prossima run: in quel caso lastSuccessAt NON avanza.
Le prove manuali con limite (SCRAPER_LIMIT) non sono controlli completi e non
toccano lo stato.

Limite noto: l'esito si ricava dai messaggi dello scraper. Se cambi quei
messaggi, aggiorna PARTIAL_MARKERS.
"""

import json
import os
import re
from datetime import datetime, timezone

LOG_PATH = "scraper.log"
STATUS_PATH = "status.json"
DATA_PATH = "data.json"

PARTIAL_MARKERS = (
    "il sito ci blocca",
    "bloccato (",
    "sitemap: bloccati",
    "restano per la prossima run",
    "saltata per errore imprevisto",
    "pagina elenco non raggiungibile",
    "(limite tempo/blocco)",
)


def leggi_json(percorso, default):
    try:
        with open(percorso, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return default


def main():
    if os.environ.get("SCRAPER_LIMIT", "").strip():
        print("Esecuzione con limite: non e' un controllo completo, stato non aggiornato.")
        return

    try:
        with open(LOG_PATH, encoding="utf-8", errors="replace") as f:
            log = f.read().lower()
    except FileNotFoundError:
        print("scraper.log non trovato: stato non aggiornato.")
        return

    if not re.search(r"salvati \d+ richiami", log):
        print("Il log non riporta il salvataggio finale: stato non aggiornato.")
        return

    outcome = "partial" if any(m in log for m in PARTIAL_MARKERS) else "ok"
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    precedente = leggi_json(STATUS_PATH, {})
    dati = leggi_json(DATA_PATH, [])

    stato = {
        "lastRunAt": now,
        "lastSuccessAt": now if outcome == "ok" else precedente.get("lastSuccessAt"),
        "outcome": outcome,
        "records": len(dati) if isinstance(dati, list) else 0,
    }
    with open(STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump(stato, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"Stato registrato: {outcome} ({stato['records']} richiami)")


if __name__ == "__main__":
    main()
