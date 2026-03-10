"""
Google Sheets Logger.

Logt resultaten van leerlingen naar een geconfigureerde Google Spreadsheet.
Kolommen: Tijdstempel | Naam | Domein | Vraag | Poging1 | Poging2 | Feedback
"""
from __future__ import annotations

import datetime
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials

from config import GOOGLE_SHEETS_CREDENTIALS_FILE, GOOGLE_SHEETS_SPREADSHEET_ID

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

HEADER_ROW = [
    "Tijdstempel", "Naam", "Domein", "Vraag ID",
    "Poging 1 Score", "Poging 2 Score", "Feedback",
]


def _get_werkblad() -> gspread.Worksheet:
    """Maakt verbinding met Google Sheets en geeft het eerste werkblad terug."""
    creds = Credentials.from_service_account_file(
        str(GOOGLE_SHEETS_CREDENTIALS_FILE), scopes=SCOPES
    )
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(GOOGLE_SHEETS_SPREADSHEET_ID)
    werkblad = spreadsheet.sheet1

    # Voeg header toe als het blad leeg is
    if not werkblad.row_values(1):
        werkblad.append_row(HEADER_ROW)

    return werkblad


def log_resultaat(
    naam: str,
    domein: str,
    vraag_id: str,
    score_poging1: int,
    feedback: str,
    score_poging2: Optional[int] = None,
) -> None:
    """Voeg één rij toe aan de Google Spreadsheet."""
    try:
        werkblad = _get_werkblad()
        rij = [
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            naam,
            domein,
            vraag_id,
            score_poging1,
            score_poging2 if score_poging2 is not None else "",
            feedback,
        ]
        werkblad.append_row(rij)
    except Exception as e:
        # Logging-fouten mogen de app niet breken
        print(f"[Sheets] Kon resultaat niet loggen: {e}")
