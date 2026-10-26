"""
inject_data.py - incolla i dati e lo stato dell'ultimo controllo dentro index.html.

Serve a tenere il sito autonomo: i dati vivono dentro l'HTML, quindi il file
funziona anche aperto con doppio clic, senza server e senza Python.
Questo script gira su GitHub Actions dopo lo scraper; per una prova locale:
  python scraper.py 5 && python write_status.py && python inject_data.py

Gestisce due blocchi, entrambi sostituiti in modo idempotente:
  /* DATI-INIZIO */ ... /* DATI-FINE */         const RECALLS (da data.json)
  <!-- STATO-INIZIO --> ... <!-- STATO-FINE -->  riga "Ultimo controllo"
                                                 (da status.json + status_banner.js)
Se il blocco di stato non esiste ancora, viene creato prima di </body>.
"""

import json
import re

INIZIO = "/* DATI-INIZIO */"
FINE = "/* DATI-FINE */"
STATO_INIZIO = "<!-- STATO-INIZIO -->"
STATO_FINE = "<!-- STATO-FINE -->"


def carica_json(percorso):
    try:
        with open(percorso, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return None


def sostituisci_dati(html, dati):
    # Impedisce che una stringa "</script>" nei dati chiuda il blocco script.
    payload = json.dumps(dati, ensure_ascii=False, indent=2).replace("</script>", "<\\/script>")
    blocco = INIZIO + "\nconst RECALLS = " + payload + ";\n" + FINE
    return re.sub(
        re.escape(INIZIO) + r".*?" + re.escape(FINE),
        lambda _: blocco,
        html,
        flags=re.S,
    )


def blocco_stato():
    stato = carica_json("status.json")  # None se manca: il banner non compare
    with open("status_banner.js", encoding="utf-8") as f:
        codice = f.read()
    payload = json.dumps(stato, ensure_ascii=False).replace("</", "<\\/")
    return (
        STATO_INIZIO + "\n<script>\nwindow.RICHIAMI_STATUS = " + payload + ";\n"
        + codice + "\n</script>\n" + STATO_FINE
    )


def sostituisci_stato(html):
    blocco = blocco_stato()
    if STATO_INIZIO in html and STATO_FINE in html:
        return re.sub(
            re.escape(STATO_INIZIO) + r".*?" + re.escape(STATO_FINE),
            lambda _: blocco,
            html,
            flags=re.S,
        )
    pos = html.rfind("</body>")
    if pos == -1:
        raise SystemExit("index.html senza </body>: impossibile inserire la riga di stato.")
    return html[:pos] + blocco + "\n" + html[pos:]


dati = carica_json("data.json")
if dati is None:
    raise SystemExit("data.json mancante o non valido.")

with open("index.html", encoding="utf-8") as f:
    html = f.read()

nuovo = sostituisci_stato(sostituisci_dati(html, dati))

if nuovo == html:
    print("Nessuna modifica (dati e stato già aggiornati).")
else:
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(nuovo)
    print(f"Iniettati {len(dati)} richiami e lo stato dell'ultimo controllo dentro index.html")
