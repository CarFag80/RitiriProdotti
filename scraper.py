"""
scraper.py — Richiami alimentari (Ministero della Salute) -> data.json

AGGIORNATO sul sorgente HTML reale di una scheda di richiamo, che Carmine
ha recuperato dal browser. La struttura dei campi è ora quella effettiva:

  <h1>…</h1>
  <div class="pb-2"><span class="fw-bold">Prodotto: </span>VALORE</div>
  <div class="pb-2"><span class="fw-bold">Marca: </span>VALORE</div>
  <div class="pb-2"><span class="fw-bold">Sostanza/Rischio: </span>VALORE</div>
  <div class="pb-2"><span class="fw-bold">Paese di origine: </span>VALORE</div>
  <div class="pb-2"><span class="fw-bold">Numero lotto: </span>VALORE</div>
  <div class="pb-2"><span class="fw-bold">News/Avviso: </span><a href=…>DATA</a></div>
  … <a download href=…>allegato</a> …
  … <button class="chip">Area tematica</button>

Il parsing delle etichette è generico: ogni <div class="pb-2"> con uno
<span class="fw-bold">Etichetta:</span> finisce in record["campi"], anche se
il Ministero aggiunge o rinomina un campo. Quelli noti vengono mappati sui
nomi usati dal sito; gli altri restano comunque disponibili.

COSA È VERIFICATO E COSA NO
- parse_detail(): TESTATO sul sorgente reale, estrae tutti i campi.
- fetch(): NON testato dal vivo — questo ambiente non raggiunge
  salute.gov.it (protezione Gcore). Playwright dovrebbe passare perché il
  controllo è automatico e non è un captcha, ma va provato in locale.
- discover_urls(): scritta su due strade alternative, entrambe da verificare
  in locale (vedi la funzione).
"""

import json
import re
import sys
import time

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE = "https://www.salute.gov.it"
LIST_URL = f"{BASE}/new/it/avvisi/avvisi-e-richiami-di-prodotti-alimentari/"
SITEMAP_URL = f"{BASE}/new/sitemap-index.xml"
OUTPUT_PATH = "data.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

LABEL_MAP = {
    "prodotto": "product",
    "marca": "brand",
    "sostanza/rischio": "reasonShort",
    "paese di origine": "country",
    "numero lotto": "lot",
    "produttore": "producer",
    "nome o ragione sociale dell'osa": "producer",
    "sede dello stabilimento": "plant",
    "data di scadenza": "expiry",
    "termine minimo di conservazione": "expiry",
    "peso": "packaging",
    "quantita": "packaging",
    "quantità": "packaging",
}

RISK_KEYWORDS = [
    "listeria", "salmonella", "escherichia", "coli", "botulin",
    "allergen", "allerg", "corpo estraneo", "corpi estranei",
    "plastica", "vetro", "metallo", "microbiolog", "tossina",
    "istamina", "micotossin", "aflatossin", "ossido di etilene",
]


def clean(text):
    return re.sub(r"\s+", " ", (text or "")).strip()


# ---------------------------------------------------------------- browser --
class Browser:
    """Wrapper minimale su Playwright: apre un browser vero una volta sola
    e lo riusa per tutte le pagine, così il controllo Gcore si risolve una
    volta e i cookie restano validi per le richieste successive."""

    def __init__(self, headless=True):
        self.headless = headless

    def __enter__(self):
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)
        self._ctx = self._browser.new_context(user_agent=USER_AGENT, locale="it-IT")
        self.page = self._ctx.new_page()
        return self

    def __exit__(self, *exc):
        self._browser.close()
        self._pw.stop()

    def get(self, url, wait_ms=2000, timeout_ms=45000):
        self.page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        self.page.wait_for_timeout(wait_ms)  # margine per il controllo Gcore
        return self.page.content()


