"""
scraper.py - Richiami alimentari (Ministero della Salute) -> data.json

Due fonti, una sola pagina elenco ("Avvisi e richiami di prodotti alimentari"):
  ufficiali  -> /new/it/avvisi-sicurezza-alimentare/<slug>
  operatori  -> /new/it/ext-avviso-sicurezza-alimentare/<slug>
                (si raggiungono cliccando la scheda "Richiami degli Operatori")

STRATEGIA (Variante B)
- Prima esecuzione (nessuno storico precedente): scarica TUTTO lo storico,
  con checkpoint git+push ogni 20 schede nuove o 5 minuti.
- Esecuzioni successive: solo schede NUOVE non ancora in cache; se la loro
  data e' precedente al YEAR_FILTER (2026), vengono scartate. Le schede senza
  data riconoscibile vengono comunque salvate (con avviso), per evitare
  perdita di dati e ritentativi infiniti. Nessun refresh delle schede gia'
  presenti. Checkpoint solo locale (nessun commit) per ridurre i deploy
  Netlify: il push avviene una sola volta, a fine run, se data.json e'
  cambiato.

STATO DELLA VERIFICA
- parse_detail(), to_iso(), split_lots(), classificazione rischio: testati offline.
- Browser/discover_urls/paginazione: NON testati dal vivo (salute.gov.it e' protetto
  da Gcore). Provare in locale con: python scraper.py 5
"""

import json
import random
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urldefrag

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE = "https://www.salute.gov.it"
OFFICIAL_URL = f"{BASE}/new/it/avvisi/avvisi-e-richiami-di-prodotti-alimentari/"
OPERATOR_URL = OFFICIAL_URL
OPERATOR_TAB_LABEL = "Richiami degli Operatori"
SITEMAP_URL = f"{BASE}/new/sitemap-index.xml"
OUTPUT_PATH = "data.json"
YEAR_FILTER = 2026

CHECKPOINT_EVERY = 20
CHECKPOINT_MAX_SECONDS = 300
CHECKPOINT_TAG = " [skip ci]"
MAX_RUNTIME_SECONDS = 35 * 60

DELAY_RANGE = (3.0, 6.0)
SITEMAP_DELAY_RANGE = (1.0, 2.5)
BLOCK_BACKOFF_SECONDS = 120
MAX_CONSECUTIVE_BLOCKS = 2
BLOCK_MARKERS = (
    "sorry, you have been blocked", "attention required", "just a moment",
    "please enable cookies", "browser validation", "verifying you are human",
    "access denied",
)

MAX_LIST_PAGES = 40
NEXT_PAGE_SELECTOR = ", ".join([
    "a[rel=next]",
    "button:has-text('Carica altri')",
    "button:has-text('Mostra altri')",
    "a:has-text('Successiva')",
    "a:has-text('Avanti')",
    "button:has-text('Successiva')",
    "li.next a",
    "[aria-label*='successiv' i]",
])

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
    "quantit\u00e0": "packaging",
    "denominazione": "product",
    "motivo della segnalazione": "reasonShort",
}

IT_MONTHS = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5,
    "giugno": 6, "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10,
    "novembre": 11, "dicembre": 12,
}

RISK_RE = re.compile(
    r"\b(?:listeri\w*|salmonell\w*|escherichia|e\.?\s?coli|coli|stec|botulin\w*|"
    r"allergen\w*|allerg\w*|corp[oi]\s+estran\w*|plastic[ahe]\w*|vetro|vetri|"
    r"metall[oi]|microbiolog\w*|tossin\w*|istamin\w*|micotossin\w*|"
    r"aflatossin\w*|ossido\s+di\s+etilene)\b",
    re.I,
)
LOT_NOT_CODE = re.compile(r"scad|tmc|entro|data|\d{1,2}/\d{1,2}/\d{2,4}", re.I)


def clean(text):
    return re.sub(r"\s+", " ", (text or "")).strip()


