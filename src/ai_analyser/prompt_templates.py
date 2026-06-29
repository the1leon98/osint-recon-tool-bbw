"""
Prompt-Templates für die LLM-gestützte OSINT-Risikoanalyse.

Enthält sorgfältig formulierte Prompt-Schablonen, die das LLM in
die Rolle eines OSINT-Sicherheitsanalysten versetzen und strukturierte
JSON-Ausgaben erzwingen. Jeder Prompt ist so konstruiert, dass er:

1. Die Rolle klar definiert (Persona-Pattern)
2. Das exakte JSON-Ausgabeformat vorgibt (Schema-Enforcement)
3. Halluzinationen durch konkrete Ankerpunkte minimiert
4. Fallback-Logik vorsieht („wenn keine Daten vorhanden, dann ...")

Prompt-Engineering-Prinzipien:
- Keine offenen Fragen → immer strukturierte Antwort erzwingen
- Beispiele geben dem Modell Anker für das Format
- „WICHTIG:"-Marker für kritische Constraints
- JSON-Schema INLINE, nicht als externen Verweis

Beispiel für build_risk_prompt-Ausgabe:
    {
      "risk_score": 72,
      "attack_surface": [
        "LinkedIn: Berufshistorie ermöglicht Spear-Phishing",
        "GitHub: Code-Repositories verraten Technologie-Stack"
      ],
      "summary": "Hohes Risiko durch starke berufliche Online-Präsenz..."
    }

Autor: Rayquaza
Datum: 2026-06-29
"""

import json
from typing import Any


# =========================================================================
# SYSTEM-PROMPT: Definiert die KI-Persona für alle Analyse-Calls
# =========================================================================

SYSTEM_PROMPT = (
    "Du bist ein erfahrener OSINT-Sicherheitsanalyst mit Spezialisierung "
    "auf digitale Angriffsflächenanalyse. Du bewertest die Auffindbarkeit "
    "persönlicher Daten im Internet und identifizierst Risiken für "
    "Identitätsdiebstahl, Social Engineering und gezielte Angriffe.\n\n"
    "Deine Analysen sind präzise, faktenbasiert und immer mit konkreten "
    "Beispielen belegt. Du trennst strikt zwischen Fakten (belegbare Funde) "
    "und Interpretation (abgeleitete Risiken).\n\n"
    "KRITISCH: Antworte AUSSCHLIESSLICH mit validem JSON. Kein Markdown, "
    "keine Code-Blöcke (```), keine Erklärungen außerhalb des JSON-Objekts. "
    "Kein einleitender Text, kein abschließender Text — NUR das JSON-Objekt "
    "von { bis }."
)

# =========================================================================
# JSON-Schema-Vorlagen (als Python-Dicts, werden bei Bedarf serialisiert)
# =========================================================================

_RISK_SCHEMA: dict[str, Any] = {
    "risk_score": 0,
    "attack_surface": [],
    "summary": "",
}

_PROFILE_SCHEMA: dict[str, Any] = {
    "digital_footprint": "",
    "key_findings": [],
    "privacy_score": 0,
    "recommendations": [],
}


# =========================================================================
# Prompt-Builder
# =========================================================================

