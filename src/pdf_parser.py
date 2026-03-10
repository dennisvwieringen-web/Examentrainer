"""
PDF Parser voor MaWi VWO-examens.

Bestandsnaamconventie: vw-{code}-{variant}-{jaar2}-{tijdvak}-{type}.pdf
  type: o = opgaven | b = bronnenboekje | c = correctievoorschrift

Uitvoerformaat per vraag (Vraag dataclass):
  id           "2025_tv2_1"
  jaar         2025
  tijdvak      2
  vraag_nummer "1"        (of "5a", "5b" voor deelvragen)
  opgave_nr    1
  opgave_titel "Vrijheidsbeeld"
  vraag_tekst  volledige vraagstelling incl. context-instructie
  bron_refs    ["tekst 1"]  (welke bronnen nodig zijn)
  domein       "Politiek & Democratie"
  max_punten   2
  is_mc        False
  mc_opties    {}           ({"A": "...", "B": "..."} voor MC)
  cv_fragment  volledige correct-antwoord tekst uit het CV
"""
import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

import fitz  # PyMuPDF

from config import DATA_DIR

# ---------------------------------------------------------------------------
# Domein-mapping per opgavetitel (handmatig, op basis van syllabus MaWi VWO)
# ---------------------------------------------------------------------------
OPGAVE_DOMEIN: dict[str, str] = {
    # ── Domein B: Vorming ────────────────────────────────────
    # Socialisatie, identiteit, cultuur, normen & waarden
    "vrijheidsbeeld":               "Vorming",
    "coffin homes":                 "Vorming",
    "multicultureel":               "Vorming",
    "migratie":                     "Vorming",
    "säg hej":                      "Vorming",
    "sag hej":                      "Vorming",
    "gelijkheidssprookje":          "Vorming",
    "mensen en dingen":             "Vorming",
    "slapen in het openbaar":       "Vorming",
    "waar blijft mijn tijd":        "Vorming",

    # ── Domein C: Verhouding ─────────────────────────────────
    # Macht, democratie, rechtsstaat, politiek, criminaliteit
    "politiek":                     "Verhouding",
    "democratie":                   "Verhouding",
    "burgemeester":                 "Verhouding",
    "politici":                     "Verhouding",
    "partij":                       "Verhouding",
    "denk":                         "Verhouding",
    "vertrouwen":                   "Verhouding",
    "burger":                       "Verhouding",
    "strijdpunten":                 "Verhouding",
    "euroscepsis":                  "Verhouding",
    "europese commissie":           "Verhouding",
    "duidelijke taal":              "Verhouding",
    "criminaliteit":                "Verhouding",
    "rechtsstaat":                  "Verhouding",
    "jihadi":                       "Verhouding",
    "hells angels":                 "Verhouding",
    "jeugdgroepen":                 "Verhouding",
    "boeven":                       "Verhouding",
    "strafhof":                     "Verhouding",
    "strafrecht":                   "Verhouding",
    "verkeersdelicten":             "Verhouding",
    "alcoholgebruik":               "Verhouding",
    "crimefighter":                 "Verhouding",
    "verbod":                       "Verhouding",
    "eilandstaten":                 "Verhouding",
    "micronatie":                   "Verhouding",
    "hongarije":                    "Verhouding",
    "europese unie":                "Verhouding",
    "soeverein":                    "Verhouding",

    # ── Domein D: Verandering ────────────────────────────────
    # Modernisering, globalisering, technologie, sociale verandering
    "globalisering":                "Verandering",
    "ebola":                        "Verandering",
    "kringlooplandbouw":            "Verandering",
    "meent en de oceaan":           "Verandering",
    "massatoerisme":                "Verandering",
    "colombia":                     "Verandering",
    "minister blok":                "Verandering",
    "internationaal":               "Verandering",
    "zuid-afrika":                  "Verandering",
    "zuid-chinese zee":             "Verandering",
    "klimaat":                      "Verandering",
    "aardgasvrij":                  "Verandering",
    "deeleconomie":                 "Verandering",
    "logeren bij locals":           "Verandering",
    "k-popfans":                    "Verandering",

    # ── Domein E: Binding ────────────────────────────────────
    # Sociale cohesie, groepen, netwerken, ongelijkheid, media
    "sociale media":                "Binding",
    "media":                        "Binding",
    "gepersonaliseerde":            "Binding",
    "burgerwetenschap":             "Binding",
    "voetbaljournalistiek":         "Binding",
    "overname":                     "Binding",
    "netwerk":                      "Binding",
    "activisme":                    "Binding",
    "ongelijkheid":                 "Binding",
    "problematisch":                "Binding",
    "self-tracking":                "Binding",
    "boycot":                       "Binding",
    "privacy":                      "Binding",
    "vloggers":                     "Binding",
    "persvrijheid":                 "Binding",
    "big data":                     "Binding",
    "booktok":                      "Binding",
    "reclame":                      "Binding",

    # Extra Vorming
    "wie heeft een relatie":        "Vorming",
    "wat is integratie":            "Vorming",
    "schaduw in los angeles":       "Vorming",
    "versierde nagels":             "Vorming",
    "integratie":                   "Vorming",

    # Extra Verhouding
    "opkomstplicht":                "Verhouding",
    "arib":                         "Verhouding",
    "nexitverlangens":              "Verhouding",
    "terug naar een meerderheid":   "Verhouding",
    "opiniepeilingen":              "Verhouding",
    "meerderheidsstelsel":          "Verhouding",

    # Extra Verandering
    "k80":                          "Verandering",
    "europese belasting":           "Verandering",
    "inflation reduction":          "Verandering",
    "visserijconflict":             "Verandering",
    "diplomatieke breuk":           "Verandering",
    "nicaragua":                    "Verandering",
}