# -------------------------------------------------------------- discovery --
def discover_urls(browser, limit=None):
    """Trova gli URL delle schede di richiamo.

    Due strade, in ordine di preferenza. Entrambe DA VERIFICARE in locale:
    non ho potuto raggiungere il sito per confermare quale delle due funzioni.

    1) Sitemap. Il sorgente della pagina dichiara
       <link rel="sitemap" href="/new/sitemap-index.xml">. Se contiene le
       schede, è la via più solida: niente paginazione da gestire.
    2) Pagina elenco. In alternativa si raccolgono i link della pagina
       "Avvisi e richiami di prodotti alimentari". ATTENZIONE: il sito è in
       Gatsby e l'elenco potrebbe essere paginato o caricato via JavaScript;
       in quel caso qui servirà gestire il "carica altri" / le pagine
       successive. Con un esempio della pagina elenco lo sistemo.
    """
    urls = []

    # --- strada 1: sitemap ---
    try:
        xml = browser.get(SITEMAP_URL, wait_ms=1500)
        sub_sitemaps = re.findall(r"<loc>\s*([^<]+?)\s*</loc>", xml)
        for sm in sub_sitemaps:
            if not sm.endswith(".xml"):
                continue
            body = browser.get(sm, wait_ms=800)
            urls += [
                u for u in re.findall(r"<loc>\s*([^<]+?)\s*</loc>", body)
                if "avvisi-sicurezza-alimentare" in u
            ]
        if urls:
            print(f"Sitemap: trovate {len(urls)} schede.")
    except Exception as e:
        print(f"Sitemap non utilizzabile ({e}); provo con la pagina elenco.")

    # --- strada 2: pagina elenco ---
    if not urls:
        html = browser.get(LIST_URL)
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select("a[href]"):
            href = a["href"]
            if "avvisi-sicurezza-alimentare" in href:
                urls.append(href if href.startswith("http") else BASE + href)
        print(f"Pagina elenco: trovati {len(urls)} link.")

    # dedup preservando l'ordine
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out[:limit] if limit else out


# ----------------------------------------------------------------- parser --
def parse_detail(html, url=""):
    """TESTATA sul sorgente reale di una scheda."""
    soup = BeautifulSoup(html, "html.parser")
    record = {"sourceUrl": url}

    h1 = soup.find("h1")
    record["title"] = clean(h1.get_text()) if h1 else ""

    campi = {}
    for div in soup.select("div.pb-2"):
        span = div.find("span", class_="fw-bold")
        if not span:
            continue
        label = clean(span.get_text()).rstrip(":").strip().lower()
        if not label:
            continue
        value = clean(clean(div.get_text()).replace(clean(span.get_text()), "", 1))
        campi[label] = value
        if "news" in label:
            a = div.find("a", href=True)
            if a:
                record["noticeUrl"] = BASE + a["href"] if a["href"].startswith("/") else a["href"]
                record["noticeDate"] = clean(a.get_text())

    record["campi"] = campi
    for label, value in campi.items():
        key = LABEL_MAP.get(label)
        if key and value:
            record[key] = value

    lot_raw = record.pop("lot", "")
    record["lots"] = [clean(x) for x in re.split(r"[;,]| e ", lot_raw) if clean(x)]

    record["attachments"] = [
        {
            "name": clean(a.get_text()),
            "url": BASE + a["href"] if a["href"].startswith("/") else a["href"],
        }
        for a in soup.select("a[download][href]")
    ]

    chip = soup.select_one("button.chip")
    record["topic"] = clean(chip.get_text()) if chip else ""

    # Euristica grezza. NOTA: il campo "Sostanza/Rischio" non sempre nomina
    # un rischio — nella scheda di esempio conteneva solo la descrizione del
    # prodotto. Quindi questa classificazione va presa con le pinze; se
    # serve precisione, meglio leggere anche la notizia collegata.
    blob = " ".join([record.get("reasonShort", ""), record.get("title", "")]).lower()
    record["category"] = "risk" if any(k in blob for k in RISK_KEYWORDS) else "info"

    if not record.get("product"):
        record["product"] = record["title"]
    record["id"] = url.rstrip("/").rsplit("/", 1)[-1] or record["title"][:50]
    record["published"] = to_iso(record.get("noticeDate", ""))

    return record


def to_iso(it_date):
    """'11/9/2026' -> '2026-09-11'. Stringa vuota se non riconosciuta."""
    m = re.match(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*$", it_date or "")
    if not m:
        return ""
    d, mth, y = m.groups()
    return f"{y}-{int(mth):02d}-{int(d):02d}"


# ------------------------------------------------------------------- main --
def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None

    with Browser() as b:
        urls = discover_urls(b, limit=limit)
        if not urls:
            raise SystemExit(
                "Nessuna scheda trovata. Salva su file il contenuto di "
                "discover_urls e guarda cosa è tornato: probabilmente "
                "l'elenco è paginato o caricato via JavaScript."
            )

        records = []
        for i, url in enumerate(urls, 1):
            try:
                records.append(parse_detail(b.get(url, wait_ms=1200), url))
                print(f"[{i}/{len(urls)}] ok  {url}")
            except Exception as e:
                print(f"[{i}/{len(urls)}] ERRORE {url}: {e}")
            time.sleep(0.5)  # cortesia verso il server

    records.sort(key=lambda r: r.get("published", ""), reverse=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"\nSalvati {len(records)} richiami in {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