def build_risk_prompt(aggregated_data: dict[str, Any]) -> str:
    """
    Baut den detaillierten Prompt für die Risikoanalyse.

    Struktur:
        1. Kontext: Benutzername und Anzahl gefundener Profile
        2. Daten: Plattform-Liste mit URLs und Konfidenzen
        3. Aufgabe: Drei Bewertungsdimensionen
        4. Schema: Exaktes JSON-Format mit Constraints

    Args:
        aggregated_data: Aggregiertes Daten-Dict aus ResultAggregator.aggregate().
                         Erwartete Keys: username, total_profiles, platforms,
                         distribution, distribution_percent.

    Returns:
        Vollständiger Prompt-String für den OpenAI-API-Call.

    Example:
        >>> data = {"username": "max_mustermann", "total_profiles": 5, ...}
        >>> prompt = build_risk_prompt(data)
        >>> print(prompt[:100])
        Analysiere die folgende OSINT-Datenerhebung für den Benutzernamen...
    """
    username = aggregated_data.get("username", "UNBEKANNT")
    total_profiles = aggregated_data.get("total_profiles", 0)
    platforms: dict[str, dict] = aggregated_data.get("platforms", {})
    distribution: dict[str, int] = aggregated_data.get("distribution", {})
    distribution_pct: dict[str, float] = aggregated_data.get("distribution_percent", {})

    # === Plattform-Liste als Text aufbereiten ===
    if platforms:
        platform_lines: list[str] = []
        for norm_url, info in platforms.items():
            plat_name = info.get("platform", "?")
            url = info.get("url", norm_url)
            conf = info.get("confidence", 0.0)
            source = info.get("source", "?")
            platform_lines.append(
                f"  - {plat_name}: {url} "
                f"(Konfidenz: {conf:.0%}, Quelle: {source})"
            )
        platform_text = "\n".join(platform_lines)
    else:
        platform_text = "  (Keine Profile gefunden)"

    # === Verteilung als Text ===
    if distribution:
        dist_lines = [
            f"  - {name}: {count} Funde ({distribution_pct.get(name, 0)}%)"
            for name, count in sorted(
                distribution.items(), key=lambda kv: kv[1], reverse=True
            )
        ]
        dist_text = "\n".join(dist_lines)
    else:
        dist_text = "  (Keine Verteilungsdaten)"

    # === JSON-Schema für strikte Formatierung ===
    schema_json = json.dumps(_RISK_SCHEMA, indent=2, ensure_ascii=False)

    # === Vollständiger Prompt ===
    prompt = (
        f"Analysiere die folgende OSINT-Datenerhebung für den Benutzernamen "
        f"'{username}'.\n\n"
        f"GEFUNDENE PROFILE ({total_profiles} gesamt):\n"
        f"{platform_text}\n\n"
        f"PLATTFORM-VERTEILUNG:\n"
        f"{dist_text}\n\n"
        f"AUFGABE — Bewerte die folgenden drei Dimensionen:\n\n"
        f"1) RISIKO-SCORE (0-100):\n"
        f"   Wie hoch ist das kombinierte Risiko für diese Person durch\n"
        f"   Identitätsdiebstahl, Social Engineering und gezielte Angriffe?\n"
        f"   Berücksichtige: Anzahl der Plattformen, Art der Plattformen\n"
        f"   (LinkedIn > GitHub > Instagram > YouTube), Konfidenz der Funde.\n\n"
        f"2) ANGRIFFSFLÄCHEN (Liste von Strings):\n"
        f"   Welche KONKRETEN Angriffsflächen bestehen?\n"
        f"   Jeder Punkt MUSS enthalten:\n"
        f"   - Die betroffene Plattform\n"
        f"   - Die Art der exponierten Daten\n"
        f"   - Das daraus resultierende Risiko\n"
        f"   Beispiel: \"LinkedIn: Vollständige Berufshistorie öffentlich "
        f"einsehbar → Ermöglicht Spear-Phishing mit gefälschten Job-Angeboten\"\n\n"
        f"3) ZUSAMMENFASSUNG (1-3 Sätze):\n"
        f"   Prägnante Gesamtbewertung der digitalen Angriffsfläche.\n\n"
        f"ANTWORTFORMAT — AUSSCHLIESSLICH das folgende JSON-Objekt:\n"
        f"{schema_json}\n\n"
        f"WICHTIG:\n"
        f"- risk_score MUSS eine Ganzzahl zwischen 0 und 100 sein\n"
        f"- attack_surface MUSS eine Liste von Strings sein (auch bei 0 Funden: [])\n"
        f"- summary MUSS ein String sein\n"
        f"- KEINE Markdown-Formatierung, KEINE Code-Blöcke (```), KEIN Text "
        f"außerhalb des JSON\n"
        f"- Antworte NUR mit dem JSON-Objekt von {{ bis }}"
    )

    return prompt


