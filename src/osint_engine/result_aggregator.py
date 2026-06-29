"""
Result Aggregator — Merge, Deduplizierung & Statistiken.

Führt Ergebnisse aus Sherlock-Scanner (direkte HTTP-Prüfung) und
Google-Dorking (geparste Suchergebnisse) zusammen. Dedupliziert nach
normalisierten URLs, gewichtet Quellen nach Verlässlichkeit und
produziert eine saubere Datenbasis für die KI-Analyse.

Merge-Strategie:
- Sherlock-Treffer (HTTP 200 direkt) haben Gewicht 0.6 — höhere
  Konfidenz, da die Profil-URL direkt geprüft wurde.
- Google-Dork-Treffer (geparst aus SERP) haben Gewicht 0.4 —
  indirekter Nachweis, kann false positives enthalten.
- Bei gleicher URL wird die gewichtete Konfidenz fusioniert.

Beispiel-Rückgabe von aggregate():
{
    "username": "max_mustermann",
    "total_profiles": 7,
    "platforms": {
        "GitHub": {
            "url": "https://github.com/max_mustermann",
            "confidence": 0.95,
            "source": "sherlock+dork",
            "logo": "github.png",
            "color": "#181717"
        },
        ...
    },
    "distribution": {"GitHub": 1, "Reddit": 2, ...},
    "distribution_percent": {"GitHub": 14.3, "Reddit": 28.6, ...},
    "raw_sherlock": [...],
    "raw_dork": [...]
}

Autor: Rayquaza
Datum: 2026-06-29
"""

from collections import Counter
from typing import Any


