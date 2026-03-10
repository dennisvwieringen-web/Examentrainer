"""
Ingest-script: verwerkt alle examens in data/pdfs/ naar JSON in data/processed/.

Gebruik:
    python scripts/ingest_pdfs.py

Bestandsnaamconventie (CvTE-standaard):
    vw-{code}-{variant}-{jaar2}-{tijdvak}-{type}.pdf
    voorbeeld: vw-1034-a-25-2-o.pdf

Het script:
1. Groepeert bestanden per examen (zelfde code+variant+jaar+tijdvak).
2. Extraheert vragen uit -o PDF.
3. Extraheert bronnen uit -b PDF (voor context in de app).
4. Extraheert CV-fragmenten uit -c PDF.
5. Koppelt alles en slaat op als JSON.
"""
import re
import sys
from pathlib import Path
from collections import defaultdict

# Zorg dat de projectroot in het pad staat
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import PDF_DIR, DATA_DIR
from src.pdf_parser import (
    Vraag,
    parse_opgaven,
    parse_bronnen,
    parse_cv,
    koppel_cv,
    sla_op_als_json,
)

# Patroon: vw-1034-a-25-2-o.pdf → groepen: code=1034, variant=a, jaar=25, tv=2, type=o
RE_BESTANDSNAAM = re.compile(
    r"vw-(\d+)-([a-z])-(\d{2})-(\d)-([obc])(?:-[a-z0-9]+)?\.pdf$", re.IGNORECASE
)


def _jaar_volledig(jaar_kort: str) -> int:
    """"25" → 2025, "98" → 1998."""
    j = int(jaar_kort)
    return 2000 + j if j < 50 else 1900 + j


def groepeer_bestanden(pdf_map: Path) -> dict[str, dict[str, Path]]:
    """
    Geeft een dict: {examen_id: {"o": path, "b": path, "c": path}}
    examen_id bijv. "1034-a-25-2"
    """
    groepen: dict[str, dict[str, Path]] = defaultdict(dict)

    for pdf in sorted(pdf_map.glob("*.pdf")):
        m = RE_BESTANDSNAAM.match(pdf.name)
        if not m:
            print(f"[skip] Bestandsnaam herkend niet: {pdf.name}")
            continue
        code, variant, jaar_kort, tijdvak, type_ = m.groups()
        examen_id = f"{code}-{variant}-{jaar_kort}-{tijdvak}"
        groepen[examen_id][type_.lower()] = pdf

    return groepen


def verwerk_examen(examen_id: str, bestanden: dict[str, Path]) -> list[Vraag]:
    """Verwerkt één examen (triplet o+b+c) naar een lijst Vraag-objecten."""
    parts = examen_id.split("-")
    jaar = _jaar_volledig(parts[2])
    tijdvak = int(parts[3])

    print(f"\n=== Verwerken: examen {examen_id} (VWO {jaar} tijdvak {tijdvak}) ===")

    # 1. Vragen uit opgaven-PDF
    if "o" not in bestanden:
        print(f"  [!] Geen opgaven-PDF gevonden voor {examen_id}, overgeslagen.")
        return []

    print(f"  [o] Vragen extraheren uit: {bestanden['o'].name}")
    vragen = parse_opgaven(bestanden["o"], jaar, tijdvak)
    print(f"      -> {len(vragen)} vragen gevonden")

    # 2. CV koppelen
    if "c" in bestanden:
        print(f"  [c] CV verwerken: {bestanden['c'].name}")
        cv_map = parse_cv(bestanden["c"])
        print(f"      -> {len(cv_map)} CV-items gevonden")
        vragen = koppel_cv(vragen, cv_map)
        zonder_cv = sum(1 for v in vragen if not v.cv_fragment)
        if zonder_cv:
            print(f"  [!] {zonder_cv} vragen zonder CV-koppeling")
    else:
        print(f"  [!] Geen CV-PDF gevonden voor {examen_id}")

    # 3. Bronnen-metadata (optioneel, voor toekomstig gebruik)
    if "b" in bestanden:
        print(f"  [b] Bronnen verwerken: {bestanden['b'].name}")
        bronnen = parse_bronnen(bestanden["b"])
        print(f"      -> {len(bronnen)} bronnen geïndexeerd: {list(bronnen.keys())}")
        # Sla bronnen op als apart JSON
        bronnen_pad = DATA_DIR / f"{examen_id}-bronnen.json"
        bronnen_pad.parent.mkdir(parents=True, exist_ok=True)
        import json
        with open(bronnen_pad, "w", encoding="utf-8") as f:
            json.dump(bronnen, f, ensure_ascii=False, indent=2)
        print(f"      -> Opgeslagen: {bronnen_pad.name}")

    return vragen


def main():
    print(f"PDF-map:       {PDF_DIR}")
    print(f"Output-map:    {DATA_DIR}")

    if not PDF_DIR.exists():
        print(f"\n[fout] PDF-map bestaat niet: {PDF_DIR}")
        print("Maak de map aan en plaats de PDF-bestanden hierin.")
        return

    groepen = groepeer_bestanden(PDF_DIR)
    if not groepen:
        print("\nGeen geldige PDF-bestanden gevonden.")
        print("Verwachte bestandsnaam: vw-{code}-{variant}-{jaar2}-{tijdvak}-{type}.pdf")
        print("Voorbeeld: vw-1034-a-25-2-o.pdf")
        return

    print(f"\n{len(groepen)} examen(s) gevonden: {list(groepen.keys())}")

    alle_vragen: list[Vraag] = []
    for examen_id, bestanden in sorted(groepen.items()):
        vragen = verwerk_examen(examen_id, bestanden)
        if vragen:
            # Sla per examen op
            output = DATA_DIR / f"{examen_id}.json"
            sla_op_als_json(vragen, output)
            alle_vragen.extend(vragen)

    # Overzicht
    print(f"\n{'='*50}")
    print(f"Totaal: {len(alle_vragen)} vragen verwerkt uit {len(groepen)} examen(s).")

    # Domeinen-overzicht
    from collections import Counter
    domein_teller = Counter(v.domein for v in alle_vragen)
    print("\nVragen per domein:")
    for domein, aantal in sorted(domein_teller.items()):
        print(f"  {domein:<40} {aantal:>3}")

    # Kwaliteitscheck
    zonder_cv = [v for v in alle_vragen if not v.cv_fragment]
    if zonder_cv:
        print(f"\n[!] {len(zonder_cv)} vragen zonder CV-fragment:")
        for v in zonder_cv:
            print(f"    vraag {v.vraag_nummer} (id: {v.id})")


if __name__ == "__main__":
    main()