def build_profile_summary_prompt(data: dict[str, Any]) -> str:
    """
    Baut einen kürzeren Prompt für eine reine Profilzusammenfassung.

    Weniger umfangreich als build_risk_prompt — konzentriert sich auf
    die Beschreibung des digitalen Fußabdrucks ohne Risiko-Scoring.
    Geeignet für schnelle Übersichten (z.B. Karteikartenkopf).

    Args:
        data: Vereinfachtes Daten-Dict. Erwartet:
              username, platform_count, platform_list (Liste von Namen).

    Returns:
        Prompt-String für Profilzusammenfassung.

    Example:
        >>> data = {"username": "max", "platform_count": 4,
        ...         "platform_list": ["GitHub", "Reddit", "Twitter", "Twitch"]}
        >>> prompt = build_profile_summary_prompt(data)
    """
    username = data.get("username", "UNBEKANNT")
    platform_count = data.get("platform_count", 0)
    platform_list: list[str] = data.get("platform_list", [])

    if platform_list:
        platforms_str = ", ".join(platform_list)
        platform_detail = (
            f"Die Person ist auf {platform_count} Plattformen aktiv: "
            f"{platforms_str}."
        )
    else:
        platform_detail = "Es wurden KEINE Social-Media-Profile gefunden."

    schema_json = json.dumps(_PROFILE_SCHEMA, indent=2, ensure_ascii=False)

    prompt = (
        f"Erstelle eine kurze Profilzusammenfassung für den Benutzernamen "
        f"'{username}'.\n\n"
        f"DATENLAGE:\n"
        f"{platform_detail}\n\n"
        f"AUFGABE:\n"
        f"1) digital_footprint: Beschreibe in 2-3 Sätzen den digitalen "
        f"Fußabdruck der Person. Welche Arten von Plattformen dominieren?\n"
        f"2) key_findings: Liste 2-5 zentrale Erkenntnisse als Strings.\n"
        f"3) privacy_score: Schätze den Privatsphäre-Level (0=sehr privat, "
        f"100=völlig öffentlich).\n"
        f"4) recommendations: 1-3 konkrete Verbesserungsvorschläge.\n\n"
        f"ANTWORTFORMAT:\n"
        f"{schema_json}\n\n"
        f"WICHTIG: Nur JSON, kein Markdown, keine Code-Blöcke."
    )

    return prompt


def build_handlungsempfehlungen_prompt(
    risk_score: int, attack_surface: list[str]
) -> str:
    """
    Baut einen Prompt für konkrete Handlungsempfehlungen basierend auf
    dem Risiko-Score und den identifizierten Angriffsflächen.

    Dieser Prompt wird NACH der Risikoanalyse aufgerufen und nutzt
    deren Ergebnisse als Input.

    Args:
        risk_score: Der vom LLM ermittelte Risiko-Score (0-100).
        attack_surface: Liste der identifizierten Angriffsflächen.

    Returns:
        Prompt-String für Handlungsempfehlungen.
    """
    if attack_surface:
        surfaces_text = "\n".join(f"  - {s}" for s in attack_surface)
    else:
        surfaces_text = "  (Keine spezifischen Angriffsflächen identifiziert)"

    schema = {
        "urgency": "",
        "actions": [],
        "priority_order": [],
    }
    schema_json = json.dumps(schema, indent=2, ensure_ascii=False)

    prompt = (
        f"Basierend auf einem OSINT-Risiko-Score von {risk_score}/100 und "
        f"folgenden Angriffsflächen, gib konkrete Handlungsempfehlungen:\n\n"
        f"ANGRIFFSFLÄCHEN:\n"
        f"{surfaces_text}\n\n"
        f"AUFGABE:\n"
        f"1) urgency: 'hoch', 'mittel' oder 'niedrig' — wie dringend "
        f"sollte gehandelt werden?\n"
        f"2) actions: Konkrete, umsetzbare Maßnahmen (3-5 Stück). "
        f"Jede Maßnahme als String mit Plattform-Bezug.\n"
        f"3) priority_order: Die actions-Strings in absteigender Priorität "
        f"(wichtigste zuerst).\n\n"
        f"ANTWORTFORMAT:\n"
        f"{schema_json}\n\n"
        f"WICHTIG: Nur JSON, kein Markdown, keine Code-Blöcke."
    )

    return prompt
