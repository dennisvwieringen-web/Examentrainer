"""
Docent Dashboard — Examencoach Maatschappijwetenschappen

Toont wie de examencoach heeft gebruikt en wanneer.
Stuurt op verzoek een overzicht per mail naar de docent.
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import APP_TITLE, EMAIL_RECIPIENT
from src.sheets_logger import lees_resultaten
from src.email_sender import stuur_overzicht

st.set_page_config(page_title=f"Dashboard — {APP_TITLE}", layout="centered")
st.title("📊 Leerlingoverzicht")
st.caption("Wie heeft de Examencoach gebruikt en wanneer?")

# ── Data laden ───────────────────────────────────────────────────────────────
with st.spinner("Resultaten ophalen…"):
    rijen = lees_resultaten()

if not rijen:
    st.info("Nog geen gebruik geregistreerd. Zodra een leerling een vraag beantwoordt, verschijnt die hier.")
    st.stop()

# ── Overzichtstabel: per leerling ─────────────────────────────────────────────
leerlingen: dict[str, dict] = {}
for rij in rijen:
    naam     = str(rij.get("Naam", "")).strip()
    tijdstip = str(rij.get("Tijdstempel", ""))
    domein   = str(rij.get("Domein", ""))
    if not naam:
        continue
    if naam not in leerlingen:
        leerlingen[naam] = {"eerste": tijdstip, "laatste": tijdstip, "vragen": 0, "domeinen": set()}
    leerlingen[naam]["vragen"] += 1
    leerlingen[naam]["domeinen"].add(domein)
    if tijdstip < leerlingen[naam]["eerste"]:
        leerlingen[naam]["eerste"] = tijdstip
    if tijdstip > leerlingen[naam]["laatste"]:
        leerlingen[naam]["laatste"] = tijdstip

tabel = [
    {
        "Naam":            naam,
        "Eerste gebruik":  info["eerste"],
        "Laatste gebruik": info["laatste"],
        "Vragen":          info["vragen"],
        "Domeinen":        ", ".join(sorted(info["domeinen"])),
    }
    for naam, info in sorted(leerlingen.items())
]

st.metric("Leerlingen", len(leerlingen))
st.dataframe(tabel, use_container_width=True, hide_index=True)

# ── Recente activiteit ────────────────────────────────────────────────────────
with st.expander("Alle activiteit (tijdlijn)"):
    tijdlijn = sorted(
        [{"Tijdstip": r.get("Tijdstempel",""), "Naam": r.get("Naam",""), "Domein": r.get("Domein","")}
         for r in rijen if r.get("Naam","").strip()],
        key=lambda x: x["Tijdstip"],
        reverse=True,
    )
    st.dataframe(tijdlijn, use_container_width=True, hide_index=True)

# ── Mailknop ─────────────────────────────────────────────────────────────────
st.divider()
if st.button(f"📧 Stuur overzicht naar {EMAIL_RECIPIENT}", type="primary"):
    with st.spinner("E-mail verzenden…"):
        try:
            stuur_overzicht(rijen)
            st.success(f"✅ Overzicht verstuurd naar **{EMAIL_RECIPIENT}**")
        except Exception as fout:
            st.error(f"❌ Verzenden mislukt: {fout}")