class ResultAggregator:
    """
    Führt OSINT-Ergebnisse aus verschiedenen Quellen zusammen.

    Dedupliziert nach normalisierten URLs, gewichtet Quellen-Konfidenzen
    und erstellt Statistiken für die Report-Generierung.

    Source-Gewichtung (begründet):
        sherlock → 0.6  (direkte HTTP-Prüfung, hohe Verlässlichkeit)
        dork     → 0.4  (indirekt via SERP-Parsing, geringere Verlässlichkeit)
    """

    # Gewichtung der Quellen für merge_confidence
    _SOURCE_WEIGHTS: dict[str, float] = {
        "sherlock": 0.6,
        "google_dork": 0.4,
        "duckduckgo": 0.35,
    }

    # ------------------------------------------------------------------
    # Öffentliche API
    # ------------------------------------------------------------------

    def aggregate(
        self,
        username: str,
        sherlock_results: list[dict],
        dork_results: list[dict],
    ) -> dict[str, Any]:
        """
        Führt Sherlock- und Dork-Ergebnisse zu einem Datensatz zusammen.

        Dedupliziert nach normalisierter URL, merged Konfidenzen
        gewichtet und erstellt die Plattform-Verteilung.

        Args:
            username: Der recherchierte Benutzername.
            sherlock_results: Liste von Dicts aus SherlockScanner.scan().
            dork_results: Liste von Dicts aus GoogleDorker.dork().

        Returns:
            Strukturiertes Dict (siehe Modul-Docstring für Beispiel).
        """
        # Dictionary: normalisierte URL → gemergter Eintrag
        merged: dict[str, dict] = {}

        # --- Phase 1: Sherlock-Ergebnisse einpflegen (Primärquelle) ---
        for result in sherlock_results:
            if not result.get("exists"):
                continue  # Nur positive Funde aggregieren

            url = result.get("url", "")
            norm_url = self._normalize_url(url)

            merged[norm_url] = {
                "url": url,
                "platform": result.get("platform", "unknown"),
                "confidence": result.get("confidence", 0.0),
                "source": "sherlock",
                "sherlock_confidence": result.get("confidence", 0.0),
                "dork_confidence": None,
                "status_code": result.get("status_code"),
                "response_time_ms": result.get("response_time_ms"),
                "logo": self._lookup_field(result, "logo"),
                "color": self._lookup_field(result, "color"),
                "weight": self._lookup_field(result, "weight", 1.0),
            }

        # --- Phase 2: Dork-Ergebnisse einpflegen oder mergen ---
        for result in dork_results:
            url = result.get("url", "")
            norm_url = self._normalize_url(url)
            dork_conf = result.get("confidence", 0.0)
            dork_source = result.get("source", "google_dork")

            if norm_url in merged:
                # URL existiert bereits von Sherlock → Konfidenzen mergen
                existing = merged[norm_url]
                existing["confidence"] = self.merge_confidence(
                    c1=existing.get("sherlock_confidence", 0.0),
                    c2=dork_conf,
                    source1="sherlock",
                    source2=dork_source,
                )
                existing["dork_confidence"] = dork_conf
                existing["source"] = f"sherlock+{dork_source}"
                # Snippet ergänzen, falls vorhanden
                if result.get("snippet"):
                    existing["snippet"] = result["snippet"]
            else:
                # Neue URL nur aus Dork → niedrigere Konfidenz, aber trotzdem aufnehmen
                merged[norm_url] = {
                    "url": url,
                    "platform": result.get("platform", "unknown"),
                    "confidence": dork_conf,
                    "source": dork_source,
                    "sherlock_confidence": None,
                    "dork_confidence": dork_conf,
                    "status_code": None,
                    "response_time_ms": None,
                    "logo": self._lookup_field(result, "logo"),
                    "color": self._lookup_field(result, "color"),
                    "weight": self._lookup_field(result, "weight", 0.5),
                    "snippet": result.get("snippet", ""),
                }

        # --- Phase 3: Plattform-Verteilung berechnen ---
        platform_counter: Counter[str] = Counter()
        for entry in merged.values():
            platform_counter[entry["platform"]] += 1

        distribution = dict(platform_counter)

        # --- Phase 4: Ergebnis-Dict bauen ---
        return {
            "username": username,
            "total_profiles": len(merged),
            "platforms": dict(merged),  # Key = normalisierte URL
            "distribution": distribution,
            "distribution_percent": self._calc_percentages(distribution),
            "raw_sherlock": sherlock_results,
            "raw_dork": dork_results,
        }

    def merge_confidence(
        self,
        c1: float,
        c2: float,
        source1: str,
        source2: str,
    ) -> float:
        """
        Fusioniert zwei Konfidenzwerte gewichtet nach Quelle.

        Gewichtung:
            sherlock      → 0.6
            google_dork   → 0.4
            duckduckgo    → 0.35
            unknown       → 0.3 (Fallback)

        Formel:
            merged = (c1 * w1 + c2 * w2) / (w1 + w2)

        Edge Cases:
            - Eine Konfidenz ≤ 0 → die andere wird unverändert übernommen.
            - Beide ≤ 0 → 0.0.

        Args:
            c1: Konfidenzwert aus Quelle 1.
            c2: Konfidenzwert aus Quelle 2.
            source1: Name der ersten Quelle (z.B. "sherlock").
            source2: Name der zweiten Quelle (z.B. "google_dork").

        Returns:
            Gewichtete, fusionierte Konfidenz (0.0 – 1.0).
        """
        # Edge Cases: eine Quelle hat keine Daten
        if c1 <= 0 and c2 <= 0:
            return 0.0
        if c1 <= 0:
            return round(c2, 4)
        if c2 <= 0:
            return round(c1, 4)

        w1 = self._SOURCE_WEIGHTS.get(source1, 0.3)
        w2 = self._SOURCE_WEIGHTS.get(source2, 0.3)

        merged = (c1 * w1 + c2 * w2) / (w1 + w2)
        return round(min(merged, 1.0), 4)

    def get_statistics(self, data: dict) -> dict:
        """
        Berechnet erweiterte Statistiken für Visualisierungen.

        Args:
            data: Das aggregierte Daten-Dict aus aggregate().

        Returns:
            Dict mit:
            {
                "total": int,              # Gesamtzahl Funde
                "unique_platforms": int,   # Anzahl verschiedener Plattformen
                "top5": [(name, count), ...],  # Top 5 nach Häufigkeit
                "percentages": {name: float},  # Prozentuale Verteilung
                "avg_confidence": float,   # Durchschnittliche Konfidenz
                "sources": {name: count},  # Funde pro Quelle
            }
        """
        distribution: dict[str, int] = data.get("distribution", {})
        platforms: dict[str, dict] = data.get("platforms", {})

        total = sum(distribution.values())

        # Top 5 Plattformen
        sorted_platforms = sorted(
            distribution.items(), key=lambda kv: kv[1], reverse=True
        )
        top5 = sorted_platforms[:5]

        # Prozentuale Verteilung
        percentages = self._calc_percentages(distribution)

        # Durchschnittliche Konfidenz über alle Funde
        confidences = [
            entry.get("confidence", 0.0)
            for entry in platforms.values()
        ]
        avg_confidence = (
            round(sum(confidences) / len(confidences), 4)
            if confidences
            else 0.0
        )

        # Quellen-Verteilung
        source_counter: Counter[str] = Counter()
        for entry in platforms.values():
            source_counter[entry.get("source", "unknown")] += 1

        return {
            "total": total,
            "unique_platforms": len(distribution),
            "top5": top5,
            "percentages": percentages,
            "avg_confidence": avg_confidence,
            "sources": dict(source_counter),
        }

    # ------------------------------------------------------------------
    # Interne Hilfsmethoden
    # ------------------------------------------------------------------

    def _normalize_url(self, url: str) -> str:
        """
        Normalisiert eine URL für den deduplizierten Vergleich.

        Transformationen:
            1. https://  → entfernen
            2. http://   → entfernen
            3. www.      → entfernen
            4. Trailing / → entfernen
            5. Lowercase

        Dadurch werden identisch:
            https://www.github.com/user/
            http://github.com/user
            HTTPS://GITHUB.COM/user/

        Args:
            url: Rohe URL aus Scan-Ergebnissen.

        Returns:
            Normalisierte URL (nur domain + pfad, lowercase).
        """
        url = url.strip().lower()

        # Protokoll entfernen
        for prefix in ("https://", "http://"):
            if url.startswith(prefix):
                url = url[len(prefix):]
                break

        # www.-Präfix entfernen
        if url.startswith("www."):
            url = url[4:]

        # Trailing Slash entfernen (aber nicht bei Root "/")
        url = url.rstrip("/")

        return url

    def _calc_percentages(self, distribution: dict[str, int]) -> dict[str, float]:
        """
        Konvertiert absolute Häufigkeiten in Prozente.

        Args:
            distribution: {platform_name: count}

        Returns:
            {platform_name: percent} mit einer Nachkommastelle.
        """
        total = sum(distribution.values())
        if total == 0:
            return {}

        return {
            name: round((count / total) * 100, 1)
            for name, count in distribution.items()
        }

    @staticmethod
    def _lookup_field(result: dict, field: str, default: Any = None) -> Any:
        """
        Sucht ein Feld im Ergebnis-Dict, mit Fallback-Default.

        Args:
            result: Ergebnis-Dict.
            field: Feldname.
            default: Default-Wert wenn Feld nicht existiert.

        Returns:
            Feldwert oder default.
        """
        return result.get(field, default)