class Blocked(Exception):
    pass


def looks_blocked(html):
    low = (html or "").lower()
    return any(m in low for m in BLOCK_MARKERS)


class Browser:
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

    def _settle(self, timeout_ms):
        try:
            self.page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 10000))
        except Exception:
            pass

    def get(self, url, wait_ms=2000, timeout_ms=45000):
        self.page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        self._settle(timeout_ms)
        self.page.wait_for_timeout(wait_ms)
        return self.page.content()

    def get_locs(self, url, wait_ms=800):
        html = self.get(url, wait_ms=wait_ms)
        if looks_blocked(html):
            raise Blocked("sitemap bloccata")
        locs = re.findall(r"<loc>\s*([^<]+?)\s*</loc>", html)
        if not locs:
            text = self.page.evaluate("() => document.documentElement.textContent || ''")
            locs = re.findall(r"https?://.+?(?=https?://|\s|$)", text)
        return locs

    def click_tab(self, text, wait_ms=2500, timeout_ms=15000):
        self.page.get_by_text(text, exact=False).first.click(timeout=timeout_ms)
        self.page.wait_for_timeout(wait_ms)
        self._settle(timeout_ms)
        return self.page.content()

    def next_page(self, wait_ms=2000, timeout_ms=15000):
        try:
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            loc = self.page.locator(NEXT_PAGE_SELECTOR)
            if loc.count() == 0:
                return None
            el = loc.first
            if not el.is_visible() or not el.is_enabled():
                return None
            el.click(timeout=5000)
        except Exception:
            return None
        self.page.wait_for_timeout(wait_ms)
        self._settle(timeout_ms)
        return self.page.content()


def fetch_sitemap_urls(browser):
    urls = []
    try:
        locs = browser.get_locs(SITEMAP_URL, wait_ms=1500)
    except Exception as e:
        print(f"Sitemap non utilizzabile ({e}); user\u00f2 solo la pagina elenco.")
        return urls
    subs = [u for u in locs if u.endswith(".xml")]
    urls += [u for u in locs if not u.endswith(".xml")]
    ok = failed = 0
    for sm in subs:
        try:
            urls += browser.get_locs(sm)
            ok += 1
        except Blocked:
            print("Sitemap: bloccati, mi fermo qui con le sotto-mappe.")
            break
        except Exception:
            failed += 1
        time.sleep(random.uniform(*SITEMAP_DELAY_RANGE))
    if failed:
        print(f"Sitemap: {failed}/{len(subs)} sotto-mappe non raggiungibili, saltate.")
    print(f"Sitemap: {len(urls)} URL totali da {ok} sotto-mappe.")
    return urls


def extract_links(html, pattern):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.select("a[href]"):
        if pattern in a["href"]:
            out.append(urldefrag(urljoin(BASE, a["href"]))[0])
    return out


def discover_urls(browser, list_url, pattern, sitemap_urls, limit=None, click_label=None):
    urls = [u for u in sitemap_urls if pattern in u]
    if urls:
        print(f"Sitemap: {len(urls)} schede per '{pattern}'.")

    try:
        html = browser.get(list_url)
        if click_label:
            try:
                html = browser.click_tab(click_label)
            except Exception as e:
                print(f"Click su '{click_label}' non riuscito ({e}); leggo la pagina cos\u00ec com'\u00e8.")
        found, seen = [], set()
        page_no = 0
        for page_no in range(MAX_LIST_PAGES):
            new = [l for l in extract_links(html, pattern) if l not in seen]
            if page_no > 0 and not new:
                break
            seen.update(new)
            found += new
            html = browser.next_page()
            if html is None:
                break
        if found:
            print(f"Pagina elenco: {len(found)} link in {page_no + 1} pagina/e.")
        urls += found
    except Exception as e:
        print(f"Pagina elenco non raggiungibile ({e}).")

    seen, out = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out[:limit] if limit else out


