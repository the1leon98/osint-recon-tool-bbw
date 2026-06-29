"""
Risk Calculator — Hybrider Risiko-Score aus KI & quantitativen Metriken.

Kombiniert die qualitative KI-Analyse (GPT-4o-mini) mit quantitativen
Metriken (Anzahl Funde, Plattform-Gewichtung) zu einem finalen,
deterministischen Risiko-Score (0-100).

Formel (transparent dokumentiert):
    final_score = ai_score × 0.7 + quant_score × 0.3

    ai_score   = Vom LLM ermittelter Score (0-100)
                 Gewicht 70 % → Qualitative Tiefe der Analyse.
    quant_score = min(total_profiles / 20 × 100, 100)
                 Gewicht 30 % → Objektive Fundmenge.
                 Annahme: 20+ offene Profile = maximales quantitatives Risiko.

Risikostufen & Farben (WCAG-konform):
    niedrig   (0-24)  → #22c55e (Grün)
    mittel    (25-49) → #eab308 (Gelb)
    hoch      (50-74) → #f97316 (Orange)
    kritisch  (75-100)→ #ef4444 (Rot)

Beispiel-Berechnung:
    AI-Analyse: risk_score = 68
    Quantitative: 7 Profile auf 4 Plattformen
    quant_score = min(7/20 × 100, 100) = 35.0
    final_score = round(68 × 0.7 + 35.0 × 0.3) = round(47.6 + 10.5) = 58
    → Risikostufe: "hoch" (50-74)

Autor: Rayquaza
Datum: 2026-06-29
"""

from typing import Any

# =========================================================================
# Risikostufen-Schwellwerte
# =========================================================================

RISK_THRESHOLDS: dict[str, int] = {
    "niedrig": 25,    #  0–24
    "mittel": 50,     # 25–49
    "hoch": 75,       # 50–74
    "kritisch": 100,  # 75–100
}

# =========================================================================
# Farben pro Risikostufe (WCAG AA auf weißem Hintergrund)
# =========================================================================

RISK_COLORS: dict[str, str] = {
    "niedrig": "#22c55e",   # Grün — Green-500
    "mittel": "#eab308",    # Gelb — Yellow-500
    "hoch": "#f97316",      # Orange — Orange-500
    "kritisch": "#ef4444",  # Rot — Red-500
}

# =========================================================================
# CSS-Klassen für HTML-Report (Tailwind-kompatibel)
# =========================================================================

_RISK_CSS_CLASSES: dict[str, str] = {
    "niedrig": "risk-low",
    "mittel": "risk-mid",
    "hoch": "risk-high",
    "kritisch": "risk-critical",
}

# =========================================================================
# Konfiguration: Gewichtung & quantitative Skalierung
# =========================================================================

# Gewichtung der beiden Score-Komponenten (Summe muss 1.0 sein)
_AI_WEIGHT: float = 0.7       # Qualitative KI-Analyse
_QUANT_WEIGHT: float = 0.3    # Quantitative Metriken (Anzahl Funde)

# Maximale Profil-Anzahl, ab der quant_score = 100 ist.
# Annahme: Wer 20+ öffentliche Profile hat, ist im Internet maximal exponiert.
_MAX_PROFILES_FOR_QUANT: int = 20

# Schwellwert für Plattform-Anzahl (zusätzliche Warnmeldung)
_PLATFORM_WARNING_THRESHOLD: int = 5


# =========================================================================
# Hauptfunktion
# =========================================================================

