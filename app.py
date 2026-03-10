"""
Examencoach Maatschappijwetenschappen — Streamlit Frontend

Flow:
1. Leerling voert naam in en kiest een domein.
2. App toont één vraag tegelijk (met bron indien beschikbaar).
3. Leerling typt antwoord → AI-beoordeling via GPT-4o.
4. Feedback + tweede kans.
5. Resultaten worden gelogd in Google Sheets.
"""
import html as _html
import json
import random
import re
from pathlib import Path

import streamlit as st

from config import APP_TITLE, DATA_DIR, DOMEINEN
from src.ai_grader import beoordeel_antwoord
from src.pdf_parser import Vraag, laad_vragen_uit_json
from src.sheets_logger import log_resultaat

st.set_page_config(page_title=APP_TITLE, layout="wide")
st.title(APP_TITLE)


# ---------------------------------------------------------------------------
# Hulpfuncties
# ---------------------------------------------------------------------------

# Trefwoorden voor Domein A – Vaardigheden (onderzoeksmethoden, invalshoeken)
_VAARDIGHEID_TREFWOORDEN = re.compile(
    r"\b(hypothese|variabele|kwalitatief|kwantitatief|steekproef|populatie|"
    r"representatief|observati|interview|enquête|vragenlijst|inhoudsanalys|"
    r"literatuuronderzoek|onderzoeksmethode|betrouwbaarheid|validiteit|"
    r"invalshoek|benaderingswijze|sociaaleconomisch|sociaal-cultureel|"
    r"sociaalpsychologisch|politicologisch|onderzoeksopzet|operationalis)\w*",
    re.IGNORECASE,
)


def _reinig_brontekst(tekst: str) -> str:
    """Herstelt kolomafbrekingen en verwijdert PDF-artefacten uit bronteksten.

    PDF-extractie levert tekst in smalle kolommen op (elke regel ~6 woorden).
    Deze functie voegt die fragmentregels samen tot vloeiende alinea's.
    """
    # ── Verwijder PDF-rommel ────────────────────────────────────────────────
    tekst = re.sub(r"--- pagina ---", "", tekst)
    tekst = re.sub(r"VW-\S+\s*/\s*\d+\s*", "", tekst)
    tekst = re.sub(r"lees verder\s*►+", "", tekst)

    # ── Verwijder "tekst X" / "figuur X" header-regel bovenaan ─────────────
    tekst = re.sub(r"(?im)^\s*(?:tekst|figuur|afbeelding)\s+\d+\s*$", "", tekst)

    # ── Splits in blokken op lege regels (echte alinea-grenzen) ────────────
    blokken = re.split(r"\n{2,}", tekst)

    alineas = []
    for blok in blokken:
        regels = [r.strip() for r in blok.splitlines() if r.strip()]
        if not regels:
            continue
        # Voeg kolomfragmenten samen tot één doorlopende alinea
        alinea = " ".join(regels)
        alinea = re.sub(r"  +", " ", alinea)
        alineas.append(alinea)

    return "\n\n".join(alineas).strip()


def _reinig_vraag_tekst(tekst: str) -> str:
    """Verwijdert PDF-artefacten uit vraag-teksten (paginamarkeringen, voetteksten)."""
    tekst = re.sub(r"--- pagina ---\s*", " ", tekst)
    tekst = re.sub(r"VW-\S+\s*/\s*\d+\s*", "", tekst)
    tekst = re.sub(r"lees verder\s*►+\s*", "", tekst)
    tekst = re.sub(r"\n{3,}", "\n\n", tekst)
    return tekst.strip()


def _als_html(tekst: str, vet: bool = False) -> str:
    """Zet platte tekst om naar veilige HTML-paragrafen (escaped, newlines → <br>)."""
    stijl = "font-weight:600;" if vet else ""
    paragrafen = "".join(
        f"<p style='margin:0 0 0.7em 0;{stijl}'>"
        f"{_html.escape(p).replace(chr(10), '<br>')}</p>"
        for p in tekst.split("\n\n")
        if p.strip()
    )
    return paragrafen


@st.cache_data
def laad_alle_vragen() -> tuple[list[Vraag], dict[str, dict[str, str]]]:
    """Laad alle verwerkte JSON-bestanden uit data/processed/.

    Retourneert:
      vragen        – lijst van alle Vraag-objecten
      bronnen_lookup – {vraag_id: {"tekst 1": "<tekst>", ...}}
    """
    vragen: list[Vraag] = []
    bronnen_lookup: dict[str, dict[str, str]] = {}

    for json_bestand in sorted(DATA_DIR.glob("*.json")):
        if json_bestand.name.endswith("-bronnen.json"):
            continue

        vraag_lijst = laad_vragen_uit_json(json_bestand)
        vragen.extend(vraag_lijst)

        # Laad bijbehorend bronnenbestand indien aanwezig
        bronnen_bestand = DATA_DIR / (json_bestand.stem + "-bronnen.json")
        if bronnen_bestand.exists():
            with open(bronnen_bestand, encoding="utf-8") as f:
                bronnen_data: dict[str, str] = json.load(f)

            for vraag in vraag_lijst:
                # Detecteer referenties: via bron_refs + scan vraag_tekst
                refs: set[str] = set(vraag.bron_refs)
                for m in re.finditer(r"\btekst\s+(\d+)\b", vraag.vraag_tekst, re.IGNORECASE):
                    refs.add(f"tekst {m.group(1)}")

                if refs:
                    bronnen_lookup[vraag.id] = {
                        label: _reinig_brontekst(bronnen_data[label])
                        for label in sorted(refs)
                        if label in bronnen_data
                    }

    return vragen, bronnen_lookup


