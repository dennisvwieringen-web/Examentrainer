"""
Examencoach Maatschappijwetenschappen — Streamlit Frontend

Flow:
1. Leerling voert naam in en kiest een domein.
2. App toont één vraag tegelijk (met bron indien beschikbaar).
3. Leerling typt antwoord → AI-beoordeling via GPT-4o.
4. Feedback + tweede kans.
5. Resultaten worden gelogd in Google Sheets.
"""
import json
import random
from pathlib import Path

import streamlit as st

from config import APP_TITLE, DATA_DIR, DOMEINEN
from src.ai_grader import beoordeel_antwoord
from src.pdf_parser import Vraag, laad_vragen_uit_json
from src.sheets_logger import log_resultaat

st.set_page_config(page_title=APP_TITLE, layout="centered")
st.title(APP_TITLE)


# ---------------------------------------------------------------------------
# Hulpfuncties
# ---------------------------------------------------------------------------

@st.cache_data
def laad_alle_vragen() -> list[Vraag]:
    """Laad alle verwerkte JSON-bestanden uit data/processed/.
    Bronnen-bestanden (*_bronnen.json) worden overgeslagen — die bevatten
    geen Vraag-objecten maar een dict met bronteksten."""
    vragen = []
    for json_bestand in DATA_DIR.glob("*.json"):
        if json_bestand.name.endswith("-bronnen.json"):
            continue
        vragen.extend(laad_vragen_uit_json(json_bestand))
    return vragen


def filter_vragen(vragen: list[Vraag], domein: str) -> list[Vraag]:
    if domein == "Alle domeinen":
        return vragen
    return [v for v in vragen if v.domein == domein]


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
        alle_vragen = laad_alle_vragen()
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
    st.markdown(f"**{vraag.vraag_tekst}**")
    st.caption(f"Maximum: {vraag.max_punten} punt(en)  •  Poging {st.session_state.poging} van 2")

    with st.form("antwoord_form"):
        antwoord = st.text_area("Jouw antwoord", height=150, key=f"antw_{idx}_{st.session_state.poging}")
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