def calculate_risk(
    ai_response: dict[str, Any],
    aggregated_data: dict[str, Any],
) -> dict[str, Any]:
    """
    Berechnet den finalen, hybriden Risiko-Score.

    Kombiniert die qualitative KI-Analyse (70 %) mit quantitativen
    Metriken (30 %) zu einem einzigen Score (0–100) und ordnet ihn
    einer Risikostufe mit Farbe und CSS-Klasse zu.

    Args:
        ai_response: Validierte Antwort aus AIClient.analyse().
                     Erwartet: {"risk_score": int, "attack_surface": [...],
                                "summary": str}
        aggregated_data: Aggregierte Daten aus ResultAggregator.aggregate().
                         Erwartet: {"total_profiles": int, "platforms": dict,
                                    "distribution": dict, ...}

    Returns:
        Dict mit vollständiger Risikobewertung:
        {
            "final_score": int,           # 0-100, kombinierter Score
            "ai_score": int,              # Original KI-Score
            "quant_score": float,         # Quantitative Metrik
            "risk_level": str,            # "niedrig"|"mittel"|"hoch"|"kritisch"
            "color": str,                 # Hex-Farbe für UI
            "risk_level_class": str,      # CSS-Klasse für HTML
            "attack_surface": list[str],  # Angereicherte Angriffsflächen
            "summary": str,               # KI-Zusammenfassung
        }
    """
    # === Komponente 1: KI-Analyse-Score (70 % Gewicht) ===
    ai_score = ai_response.get("risk_score", 50)
    # Sicherstellen, dass ai_score im gültigen Bereich liegt
    ai_score = max(0, min(100, ai_score))

    # === Komponente 2: Quantitative Metrik (30 % Gewicht) ===
    total_profiles = aggregated_data.get("total_profiles", 0)
    # Formel: Jedes gefundene Profil zählt 5 % (20 Profile = 100 %).
    # Das ist eine logarithmisch-lineare Approximation: Die ersten 5 Profile
    # erhöhen den Score stark, ab 20 Profilen ist das Plateau erreicht.
    quant_score = min((total_profiles / _MAX_PROFILES_FOR_QUANT) * 100, 100.0)

    # === Finaler Score: Gewichtete Kombination ===
    # final_score = round(ai_score × 0.7 + quant_score × 0.3)
    final_score = round(ai_score * _AI_WEIGHT + quant_score * _QUANT_WEIGHT)
    final_score = max(0, min(100, final_score))  # Clamp auf 0–100

    # === Risikostufe bestimmen ===
    risk_level = _determine_risk_level(final_score)

    # === Angriffsflächen anreichern ===
    attack_surface = _build_enriched_attack_surface(
        ai_response=ai_response,
        aggregated_data=aggregated_data,
        total_profiles=total_profiles,
    )

    # === Ergebnis zusammenbauen ===
    result: dict[str, Any] = {
        "final_score": final_score,
        "ai_score": ai_score,
        "quant_score": round(quant_score, 1),
        "risk_level": risk_level,
        "color": RISK_COLORS[risk_level],
        "risk_level_class": _RISK_CSS_CLASSES[risk_level],
        "attack_surface": attack_surface,
        "summary": ai_response.get("summary", ""),
    }

    return result


# =========================================================================
# Interne Hilfsfunktionen
# =========================================================================

def _determine_risk_level(score: int) -> str:
    """
    Mappt einen numerischen Score auf eine Risikostufe.

    Schwellwerte (definiert in RISK_THRESHOLDS):
        0–24  → "niedrig"
       25–49  → "mittel"
       50–74  → "hoch"
       75–100 → "kritisch"

    Args:
        score: Numerischer Score (0–100).

    Returns:
        Risikostufe als String.
    """
    if score < RISK_THRESHOLDS["niedrig"]:
        return "niedrig"
    if score < RISK_THRESHOLDS["mittel"]:
        return "mittel"
    if score < RISK_THRESHOLDS["hoch"]:
        return "hoch"
    return "kritisch"


def _build_enriched_attack_surface(
    ai_response: dict[str, Any],
    aggregated_data: dict[str, Any],
    total_profiles: int,
) -> list[str]:
    """
    Reichert die KI-Angriffsflächen mit automatisch generierten
    quantitativen Funden an.

    Fügt hinzu:
        - Anzahl öffentlicher Profile + Plattform-Anzahl
        - Warnung bei >5 Plattformen (Verknüpfbarkeit der Identität)
        - Plattform-Verteilung als Kontext

    Args:
        ai_response: KI-Antwort mit attack_surface-Liste.
        aggregated_data: Aggregierte OSINT-Daten.
        total_profiles: Anzahl gefundener Profile.

    Returns:
        Angereicherte Liste von Angriffsflächen-Strings.
    """
    # KI-generierte Angriffsflächen kopieren (nicht referenzieren)
    surfaces: list[str] = list(ai_response.get("attack_surface", []))

    platforms: dict = aggregated_data.get("platforms", {})
    num_platforms = len(platforms)

    # === Automatischer Eintrag 1: Quantitative Übersicht ===
    surfaces.insert(
        0,
        f"{total_profiles} öffentliche Profile auf "
        f"{num_platforms} Plattformen gefunden",
    )

    # === Automatischer Eintrag 2: Identitäts-Verknüpfbarkeit ===
    if num_platforms > _PLATFORM_WARNING_THRESHOLD:
        surfaces.insert(
            1,
            f"Identität auf {num_platforms} verschiedenen Plattformen "
            f"verknüpfbar — ermöglicht umfassende Profilbildung",
        )

    # === Automatischer Eintrag 3: Plattformen mit hohem Gewicht ===
    high_weight_platforms = [
        (norm_url, info)
        for norm_url, info in platforms.items()
        if info.get("weight", 0) >= 1.5
    ]
    if high_weight_platforms:
        names = [info["platform"] for _, info in high_weight_platforms[:3]]
        surfaces.append(
            f"Präsenz auf hoch-sensiblen Plattformen: "
            f"{', '.join(names)} — besonders schützenswert"
        )

    return surfaces