def split_lots(raw):
    raw = clean(raw)
    if not raw:
        return []
    out = []
    for part in (clean(p) for p in re.split(r"\s*;\s*", raw)):
        if not part:
            continue
        sub = [clean(x) for x in re.split(r",\s+(?=[A-Za-z0-9])", part) if clean(x)]
        if len(sub) > 1 and all(len(s.split()) <= 2 and not LOT_NOT_CODE.search(s) for s in sub):
            out += sub
        else:
            out.append(part)
    return out


def to_iso(it_date):
    it_date = clean(it_date)
    m = re.match(r"^(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{4})$", it_date)
    if m:
        d, mth, y = m.groups()
        return f"{y}-{int(mth):02d}-{int(d):02d}"
    m = re.match(r"^(\d{1,2})\s*/\s*([A-Za-z\u00e0\u00e8\u00e9\u00ec\u00f2\u00f9]+)\s*/\s*(\d{4})$", it_date)
    if m:
        d, month_name, y = m.groups()
        mth = IT_MONTHS.get(month_name.lower())
        if mth:
            return f"{y}-{mth:02d}-{int(d):02d}"
    return ""


def parse_detail(html, url="", source="official"):
    soup = BeautifulSoup(html, "html.parser")
    record = {"sourceUrl": url}

    h1 = soup.find("h1")
    record["title"] = clean(h1.get_text()) if h1 else ""

    campi = {}
    for div in soup.select(".pb-2"):
        span = div.find("span", class_="fw-bold")
        if not span:
            continue
        label = clean(span.get_text()).rstrip(":").strip().lower()
        if not label:
            continue
        value = clean(clean(div.get_text()).replace(clean(span.get_text()), "", 1))
        campi[label] = value
        if "news" in label or "data pubblicazione" in label:
            a = div.find("a", href=True)
            if a and "news" in label:
                record["noticeUrl"] = urljoin(BASE, a["href"])
                record["noticeDate"] = clean(a.get_text())
            if not record.get("noticeDate"):
                record["noticeDate"] = value

    record["campi"] = campi
    for label, value in campi.items():
        key = LABEL_MAP.get(label)
        if key and value:
            record[key] = value

    lot_raw = record.pop("lot", "")
    record["lotsRaw"] = lot_raw
    record["lots"] = split_lots(lot_raw)

    def attachment_name(a):
        text = clean(a.get_text())
        if text:
            return text
        href = a["href"]
        for other in soup.select("a[href]"):
            if other is not a and other.get("href") == href and clean(other.get_text()):
                return clean(other.get_text())
        return href.rsplit("/", 1)[-1].split("?")[0].replace("%20", " ")

    record["attachments"] = [
        {"name": attachment_name(a), "url": urljoin(BASE, a["href"])}
        for a in soup.select("a[download][href]")
    ]

    chip = soup.select_one("button.chip")
    record["topic"] = clean(chip.get_text()) if chip else ""

    blob = " ".join([record.get("reasonShort", ""), record.get("title", "")])
    record["category"] = "risk" if RISK_RE.search(blob) else "info"

    if not record.get("product"):
        record["product"] = record["title"]
    record["id"] = make_slug(url, record["title"])
    record["published"] = to_iso(record.get("noticeDate", ""))
    record["source"] = source
    return record


def make_slug(url, title=""):
    return url.rstrip("/").rsplit("/", 1)[-1] or title[:50]


def infer_source(url):
    return "operator" if "ext-avviso-sicurezza-alimentare" in url else "official"


def normalize_records(records):
    for r in records:
        r["source"] = r.get("source") or infer_source(r.get("sourceUrl", ""))
        r["id"] = make_slug(r.get("sourceUrl", ""), r.get("title", ""))
    counts = {}
    for r in records:
        counts[r["id"]] = counts.get(r["id"], 0) + 1
    for r in records:
        if counts[r["id"]] > 1:
            r["id"] = f"{r['source']}-{r['id']}"
    return records


