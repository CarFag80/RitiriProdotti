"""
inject_data.py — incolla il contenuto di data.json dentro index.html.

Serve a tenere il sito autonomo: i dati vivono dentro l'HTML, quindi il file
funziona anche aperto con doppio clic, senza server e senza Python.
Questo script gira su GitHub Actions dopo lo scraper — non serve lanciarlo
a mano sul proprio computer.
"""

import json
import re

INIZIO = "/* DATI-INIZIO */"
FINE = "/* DATI-FINE */"

with open("data.json", encoding="utf-8") as f:
    dati = json.load(f)

with open("index.html", encoding="utf-8") as f:
    html = f.read()

blocco = INIZIO + "\nconst RECALLS = " + json.dumps(dati, ensure_ascii=False, indent=2) + ";\n" + FINE

nuovo = re.sub(
    re.escape(INIZIO) + r".*?" + re.escape(FINE),
    lambda _: blocco,
    html,
    flags=re.S,
)

if nuovo == html:
    print("Nessuna modifica (dati già aggiornati).")
else:
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(nuovo)
    print(f"Iniettati {len(dati)} richiami dentro index.html")
