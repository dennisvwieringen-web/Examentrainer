"""
Centrale configuratie voor de Examencoach applicatie.

Prioriteit voor secrets:
  1. st.secrets  — Streamlit Community Cloud (productie)
  2. .env        — lokale ontwikkeling
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def _secret(key: str, default: str = "") -> str:
    """Leest een secret uit st.secrets (Streamlit Cloud) of .env (lokaal)."""
    try:
        import streamlit as st
        val = st.secrets.get(key)
        if val is not None:
            return str(val)
    except Exception:
        pass
    return os.getenv(key, default)


# Paden
BASE_DIR = Path(__file__).parent
PDF_DIR  = BASE_DIR / _secret("PDF_DIR",  "data/pdfs")
DATA_DIR = BASE_DIR / _secret("DATA_DIR", "data/processed")
SYLLABUS_DIR = BASE_DIR / "data/syllabus"

# API Keys
OPENAI_API_KEY              = _secret("OPENAI_API_KEY")
GOOGLE_SHEETS_CREDENTIALS_FILE = BASE_DIR / _secret(
    "GOOGLE_SHEETS_CREDENTIALS_FILE", "credentials.json"
)
GOOGLE_SHEETS_SPREADSHEET_ID = _secret("GOOGLE_SHEETS_SPREADSHEET_ID")

# App instellingen
APP_TITLE    = _secret("APP_TITLE", "Examencoach Maatschappijwetenschappen")
OPENAI_MODEL = "gpt-4o"

# Domeinen uit de syllabus MaWi VWO (A t/m E)
# Domein A = Vaardigheden wordt herkend via trefwoorden in de vraagstelling.
DOMEINEN = [
    "A – Vaardigheden",  # onderzoeksmethoden, invalshoeken, hypothesen, variabelen
    "B – Vorming",       # socialisatie, identiteit, cultuur, normen & waarden
    "C – Verhouding",    # macht, democratie, rechtsstaat, politiek, criminaliteit
    "D – Verandering",   # modernisering, globalisering, technologie
    "E – Binding",       # sociale cohesie, groepen, netwerken, ongelijkheid, media
]
