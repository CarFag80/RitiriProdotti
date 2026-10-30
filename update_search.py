from pathlib import Path

OLD = """function matchesSearch(r){
  if (!searchQuery.trim()) return true;
  const q = normalize(searchQuery);
  const hay = normalize([r.product, r.title, r.brand, r.reasonShort].filter(Boolean).join(' '));
  return hay.includes(q);
}"""
NEW = r"""function matchesSearch(r){
  if (!searchQuery.trim()) return true;
  const terms = normalize(searchQuery).match(/[\p{L}\p{N}]+/gu) || [];
  if (!terms.length) return false;
  const hay = normalize([r.product, r.title, r.brand, r.reasonShort].filter(Boolean).join(' '));
  const words = hay.match(/[\p{L}\p{N}]+/gu) || [];
  return terms.every(term => words.some(word => word.startsWith(term)));
}"""


def main():
    path = Path("index.html")
    html = path.read_text(encoding="utf-8")
    if html.count(OLD) == 1 and NEW not in html:
        updated = html.replace(OLD, NEW, 1)
        path.write_text(updated, encoding="utf-8")
        print("Ricerca aggiornata: prefissi di parola, tutti i termini obbligatori.")
    elif OLD not in html and html.count(NEW) == 1:
        print("Ricerca gia aggiornata: nessuna modifica.")
    else:
        raise SystemExit("Funzione di ricerca inattesa: nessuna sostituzione eseguita.")


if __name__ == "__main__":
    main()