def _domein_van_titel(titel: str) -> str:
    t = titel.lower()
    for sleutel, domein in OPGAVE_DOMEIN.items():
        if sleutel in t:
            return domein
    return "Overig"


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------
@dataclass
class Vraag:
    id: str
    jaar: int
    tijdvak: int
    vraag_nummer: str
    opgave_nr: int
    opgave_titel: str
    vraag_tekst: str
    bron_refs: list[str] = field(default_factory=list)
    domein: str = "Onbekend"
    max_punten: int = 1
    is_mc: bool = False
    mc_opties: dict[str, str] = field(default_factory=dict)
    cv_fragment: str = ""


# ---------------------------------------------------------------------------
# Tekst extraheren uit PDF
# ---------------------------------------------------------------------------

def _extract_text(pdf_path: Path) -> str:
    """Extraheert tekst pagina voor pagina. Sorteert blokken op y/x voor
    correcte leesrichting (helpt bij twee-koloms lay-out in bronnenboekje)."""
    doc = fitz.open(str(pdf_path))
    pagina_teksten = []
    for pagina in doc:
        # Haal tekstblokken op met coördinaten
        blokken = pagina.get_text("blocks")  # (x0,y0,x1,y1,tekst,blok_nr,type)
        # Sorteer: eerst op y (rij), dan op x (kolom) — leest links voor rechts
        blokken_gesorteerd = sorted(blokken, key=lambda b: (round(b[1] / 20) * 20, b[0]))
        tekst = "\n".join(b[4].strip() for b in blokken_gesorteerd if b[4].strip())
        pagina_teksten.append(tekst)
    doc.close()
    return "\n\n--- pagina ---\n\n".join(pagina_teksten)


# ---------------------------------------------------------------------------
# Parsing: Opgaven (-o)
# ---------------------------------------------------------------------------