def filter_vragen(vragen: list[Vraag], domein: str) -> list[Vraag]:
    if domein == "Alle domeinen":
        return vragen
    # Strip optionele letter-prefix ("B – Vorming" → "Vorming")
    basis = domein.split("–")[-1].strip()
    if basis == "Vaardigheden":
        # Domein A loopt door alle opgaven heen: detecteer op trefwoorden
        return [v for v in vragen if _VAARDIGHEID_TREFWOORDEN.search(v.vraag_tekst)]
    return [v for v in vragen if v.domein == basis]


# ---------------------------------------------------------------------------
# Sessiebeheer
# ---------------------------------------------------------------------------

if "stap" not in st.session_state:
    st.session_state.stap = "login"        # login | vraag | feedback | klaar
if "huidige_vraag" not in st.session_state:
    st.session_state.huidige_vraag = None
if "poging" not in st.session_state:
    st.session_state.poging = 1
if "score_p1" not in st.session_state:
    st.session_state.score_p1 = None
if "bronnen_lookup" not in st.session_state:
    st.session_state.bronnen_lookup = {}


# ---------------------------------------------------------------------------
# Stap 1: Login
# ---------------------------------------------------------------------------

if st.session_state.stap == "login":
    with st.form("login_form"):
        naam = st.text_input("Jouw naam")
        domein = st.selectbox("Kies een domein om te oefenen", ["Alle domeinen"] + DOMEINEN)
        submit = st.form_submit_button("Start oefenen →")

    if submit and naam:
        st.session_state.naam = naam
        st.session_state.domein = domein
        alle_vragen, bronnen_lookup = laad_alle_vragen()
        st.session_state.bronnen_lookup = bronnen_lookup
        beschikbare_vragen = filter_vragen(alle_vragen, domein)

        if not beschikbare_vragen:
            st.warning("Geen vragen gevonden voor dit domein. Voeg eerst PDF's toe via scripts/ingest_pdfs.py.")
        else:
            st.session_state.vragen_pool = beschikbare_vragen
            random.shuffle(st.session_state.vragen_pool)
            st.session_state.vraag_index = 0
            st.session_state.stap = "vraag"
            st.rerun()


# ---------------------------------------------------------------------------
# Stap 2: Vraag tonen + antwoord invullen
# ---------------------------------------------------------------------------

