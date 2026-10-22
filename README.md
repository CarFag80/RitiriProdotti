# Richiami — feed dei ritiri prodotto

Sito mobile-first (`index.html`, un solo file, nessuna build) + scraper Python
che genera `data.json` da due elenchi del Ministero della Salute.

## Due fonti di dati

1. **Avvisi e richiami di prodotti alimentari** — richiami obbligatori; badge rosso "Richiamo ufficiale".
2. **Avvisi di sicurezza** (scheda "Richiami degli Operatori") — richiami volontari degli OSA; badge blu "Richiamo volontario".

## Come appare nel sito

- **Home / Feed:** data, prodotto, marca, motivo e tag categoria; filtri per anno e fonte.
- **Scheda dettaglio:** badge categoria e tipo di richiamo, lotto, produttore e allegati.

## Campi prodotti dallo scraper

| Campo | Significato |
|---|---|
| `product`, `brand`, `reasonShort`, `country` | Dati principali della scheda |
| `lots`, `lotsRaw` | Lotti separati e testo originale |
| `source` | `official` oppure `operator` |
| `published` | Data in formato ISO |
| `attachments` | Allegati con nome e URL |
| `producer`, `plant`, `expiry`, `packaging` | Campi aggiuntivi quando presenti |
| `topic`, `category` | Area tematica e classificazione euristica (`risk`/`info`) |
| `noticeUrl` | Link alla notizia collegata, se presente |

## Lo scraper

- Sitemap scaricata una sola volta per run, con pause tra le sotto-mappe.
- Pagina elenco letta con paginazione/caricamento progressivo (fino a 40 pagine).
- Cache: le schede valide non si riscaricano; quelle recenti (ultimi 30 giorni) vengono riscaricate al massimo una volta ogni 24 ore.
- Pausa casuale 3–6 s tra le schede; dopo 2 blocchi consecutivi la fonte si ferma per la run.
- Checkpoint ogni 20 schede nuove o 5 minuti, con commit `[skip ci]` per non innescare deploy Netlify.
- `data.json` salvato in JSON compatto per ridurre il peso del repository.

## Provarlo

```bash
pip install -r requirements.txt
playwright install chromium
python scraper.py 5      # limita a 5 schede per fonte
python inject_data.py    # incolla i dati dentro index.html
```

## Web app

Doppio clic su `index.html`: i dati sono incorporati e il sito funziona offline.
Se accanto esiste un `data.json` più recente, il sito lo usa.

## Pubblicazione su Netlify

1. Carica la cartella su GitHub.
2. Netlify → **Add new site → Import an existing project → Deploy with GitHub**.
3. Il workflow GitHub Actions aggiorna i dati ogni 3 ore; Netlify ripubblica automaticamente.

## Prossimi passi

- Integrare RASFF come terza fonte.
- Integrare RAPEX per i prodotti non alimentari.
