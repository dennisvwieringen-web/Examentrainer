"""
E-mail verzender voor de Examencoach.

Stuurt een HTML-overzicht van leerlinggebruik naar de docent.
Gebruikt SMTP (standaard Gmail) met credentials uit config / st.secrets.
"""
from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import EMAIL_RECIPIENT, SMTP_HOST, SMTP_PASSWORD, SMTP_PORT, SMTP_USER


def _bouw_html_tabel(rijen: list[dict]) -> str:
    """Zet resultatenrijen om naar een gestijlde HTML-tabel."""
    if not rijen:
        return "<p>Nog geen gebruik geregistreerd.</p>"

    # Groepeer: per leerling de eerste en laatste activiteit + aantal vragen
    leerlingen: dict[str, dict] = {}
    activiteiten: list[dict] = []

    for rij in rijen:
        naam      = str(rij.get("Naam", "")).strip()
        tijdstip  = str(rij.get("Tijdstempel", ""))
        domein    = str(rij.get("Domein", ""))
        if not naam:
            continue
        activiteiten.append({"naam": naam, "tijdstip": tijdstip, "domein": domein})
        if naam not in leerlingen:
            leerlingen[naam] = {"eerste": tijdstip, "laatste": tijdstip, "vragen": 0}
        leerlingen[naam]["vragen"] += 1
        if tijdstip > leerlingen[naam]["laatste"]:
            leerlingen[naam]["laatste"] = tijdstip

    # Tabel 1: samenvatting per leerling
    rijen_html = ""
    for naam, info in sorted(leerlingen.items()):
        rijen_html += (
            f"<tr>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #eee;'>{naam}</td>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #eee;'>{info['eerste']}</td>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #eee;'>{info['laatste']}</td>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #eee;text-align:center;'>{info['vragen']}</td>"
            f"</tr>"
        )

    # Tabel 2: alle sessies (laatste 30 regels, recentste eerst)
    recente = sorted(activiteiten, key=lambda r: r["tijdstip"], reverse=True)[:30]
    sessie_rijen = ""
    for a in recente:
        sessie_rijen += (
            f"<tr>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #eee;color:#555;font-size:13px;'>{a['tijdstip']}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #eee;color:#555;font-size:13px;'>{a['naam']}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #eee;color:#555;font-size:13px;'>{a['domein']}</td>"
            f"</tr>"
        )

    return f"""
    <h2 style='font-family:sans-serif;color:#1a1a2e;margin-bottom:4px;'>
        Examencoach Maatschappijwetenschappen
    </h2>
    <p style='font-family:sans-serif;color:#555;margin-top:0;'>Overzicht leerlinggebruik</p>

    <h3 style='font-family:sans-serif;color:#333;'>Per leerling</h3>
    <table style='border-collapse:collapse;font-family:sans-serif;width:100%;max-width:600px;'>
      <thead>
        <tr style='background:#1a1a2e;color:white;'>
          <th style='padding:10px 12px;text-align:left;'>Naam</th>
          <th style='padding:10px 12px;text-align:left;'>Eerste gebruik</th>
          <th style='padding:10px 12px;text-align:left;'>Laatste gebruik</th>
          <th style='padding:10px 12px;text-align:center;'>Vragen</th>
        </tr>
      </thead>
      <tbody>{rijen_html}</tbody>
    </table>

    <h3 style='font-family:sans-serif;color:#333;margin-top:2em;'>Recente activiteit (max. 30)</h3>
    <table style='border-collapse:collapse;font-family:sans-serif;width:100%;max-width:600px;'>
      <thead>
        <tr style='background:#444;color:white;'>
          <th style='padding:8px 10px;text-align:left;'>Tijdstip</th>
          <th style='padding:8px 10px;text-align:left;'>Naam</th>
          <th style='padding:8px 10px;text-align:left;'>Domein</th>
        </tr>
      </thead>
      <tbody>{sessie_rijen}</tbody>
    </table>
    """


def stuur_overzicht(rijen: list[dict]) -> None:
    """Verzendt een HTML-overzicht van leerlinggebruik naar EMAIL_RECIPIENT.

    Gooit een Exception als de verbinding mislukt zodat de aanroeper dit kan
    tonen in de UI.
    """
    if not SMTP_USER or not SMTP_PASSWORD:
        raise ValueError(
            "SMTP_USER en SMTP_PASSWORD zijn niet ingesteld. "
            "Vul ze in via .env (lokaal) of Streamlit secrets (cloud)."
        )

    html_body = _bouw_html_tabel(rijen)

    bericht = MIMEMultipart("alternative")
    bericht["Subject"] = "Examencoach — leerlingoverzicht"
    bericht["From"]    = SMTP_USER
    bericht["To"]      = EMAIL_RECIPIENT

    bericht.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, EMAIL_RECIPIENT, bericht.as_string())