# Opgave-header: "Opgave 1 Vrijheidsbeeld" of "Opgave 3 Eilandstaten vechten..."
RE_OPGAVE = re.compile(
    r"Opgave\s+(\d+)\s+(.+?)(?=\nOpgave\s+\d+|\Z)", re.DOTALL
)

# Vraagblok: "2p   1   Leg uit dat..."  of  "4p   4  –  Beredeneer..."
# Vangt ook deelvragen: "a  Leg uit..."  "b  Geef aan..."
RE_VRAAG_HEADER = re.compile(
    r"(\d+)p\s{1,6}(\d+[a-z]?)\s{1,8}(.+?)(?=\n\d+p\s{1,6}\d+|\Z)",
    re.DOTALL
)

# MC-opties: "A  een intergouvernementele organisatie"
RE_MC_OPTIE = re.compile(r"^\s*([A-F])\s{2,}(.+)$", re.MULTILINE)

# Bron-referentie: "Gebruik tekst 1", "Gebruik figuur 2", etc.
RE_BRON = re.compile(
    r"[Gg]ebruik\s+(tekst|figuur|afbeelding)\s*(\d+)", re.IGNORECASE
)


def _parse_bron_refs(tekst: str) -> list[str]:
    """Extraheert unieke bronreferenties uit vraagstelling."""
    return list({f"{m.group(1).lower()} {m.group(2)}"
                 for m in RE_BRON.finditer(tekst)})


def _parse_mc_opties(tekst: str) -> dict[str, str]:
    """Extraheert MC-opties als dict {"A": "tekst", ...}."""
    return {m.group(1): m.group(2).strip() for m in RE_MC_OPTIE.finditer(tekst)}


def parse_opgaven(pdf_path: Path, jaar: int, tijdvak: int) -> list[Vraag]:
    """Extraheert alle vragen uit een opgaven-PDF."""
    ruwe_tekst = _extract_text(pdf_path)
    prefix = f"{jaar}_tv{tijdvak}"
    vragen: list[Vraag] = []

    # Splits in opgaven
    for opgave_match in RE_OPGAVE.finditer(ruwe_tekst):
        opgave_nr = int(opgave_match.group(1))
        opgave_tekst = opgave_match.group(2)
        # Eerste regel = titel (tot eerste newline)
        opgave_titel = opgave_tekst.split("\n")[0].strip()
        domein = _domein_van_titel(opgave_titel)

        # Zoek vragen in dit opgaveblok
        for vraag_match in RE_VRAAG_HEADER.finditer(opgave_tekst):
            punten = int(vraag_match.group(1))
            nummer = vraag_match.group(2).strip()
            vraag_tekst = vraag_match.group(3).strip()

            mc_opties = _parse_mc_opties(vraag_tekst)
            bron_refs = _parse_bron_refs(opgave_tekst[:vraag_match.start()] + vraag_tekst)

            vragen.append(Vraag(
                id=f"{prefix}_{nummer}",
                jaar=jaar,
                tijdvak=tijdvak,
                vraag_nummer=nummer,
                opgave_nr=opgave_nr,
                opgave_titel=opgave_titel,
                vraag_tekst=vraag_tekst,
                bron_refs=bron_refs,
                domein=domein,
                max_punten=punten,
                is_mc=bool(mc_opties),
                mc_opties=mc_opties,
            ))

    return vragen


# ---------------------------------------------------------------------------
# Parsing: Bronnenboekje (-b)
# ---------------------------------------------------------------------------

RE_BRON_HEADER = re.compile(
    r"(?:tekst|figuur|afbeelding)\s+(\d+)\b",
    re.IGNORECASE
)