def is_valid_record(rec):
    return bool(rec.get("campi")) and not looks_blocked(rec.get("title", ""))


def load_cache():
    """Restituisce (cache, full_done). full_done=True se nello storico gia'
    scaricato esiste almeno una scheda precedente al YEAR_FILTER: significa
    che il recupero completo e' gia' stato fatto e le run successive sono
    incrementali (solo nuove schede del YEAR_FILTER o successive)."""
    try:
        with open(OUTPUT_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print("Nessun data.json precedente: prima esecuzione, scarico tutto lo storico.")
        return {}, False
    except Exception as e:
        print(f"data.json precedente non leggibile ({e}): riparto da zero.")
        return {}, False
    cache = {r["sourceUrl"]: r for r in data if r.get("sourceUrl") and is_valid_record(r)}
    full_done = any(
        (r.get("published") or "")[:4].isdigit()
        and int(r["published"][:4]) < YEAR_FILTER
        for r in cache.values()
    )
    scartate = len(data) - len(cache)
    print(f"Cache: {len(cache)} schede valide; storico completo: {'SI' if full_done else 'NO'}"
          + (f"; {scartate} non valide scartate e da riscaricare." if scartate else "."))
    return cache, full_done


def save_records(records):
    normalize_records(records)
    records_sorted = sorted(records, key=lambda r: r.get("published", ""), reverse=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(records_sorted, f, ensure_ascii=False, separators=(",", ":"))
    return records_sorted


def fetch_detail(browser, url, source, timeout_ms=25000, retries=2):
    last_err = None
    for attempt in range(retries + 1):
        try:
            html = browser.get(url, wait_ms=1200, timeout_ms=timeout_ms)
            rec = parse_detail(html, url, source=source)
            if is_valid_record(rec):
                rec["fetchedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                return rec, None
            if looks_blocked(html):
                return None, Blocked("il sito ha risposto con una pagina di blocco")
            last_err = "pagina senza i campi attesi"
        except Exception as e:
            last_err = str(e)
        if attempt < retries:
            time.sleep(2)
    return None, last_err


def git_checkpoint(records, message, publish=True):
    """publish=True (solo primo scaricamento completo): commit+push.
    publish=False (run incrementali): salva solo in locale, nessun commit,
    per non generare deploy Netlify a ogni checkpoint."""
    try:
        save_records(records)
        if not publish:
            print("Checkpoint salvato solo in locale (nessun commit, per risparmiare deploy Netlify).")
            return
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=False)
        subprocess.run(["git", "config", "user.email",
                        "github-actions[bot]@users.noreply.github.com"], check=False)
        subprocess.run(["git", "add", OUTPUT_PATH], check=False)
        if subprocess.run(["git", "diff", "--quiet", "--cached"]).returncode == 0:
            return
        subprocess.run(["git", "commit", "-m", message + CHECKPOINT_TAG], check=False)
        for attempt in range(3):
            if subprocess.run(["git", "pull", "--rebase", "origin", "main"]).returncode == 0:
                if subprocess.run(["git", "push"]).returncode == 0:
                    print(f"Checkpoint pubblicato: {message}")
                    return
            print(f"Checkpoint: push rifiutato (tentativo {attempt + 1}/3), riprovo...")
            time.sleep(5)
        print("Checkpoint non pubblicato; proseguo comunque.")
    except Exception as e:
        print(f"Checkpoint fallito ({e}); proseguo comunque.")


def scrape_source(browser, store, label, source, list_url, pattern, limit, deadline,
                  state, sitemap_urls, full_done, click_label=None):
    print(f"\n=== {label} ===")
    try:
        urls = discover_urls(browser, list_url, pattern, sitemap_urls, limit=limit,
                             click_label=click_label)
        queue = [u for u in urls if u not in store]
        print(f"{len(urls)} schede trovate: {len(queue)} nuove da scaricare, "
              f"{len(urls) - len(queue)} gia' in cache.")

        since_checkpoint, last_cp, rimaste = 0, time.time(), 0
        for i, url in enumerate(queue, 1):
            if state["blocked"] or time.time() > deadline:
                rimaste += 1
                continue
            rec, err = fetch_detail(browser, url, source)
            if isinstance(err, Blocked):
                state["blocks"] += 1
                print(f"[{i}/{len(queue)}] BLOCCATO ({state['blocks']}/{MAX_CONSECUTIVE_BLOCKS}) {url}")
                if state["blocks"] >= MAX_CONSECUTIVE_BLOCKS:
                    state["blocked"] = True
                    print("Il sito ci blocca: mi fermo per questa fonte.")
                else:
                    print(f"Attendo {BLOCK_BACKOFF_SECONDS}s prima di riprovare...")
                    time.sleep(BLOCK_BACKOFF_SECONDS)
                rimaste += 1
                continue
            state["blocks"] = 0
            if rec:
                year = (rec.get("published") or "")[:4]
                if full_done and year and year.isdigit() and int(year) < YEAR_FILTER:
                    print(f"[{i}/{len(queue)}] FUORI {YEAR_FILTER} (anno: {year}), non salvato: {url}")
                else:
                    store[url] = rec
                    flag = " (senza data!)" if not rec.get("published") else ""
                    print(f"[{i}/{len(queue)}] ok  {url}{flag}")
                    since_checkpoint += 1
            else:
                print(f"[{i}/{len(queue)}] SALTATO {url}: {err}")
            if since_checkpoint and (since_checkpoint >= CHECKPOINT_EVERY
                                     or time.time() - last_cp > CHECKPOINT_MAX_SECONDS):
                git_checkpoint(list(store.values()),
                               f"Checkpoint parziale richiami ({label.lower()})",
                               publish=not full_done)
                since_checkpoint, last_cp = 0, time.time()
            time.sleep(random.uniform(*DELAY_RANGE))
        if rimaste:
            print(f"{rimaste} schede di '{label}' restano per la prossima run.")
    except Exception as e:
        print(f"FONTE '{label}' SALTATA per errore imprevisto: {e}")


def parse_limit(argv):
    arg = argv[1].strip() if len(argv) > 1 else ""
    return int(arg) if arg.isdigit() and int(arg) > 0 else None


def main():
    limit = parse_limit(sys.argv)
    cache, full_done = load_cache()
    store = dict(cache)
    start = time.time()
    end = start + MAX_RUNTIME_SECONDS
    state = {"blocked": False, "blocks": 0}

    with Browser() as b:
        sitemap_urls = fetch_sitemap_urls(b)
        scrape_source(b, store, "RICHIAMI UFFICIALI", "official", OFFICIAL_URL,
                      "avvisi-sicurezza-alimentare", limit, start + MAX_RUNTIME_SECONDS / 2,
                      state, sitemap_urls, full_done)
        if state["blocked"] and time.time() + BLOCK_BACKOFF_SECONDS < end:
            print(f"\nAttendo {BLOCK_BACKOFF_SECONDS}s e riprovo con la fonte successiva...")
            time.sleep(BLOCK_BACKOFF_SECONDS)
            state.update(blocked=False, blocks=MAX_CONSECUTIVE_BLOCKS - 1)
        scrape_source(b, store, "RICHIAMI DEGLI OPERATORI", "operator", OPERATOR_URL,
                      "ext-avviso-sicurezza-alimentare", limit, end, state, sitemap_urls,
                      full_done, click_label=OPERATOR_TAB_LABEL)

    if not store:
        raise SystemExit("Nessuna scheda valida da nessuna delle due fonti. Controlla il log.")

    records = save_records(list(store.values()))
    off = sum(1 for r in records if r.get("source") == "official")
    ope = sum(1 for r in records if r.get("source") == "operator")
    print(f"\nSalvati {len(records)} richiami ({off} ufficiali, {ope} operatori) in {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
