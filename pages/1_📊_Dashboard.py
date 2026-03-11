"""
Docent Dashboard — Examencoach Maatschappijwetenschappen

Toont een overzicht van leerlinggebruik op basis van de Google Sheets-log.
Navigeer via de zijbalk naar deze pagina.
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import APP_TITLE
from src.sheets_logger import lees_resultaten

st.set_page_config(page_title=f"Dashboard — {APP_TITLE}", layout="wide")
st.title("📊 Docent Dashboard")
st.caption("Overzicht van leerlinggebruik van de Examencoach")

# ---------------------------------------------------------------------------
# Data laden
# ---------------------------------------------------------------------------

with st.spinner("Resultaten laden uit Google Sheets…"):
    rijen = lees_resultaten()

if not rijen:
    st.info(
        "Nog geen resultaten beschikbaar. "
        "Leerlingen worden zichtbaar nadat ze een vraag hebben beantwoord."
    )
    st.stop()

# ---------------------------------------------------------------------------
# Verwerking
# ---------------------------------------------------------------------------

import datetime
from collections import defaultdict

leerlingen: dict[str, dict] = defaultdict(lambda: {
    "sessies": set(),
    "vragen": 0,
    "score_p1_totaal": 0,
    "score_p1_teller": 0,
    "domeinen": set(),
    "laatste_activiteit": "",
})

for rij in rijen:
    naam = str(rij.get("Naam", "")).strip()
    if not naam:
        continue
    datum = str(rij.get("Tijdstempel", ""))[:10]  # "YYYY-MM-DD"
    domein = str(rij.get("Domein", ""))
    score_p1 = rij.get("Poging 1 Score")

    l = leerlingen[naam]
    l["sessies"].add(datum)
    l["vragen"] += 1
    l["domeinen"].add(domein)
    if datum > l["laatste_activiteit"]:
        l["laatste_activiteit"] = datum
    if score_p1 not in (None, ""):
        try:
            l["score_p1_totaal"] += int(score_p1)
            l["score_p1_teller"] += 1
        except (ValueError, TypeError):
            pass

# ---------------------------------------------------------------------------
# KPI-blokken
# ---------------------------------------------------------------------------

totaal_leerlingen = len(leerlingen)
totaal_vragen = sum(l["vragen"] for l in leerlingen.values())
actief_vandaag = sum(
    1 for l in leerlingen.values()
    if l["laatste_activiteit"] == datetime.date.today().strftime("%Y-%m-%d")
)

col1, col2, col3 = st.columns(3)
col1.metric("Leerlingen totaal", totaal_leerlingen)
col2.metric("Vragen beantwoord", totaal_vragen)
col3.metric("Actief vandaag", actief_vandaag)

st.divider()

# ---------------------------------------------------------------------------
# Leerlingtabel
# ---------------------------------------------------------------------------

st.subheader("Leerlingen")

tabel_data = []
for naam, l in sorted(leerlingen.items()):
    gem_score = (
        round(l["score_p1_totaal"] / l["score_p1_teller"], 1)
        if l["score_p1_teller"] > 0 else "—"
    )
    tabel_data.append({
        "Naam": naam,
        "Vragen": l["vragen"],
        "Sessies": len(l["sessies"]),
        "Gem. score (p1)": gem_score,
        "Domeinen": ", ".join(sorted(l["domeinen"])),
        "Laatste activiteit": l["laatste_activiteit"],
    })

st.dataframe(tabel_data, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Domein-verdeling
# ---------------------------------------------------------------------------

st.subheader("Vragen per domein")

domein_teller: dict[str, int] = defaultdict(int)
for rij in rijen:
    d = str(rij.get("Domein", "")).strip()
    if d:
        domein_teller[d] += 1

domein_df = [{"Domein": k, "Vragen": v} for k, v in sorted(domein_teller.items())]
st.bar_chart({r["Domein"]: r["Vragen"] for r in domein_df})

# ---------------------------------------------------------------------------
# Ruwe data (inklapbaar)
# ---------------------------------------------------------------------------

with st.expander("Alle resultaten (ruwe data)"):
    st.dataframe(rijen, use_container_width=True, hide_index=True)