elif st.session_state.stap == "vraag":
    pool = st.session_state.vragen_pool
    idx = st.session_state.vraag_index

    if idx >= len(pool):
        st.session_state.stap = "klaar"
        st.rerun()

    vraag: Vraag = pool[idx]
    st.session_state.huidige_vraag = vraag

    st.subheader(f"Vraag {idx + 1} / {len(pool)}  •  {vraag.domein}")

    # ── Bronteksten scheiden: leesbare tekst vs. visueel materiaal ────────
    bronnen = st.session_state.bronnen_lookup.get(vraag.id, {})
    tekst_bronnen = {
        k: v for k, v in bronnen.items()
        if not v.startswith("[FIGUUR") and not v.startswith("[AFBEELDING")
    }
    visuele_bronnen = [k for k, v in bronnen.items()
                       if v.startswith("[FIGUUR") or v.startswith("[AFBEELDING")]

    # ── Visuele bronnen: compacte melding ─────────────────────────────────
    if visuele_bronnen:
        labels = ", ".join(k.capitalize() for k in sorted(visuele_bronnen))
        st.caption(f"📊 {labels}: visueel materiaal — raadpleeg het originele examen.")

    # ── Layout: gesplitst leesvenster of volledig breed ───────────────────
    if tekst_bronnen:
        col_bron, col_vraag = st.columns([1, 1], gap="large")
        vraag_container = col_vraag

        with col_bron:
            # Bouw scrollbaar HTML-leesvenster
            bron_html_parts = []
            for label, tekst in tekst_bronnen.items():
                paragrafen = "".join(
                    f"<p style='margin:0 0 0.85em 0;line-height:1.8;'>"
                    f"{_html.escape(p).replace(chr(10), '<br>')}</p>"
                    for p in tekst.split("\n\n")
                    if p.strip()
                )
                bron_html_parts.append(
                    f"<div style='margin-bottom:1.5em;'>"
                    f"<span style='font-size:0.8em;font-weight:700;text-transform:uppercase;"
                    f"letter-spacing:0.06em;opacity:0.55;'>📄 {_html.escape(label.capitalize())}</span>"
                    f"<hr style='border:none;border-top:1px solid rgba(128,128,128,0.3);"
                    f"margin:0.4em 0 0.9em;'>"
                    f"{paragrafen}</div>"
                )
            st.markdown(
                f'<div style="height:72vh;overflow-y:auto;padding:1.1rem 1.4rem;'
                f'background:rgba(128,128,128,0.06);border-radius:10px;'
                f'border:1px solid rgba(128,128,128,0.2);font-size:0.92em;">'
                f'{"".join(bron_html_parts)}</div>',
                unsafe_allow_html=True,
            )
    else:
        vraag_container = st.container()

    # ── Vraag tonen + antwoordformulier ───────────────────────────────────
    vraag_tekst_schoon = _reinig_vraag_tekst(vraag.vraag_tekst)

    with vraag_container:
        st.markdown(
            f'<div style="font-size:1em;line-height:1.75;margin-bottom:0.6em;">'
            f'{_als_html(vraag_tekst_schoon, vet=True)}</div>',
            unsafe_allow_html=True,
        )
        st.caption(f"Maximum: {vraag.max_punten} punt(en)  •  Poging {st.session_state.poging} van 2")

        with st.form("antwoord_form"):
            antwoord = st.text_area(
                "Jouw antwoord", height=150, key=f"antw_{idx}_{st.session_state.poging}"
            )
            submit = st.form_submit_button("Controleer antwoord")

    if submit and antwoord.strip():
        with st.spinner("AI beoordeelt jouw antwoord…"):
            beoordeling = beoordeel_antwoord(
                vraag_tekst=vraag.vraag_tekst,
                cv_fragment=vraag.cv_fragment,
                leerling_antwoord=antwoord,
                max_punten=vraag.max_punten,
            )

        st.session_state.beoordeling = beoordeling
        st.session_state.antwoord = antwoord

        if st.session_state.poging == 1:
            st.session_state.score_p1 = beoordeling.score

        st.session_state.stap = "feedback"
        st.rerun()


# ---------------------------------------------------------------------------
# Stap 3: Feedback tonen
# ---------------------------------------------------------------------------

elif st.session_state.stap == "feedback":
    vraag = st.session_state.huidige_vraag
    b = st.session_state.beoordeling
    poging = st.session_state.poging

    # ── Scorebalk ──────────────────────────────────────────────────────────
    kleur = "green" if b.volledig_correct else "orange" if b.score > 0 else "red"
    st.markdown(f"### Score: :{kleur}[{b.score} / {b.max_punten}]")

    # ── Per-criterium breakdown ────────────────────────────────────────────
    if b.criteria:
        st.markdown("**Beoordeling per criterium:**")
        for c in b.criteria:
            icoon = "✅" if c.behaald else "❌"
            achtergrond = "#d4edda" if c.behaald else "#f8d7da"
            tekst_kleur = "#155724" if c.behaald else "#721c24"
            st.markdown(
                f"""<div style="
                    background:{achtergrond};
                    color:{tekst_kleur};
                    border-radius:6px;
                    padding:8px 12px;
                    margin-bottom:6px;
                    font-size:0.93em;
                ">
                {icoon} <strong>{c.criterium}</strong><br>
                <span style="font-style:italic; opacity:0.85;">{c.toelichting}</span>
                </div>""",
                unsafe_allow_html=True,
            )
        st.markdown("")  # ruimte voor de volgende sectie

    # ── Overkoepelende feedback + ontbrekend ──────────────────────────────
    st.info(b.feedback)
    if b.ontbrekend:
        st.warning(f"**Ontbreekt:** {b.ontbrekend}")

    # ── Navigatieknoppen ──────────────────────────────────────────────────
    col1, col2 = st.columns(2)

    if not b.volledig_correct and poging == 1:
        if col1.button("Probeer opnieuw"):
            st.session_state.poging = 2
            st.session_state.stap = "vraag"
            st.rerun()

    if col2.button("Volgende vraag →"):
        # Log naar Google Sheets
        log_resultaat(
            naam=st.session_state.naam,
            domein=vraag.domein,
            vraag_id=vraag.id,
            score_poging1=st.session_state.score_p1,
            feedback=b.feedback,
            score_poging2=b.score if poging == 2 else None,
        )
        st.session_state.vraag_index += 1
        st.session_state.poging = 1
        st.session_state.score_p1 = None
        st.session_state.stap = "vraag"
        st.rerun()


# ---------------------------------------------------------------------------
# Stap 4: Klaar
# ---------------------------------------------------------------------------

elif st.session_state.stap == "klaar":
    st.success(f"Goed gedaan, {st.session_state.naam}! Je hebt alle vragen beantwoord.")
    st.balloons()
    if st.button("Opnieuw beginnen"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
