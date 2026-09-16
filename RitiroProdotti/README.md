# Richiami — feed dei ritiri prodotto

Sito mobile-first (`index.html`, un solo file, nessuna build) + scraper Python
che genera `data.json` dal portale del Ministero della Salute.

## Cosa fa il sito

- **Home**: elenco cronologico, un rigo per richiamo con data, prodotto,
  marca e motivo.
- **Scheda**: click su un rigo → dettaglio con tutti i campi della scheda
  ministeriale, gli allegati (immagini della confezione), e due link:
  scheda ufficiale e avviso di sicurezza collegato.
- Filtro "Rischio per la salute" / "Altri avvisi".
- Routing via `#/r/<id>`: ogni scheda ha un URL condivisibile e il tasto
  indietro del telefono funziona.

Il sito legge `data.json`. Se non lo trova (es. aprendo il file con
`file://`), mostra un record di riserva **reale** e un banner che lo segnala.

## I campi reali

Dal sorgente di una scheda vera, i campi che il Ministero pubblica sono:

| Campo sito | Etichetta sul portale |
|---|---|
| `product` | Prodotto |
| `brand` | Marca |
| `reasonShort` | Sostanza/Rischio |
| `country` | Paese di origine |
| `lots` | Numero lotto |
| `noticeDate` / `noticeUrl` | News/Avviso (data + link) |
| `attachments` | blocco "Allegati" (immagini confezione) |
| `topic` | chip "Area tematica" |

**Non ci sono** i campi che avevo ipotizzato prima di vedere il sorgente:
produttore, data di scadenza, zona di vendita, testo "cosa fare". Il sito
ora non li inventa: la scheda renderizza dinamicamente `campi`, quindi se
il Ministero ne aggiunge uno compare da solo senza toccare il codice.

## Come provarlo (senza installare niente)

**Doppio clic su `index.html`.** Basta questo: i dati sono incorporati nel
file stesso, quindi funziona anche offline, senza server e senza Python.

Se accanto al file c'è un `data.json` *e* il sito gira su un server, quello
ha la precedenza sui dati incorporati. Ma è un di più: non è mai necessario.

> Se in una versione precedente vedevi il messaggio "data.json non trovato,
> lancia lo scraper": era un falso allarme. Aprendo il file con doppio clic
> il browser usa `file://` e blocca per sicurezza la lettura di `data.json`,
> anche se è lì accanto. Ora il sito non ci prova nemmeno: usa direttamente
> i dati che ha dentro.

### Per vederlo sul telefono

Il modo più semplice: carica la cartella su GitHub e attiva GitHub Pages
(Settings → Pages → Deploy from a branch → main). In un paio di minuti hai
un indirizzo pubblico da aprire dal telefono. Oppure manda `index.html` a
te stesso via mail o Telegram e aprilo: essendo autonomo, funziona lo stesso.

## Lo scraper (`scraper.py`)

**Non ti serve Python sul computer.** Lo scraper gira su GitHub Actions, cioè
sui server di GitHub: ogni 6 ore scarica i richiami, riscrive `data.json`,
li incolla dentro `index.html` con `inject_data.py` e fa commit. Tu tocchi
solo il browser.

Stato dei pezzi, onestamente:

- **`parse_detail()` — TESTATA** contro il sorgente HTML reale di una scheda.
  Estrae correttamente tutti i campi, gli allegati e le date.
- **`fetch` via Playwright — NON testata dal vivo.** L'ambiente in cui l'ho
  scritta non raggiunge `salute.gov.it`: il dominio è protetto da un
  controllo Gcore che blocca le richieste HTTP dirette. Quel controllo però
  è automatico e non è un captcha, quindi un browser headless che esegue
  JavaScript dovrebbe passare. **Lo scoprirai al primo giro dell'Action**:
  vai su GitHub nel tab "Actions", lancia il workflow a mano con "Run
  workflow" e leggi il log. Se fallisce, incollami l'errore.
- **`discover_urls()` — due strade, entrambe da verificare.**
  1. *Sitemap*: il sorgente dichiara `<link rel="sitemap" href="/new/sitemap-index.xml">`.
     Se contiene le schede è la via più solida, niente paginazione.
  2. *Pagina elenco*: fallback che raccoglie i link dalla pagina degli avvisi.
     Attenzione: il sito è in Gatsby, l'elenco potrebbe essere paginato o
     caricato via JavaScript. Se succede, mandami il sorgente della pagina
     elenco e sistemo anche quello.

### Se invece vuoi provarlo in locale

Serve Python (`python.org`) e poi:

```bash
pip install -r requirements.txt
playwright install chromium
python scraper.py 3      # il 3 limita a tre schede, per un primo giro veloce
python inject_data.py    # incolla i dati dentro index.html
```

Per vedere cosa fa il browser mentre gira, in `scraper.py` cerca `Browser()`
dentro `main()` e scrivi `Browser(headless=False)`: si aprirà una finestra
Chromium vera e vedrai se il controllo Gcore passa o blocca.

### Aggiornamento automatico

`.github/workflows/update-richiami.yml` esegue lo scraper ogni 6 ore e fa
commit di `data.json`. Funziona bene con GitHub Pages: il sito è statico e
legge il JSON dallo stesso repository.

## Un'idea da verificare

Il sito è costruito con **Gatsby**, che di solito espone i dati di ogni
pagina come JSON su un URL prevedibile, tipo:

```
/new/page-data/it/avvisi-sicurezza-alimentare/<slug>/page-data.json
```

Se quell'endpoint esiste, prendere i dati da lì sarebbe molto più solido che
fare parsing dell'HTML: niente selettori che si rompono al primo restyle.
Non ho potuto verificarlo dall'esterno. Prova ad aprirne uno nel browser:
se scarica un JSON, riscrivo lo scraper su quella base ed è tutta un'altra
robustezza.

## La classificazione rischio/avviso

`category` è un'euristica che cerca parole come "listeria", "salmonella",
"allergene" nel campo Sostanza/Rischio. **È debole**: nella scheda reale che
abbiamo, quel campo conteneva solo "Integratore a base di caffè e funghi",
cioè una descrizione del prodotto, non un rischio — infatti viene
classificata come "Avviso" e non come "Rischio salute". Se vuoi la
classificazione affidabile, la strada è leggere anche la notizia collegata
(`noticeUrl`), dove il motivo è spiegato per esteso.
