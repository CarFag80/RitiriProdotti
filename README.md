# Richiami ” feed dei ritiri prodotto

Sito mobile-first (`index.html`, un solo file, nessuna build) + scraper Python
che genera `data.json` da due fonti del Ministero della Salute.

## Due fonti di dati

Lo scraper raccoglie i richiami da **due elenchi ufficiali diversi**:

1. **Avvisi e richiami di prodotti alimentari** 
   (https://www.salute.gov.it/new/it/avvisi/avvisi-e-richiami-di-prodotti-alimentari/)
   â€” Richiami **obbligatori**: il Ministero ordina il ritiro e la comunicazione al pubblico.
   Badge: "Richiamo ufficiale" (rosso).

2. **Avvisi di sicurezza**
   (https://www.salute.gov.it/new/it/avvisi/avvisi-di-sicurezza/)
   â€” Richiami **volontari**: l'azienda (OSA â€” Operatore del Settore Alimentare) decide di ritirare di propria iniziativa.
   Badge: "Richiamo volontario" (blu).

Entrambi sono importanti per il consumatore: i volontari spesso vengono comunicati prima, gli obbligatori hanno il peso della legge.

## Come appare nel sito

### Home / Feed
- Ogni voce mostra **data**, **prodotto**, **marca**, **motivo** e una **riga di tag**: 
  - "Rischio salute" o "Avviso" (categoria del problema)
  - Fonte (non ancora mostrata nel feed per non appesantire, ma Ã¨ nei dati)
- **Filtro per fonte**: menu a tendina "Tutte le fonti / Richiami ufficiali / Richiami operatori" accanto a quello per anno.

### Scheda dettaglio
- Due badge in alto a destra della sezione hero:
  - "Rischio salute" / "Avviso" (come prima)
  - **"Richiamo ufficiale"** (rosso) o **"Richiamo volontario"** (blu) â€” chiarisce subito la differenza al consumatore.
- Tutti gli altri campi (lotto, produttore, allegati) rimangono uguali.

## I campi reali da scheda ministeriale

| Campo | Label sito | Fonte |
|---|---|---|
| product | Prodotto | Entrambe |
| brand | Marca | Entrambe |
| reasonShort | Sostanza/Rischio | Entrambe |
| country | Paese di origine | Entrambe |
| lots | Numero lotto | Entrambe |
| source | â† NEW | Entrambe (`official` o `operator`) |
| published | News/Avviso (data) | Entrambe |
| attachments | Allegati (immagini) | Entrambe |

## Lo scraper (`scraper.py`) â€” AGGIORNATO

- **Due discovery**: una per ufficiali, una per operatori.
- **Parsing identico**: usa lo stesso `parse_detail()` per entrambe; riceve `source` come parametro.
- **Output unificato**: un solo `data.json` con tutti i richiami, ordinati per data, etichettati con source.

Il log dell'esecuzione ora dice:

```
=== RICHIAMI UFFICIALI ===
[1/N] ok â€¦
â€¦
=== RICHIAMI DEGLI OPERATORI ===
[1/M] ok â€¦
â€¦
Salvati X richiami (Y ufficiali, Z operatori) in data.json
```

### Provarlo

```bash
pip install -r requirements.txt
playwright install chromium
python scraper.py 5      # limita a 5 per tipo per il primo giro
python inject_data.py    # incolla i dati dentro index.html
```

## Come provarlo (senza installare niente)

**Doppio clic su `index.html`.** I dati sono incorporati nel file stesso, quindi funziona offline.

Se sul server accanto c'Ã¨ un `data.json` piÃ¹ fresco, quello ha la precedenza. Ma Ã¨ un di piÃ¹.

## Pubblicazione su Netlify

1. Carica la cartella su GitHub.
2. Collegala a Netlify: **Add new site â†’ Import an existing project â†’ Deploy with GitHub**.
3. Il workflow GitHub Actions aggiornerÃ  i dati ogni 6 ore, Netlify ripubblicherÃ  automaticamente.

## Prossimi passi suggeriti

- Integrare **RASFF** (sistema di allerta europeo) come terza fonte â€” allargherebbe la visibilitÃ  ai richiami che interessano l'Italia da altri Paesi UE.
- Integrare **RAPEX** (prodotti non alimentari) in una scheda separata â€” avrebbe senso per un centro allerte completo.

