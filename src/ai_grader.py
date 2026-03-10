"""
AI Grader — beoordeelt leerlingantwoorden via OpenAI GPT-4o.

Scoringsmethode: per-criterium, conform de CV-structuur van CvTE.
Het CV heeft altijd twee secties:
  1. "Een juist antwoord bevat:" — de scoringsrubric (elk bullet = 1 punt)
  2. "voorbeeld van een juist antwoord:" — illustratief referentiemateriaal

De AI beoordeelt ELK criterium afzonderlijk en kent per criterium 0 of 1 punt
toe. De totaalscore is de som van de behaalde criteria-punten.
"""
import json
from dataclasses import dataclass, field

from openai import OpenAI

from config import OPENAI_API_KEY, OPENAI_MODEL

client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEEM_PROMPT = """Je bent een examencorrector voor het vak Maatschappijwetenschappen (VWO).

## Jouw taak
Je beoordeelt het antwoord van een leerling op basis van het officiële correctievoorschrift (CV).

## Hoe het CV werkt
Het CV heeft twee secties:
1. "Een juist antwoord bevat:" — dit zijn de SCORINGSCRITERIA. Elk bullet-punt is precies 1 punt.
2. "voorbeeld van een juist antwoord:" — dit is een voorbeelduitwerking ter referentie.

## Scoringsregels (conform CvTE-richtlijnen)
- Beoordeel ELK criterium uit "een juist antwoord bevat" los van de andere.
- Ken per criterium 0 of 1 punt toe.
- Beoordeel op de ESSENTIE: de leerling hoeft niet letterlijk te formuleren zoals het voorbeeld.
- Als een criterium vraagt om "een toepassing van kernconcept X": check of de kern van dat concept correct is toegepast, ook als de precieze definitie iets anders geformuleerd is.
- Als een criterium vraagt om "informatie uit tekst/figuur X": check of relevante inhoud uit die bron is gebruikt.
- Spelling en woordkeuze tellen NIET mee.
- Als een gevraagde redenering of uitleg ontbreekt: 0 punten voor dat criterium.

## Outputformaat
Geef je beoordeling als JSON met deze exacte structuur:
{
  "score": <int, som van behaalde punten>,
  "max_punten": <int, totaal aantal criteria>,
  "volledig_correct": <bool, true als score == max_punten>,
  "criteria": [
    {
      "criterium": "<tekst van het criterium uit het CV>",
      "behaald": <bool>,
      "toelichting": "<één zin: waarom wel/niet behaald>"
    }
  ],
  "feedback": "<2-3 zinnen overkoepelende feedback gericht aan de leerling>",
  "ontbrekend": "<beknopte opsomming van wat nog mist, leeg als volledig correct>"
}"""


@dataclass
class CriteriumBeoordeling:
    criterium: str
    behaald: bool
    toelichting: str


@dataclass
class Beoordeling:
    score: int
    max_punten: int
    volledig_correct: bool
    criteria: list[CriteriumBeoordeling] = field(default_factory=list)
    feedback: str = ""
    ontbrekend: str = ""


def beoordeel_antwoord(
    vraag_tekst: str,
    cv_fragment: str,
    leerling_antwoord: str,
    max_punten: int,
) -> Beoordeling:
    """
    Stuurt vraag + CV + antwoord naar GPT-4o en geeft een Beoordeling terug.

    Parameters:
        vraag_tekst:       Volledige vraagstelling inclusief context-instructies.
        cv_fragment:       Het CV-fragment: bevat BEIDE secties (criteria + voorbeeld).
        leerling_antwoord: Wat de leerling heeft ingetypt.
        max_punten:        Maximaal te behalen punten (= aantal criteria in CV).
    """
    gebruiker_prompt = f"""**Vraag aan de leerling:**
{vraag_tekst}

**Correctievoorschrift (CV):**
{cv_fragment}

**Antwoord van de leerling:**
{leerling_antwoord}

Beoordeel nu elk criterium uit "een juist antwoord bevat" afzonderlijk en geef de JSON-output."""

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": SYSTEEM_PROMPT},
            {"role": "user", "content": gebruiker_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,  # Zo laag mogelijk voor consistente, reproduceerbare scores
    )

    data = json.loads(response.choices[0].message.content)

    criteria = [
        CriteriumBeoordeling(
            criterium=c["criterium"],
            behaald=c["behaald"],
            toelichting=c["toelichting"],
        )
        for c in data.get("criteria", [])
    ]

    return Beoordeling(
        score=data["score"],
        max_punten=data["max_punten"],
        volledig_correct=data["volledig_correct"],
        criteria=criteria,
        feedback=data.get("feedback", ""),
        ontbrekend=data.get("ontbrekend", ""),
    )