def parse_bronnen(pdf_path: Path) -> dict[str, str]:
    """
    Extraheert bronnen uit het bronnenboekje als dict:
    {"tekst 1": "<volledige tekst>", "tekst 2": "...", ...}
    Figuren en afbeeldingen worden als placeholder opgeslagen.
    """
    ruwe_tekst = _extract_text(pdf_path)
    bronnen: dict[str, str] = {}

    # Zoek sectie-headers
    posities: list[tuple[int, str]] = []
    for m in RE_BRON_HEADER.finditer(ruwe_tekst):
        label = m.group(0).lower().strip()
        posities.append((m.start(), label))

    # Pak tekst tussen opeenvolgende headers
    for i, (start, label) in enumerate(posities):
        einde = posities[i + 1][0] if i + 1 < len(posities) else len(ruwe_tekst)
        inhoud = ruwe_tekst[start:einde].strip()

        # Figuren / afbeeldingen zijn niet als tekst beschikbaar
        if label.startswith("figuur") or label.startswith("afbeelding"):
            bronnen[label] = f"[{label.upper()}: visueel materiaal — zie PDF bijlage]"
        else:
            # Schoon regelnummers op (5, 10, 15...) die links van de tekst staan
            inhoud = re.sub(r"(?m)^\s*\d{1,3}\s+", "", inhoud)
            bronnen[label] = inhoud

    return bronnen


# ---------------------------------------------------------------------------
# Parsing: Correctievoorschrift (-c) → cv_fragment per vraagnummer
# ---------------------------------------------------------------------------

RE_CV_VRAAG = re.compile(
    r"^\s*(\d+[a-z]?)\s+maximumscore\s+(\d+)(.*?)(?=^\s*\d+[a-z]?\s+maximumscore|\Z)",
    re.DOTALL | re.MULTILINE
)


def parse_cv(pdf_path: Path) -> dict[str, str]:
    """
    Extraheert CV-fragmenten als dict: {"1": "<cv tekst>", "2": "...", ...}
    MC-antwoorden (enkele letter) worden direct als cv_fragment opgeslagen.
    """
    ruwe_tekst = _extract_text(pdf_path)
    cv_map: dict[str, str] = {}

    for m in RE_CV_VRAAG.finditer(ruwe_tekst):
        nummer = m.group(1).strip()
        max_score = m.group(2)
        cv_inhoud = m.group(3).strip()
        cv_map[nummer] = f"maximumscore {max_score}\n{cv_inhoud}"

    # MC-vragen staan ook in het CV als bijv. "14  A" — pak ze op
    for m in re.finditer(r"^\s*(\d+)\s+([A-F])\s*$", ruwe_tekst, re.MULTILINE):
        cv_map[m.group(1)] = f"Juist antwoord: {m.group(2)}"

    return cv_map


# ---------------------------------------------------------------------------
# Koppelen: CV aan vragen
# ---------------------------------------------------------------------------

def koppel_cv(vragen: list[Vraag], cv_map: dict[str, str]) -> list[Vraag]:
    """Voeg het cv_fragment toe aan elke Vraag op basis van vraagnummer."""
    for v in vragen:
        if v.vraag_nummer in cv_map:
            v.cv_fragment = cv_map[v.vraag_nummer]
        # Fallback: hoofd-nummer voor deelvragen (5a → 5)
        elif v.vraag_nummer.rstrip("abcde") in cv_map:
            v.cv_fragment = cv_map[v.vraag_nummer.rstrip("abcde")]
    return vragen


# ---------------------------------------------------------------------------
# Sla op / laad JSON
# ---------------------------------------------------------------------------

def sla_op_als_json(vragen: list[Vraag], output_pad: Path) -> None:
    output_pad.parent.mkdir(parents=True, exist_ok=True)
    with open(output_pad, "w", encoding="utf-8") as f:
        json.dump([asdict(v) for v in vragen], f, ensure_ascii=False, indent=2)
    print(f"[parser] Opgeslagen: {len(vragen)} vragen -> {output_pad.name}")


def laad_vragen_uit_json(json_pad: Path) -> list[Vraag]:
    with open(json_pad, encoding="utf-8") as f:
        data = json.load(f)
    return [Vraag(**item) for item in data]
