"""
HTML Report Renderer — Dynamische Report-Generierung mit Jinja2.

Erzeugt aus aggregierten OSINT-Daten und KI-Analyseergebnissen einen
vollständigen, selbst-tragenden HTML-Report. Der Report ist vollständig
offline-fähig: Alle Bilder sind Base64-eingebettet, CSS-Variablen werden
dynamisch aus den Risikofarben generiert, und Chart-Daten sind als
JavaScript-Variablen inline verfügbar.

Edge-Cases mit eleganten Fallbacks:
- Kein Avatar-Bild → SVG-Platzhalter (data:image/svg+xml)
- KI-Analyse fehlgeschlagen → risk_score=50, neutraler Hinweis
- Keine Plattform-Daten → leeres Chart mit "Keine Daten"-Label
- Output-Verzeichnis fehlt → wird automatisch angelegt

Autor: Rayquaza
Datum: 2026-06-29
"""

import base64
import datetime
import logging
from pathlib import Path
from typing import Any, Optional

from jinja2 import Environment, FileSystemLoader
from rich.console import Console

from config.settings import get_settings

logger = logging.getLogger(__name__)
console = Console()

# ---------------------------------------------------------------------------
# SVG-Platzhalter-Avatar (wird verwendet, wenn hacker_avatar.png fehlt)
# Einfaches Hacker-Symbol: Kapuzen-Silhouette auf dunklem Hintergrund
# ---------------------------------------------------------------------------
_SVG_PLACEHOLDER = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" '
    'width="128" height="128">'
    '<rect width="128" height="128" rx="16" fill="#1a1a2e"/>'
    '<circle cx="64" cy="48" r="20" fill="#0f3460" stroke="#e94560" stroke-width="2"/>'
    '<path d="M32 100c0-20 14-36 32-36s32 16 32 36" fill="#0f3460" '
    'stroke="#e94560" stroke-width="2"/>'
    '<text x="64" y="118" text-anchor="middle" fill="#e94560" '
    'font-family="monospace" font-size="10">OSINT</text>'
    "</svg>"
)


class HTMLRenderer:
    """
    Rendert OSINT-Analyse-Daten in einen HTML-Report via Jinja2.

    Nutzt Template-Inheritance (base.html → karteikarte.html) und
    dynamische Kontext-Variablen für CSS-Farben, Chart-Daten und
    Risikobewertung. Alle Assets sind Base64-eingebettet — der
    Report funktioniert vollständig offline.

    Attributes:
        template_dir: Pfad zum templates/-Verzeichnis.
        env: Jinja2-Environment mit FileSystemLoader.
        settings: Gecachte Settings-Instanz.
    """

    def __init__(self) -> None:
        """Initialisiert den Renderer mit Jinja2-Environment."""
        self.settings = get_settings()
        self.template_dir: Path = self.settings.template_dir
        self.static_dir: Path = self.settings.static_dir
        self.console: Console = Console()

        self.env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=True,  # XSS-Schutz: HTML-Escaping per Default
            trim_blocks=True,
            lstrip_blocks=True,
        )

        logger.debug(
            "HTMLRenderer: template_dir=%s, static_dir=%s",
            self.template_dir,
            self.static_dir,
        )

    # ------------------------------------------------------------------
    # Öffentliche API
    # ------------------------------------------------------------------

    def render(
        self,
        analysis_data: dict[str, Any],
        aggregated_data: dict[str, Any],
    ) -> str:
        """
        Rendert den HTML-Report als String (ohne Speicherung).

        Nützlich für Vorschau, Tests oder In-Memory-Verarbeitung.

        Args:
            analysis_data: Risikoanalyse-Dict aus risk_calculator.calculate_risk().
            aggregated_data: Aggregierte Daten aus result_aggregator.aggregate().

        Returns:
            Vollständiger HTML-String.
        """
        context = self._prepare_context(analysis_data, aggregated_data)
        template = self.env.get_template("karteikarte.html")
        return template.render(**context)

    def render_and_save(
        self,
        analysis_data: dict[str, Any],
        aggregated_data: dict[str, Any],
        output_path: Optional[str] = None,
    ) -> str:
        """
        Rendert den HTML-Report und speichert ihn auf der Festplatte.

        Erstellt das Zielverzeichnis automatisch, falls es nicht existiert.

        Args:
            analysis_data: Risikoanalyse-Dict.
            aggregated_data: Aggregierte OSINT-Daten.
            output_path: Pfad für die HTML-Datei. None → Auto-Name mit
                         Timestamp: output/report_YYYYMMDD_HHMMSS.html

        Returns:
            Absoluter Pfad zur gespeicherten HTML-Datei.
        """
        # --- Kontext bauen ---
        context = self._prepare_context(analysis_data, aggregated_data)

        # --- Template rendern ---
        template = self.env.get_template("karteikarte.html")
        html = template.render(**context)

        # --- Ausgabepfad bestimmen ---
        if output_path is None:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            username = aggregated_data.get("username", "unknown")
            output_path = (
                self.settings.output_dir
                / f"report_{username}_{timestamp}.html"
            )
        else:
            output_path = Path(output_path)

        # --- Verzeichnis anlegen ---
        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # --- Schreiben ---
        output_path.write_text(html, encoding="utf-8")

        self.console.print(
            f"[bold green]✓[/] Report gespeichert: "
            f"[cyan]{output_path}[/cyan] "
            f"({len(html):,} Bytes)"
        )

        logger.info("Report gespeichert: %s (%d Bytes)", output_path, len(html))

        return str(output_path)

    # ------------------------------------------------------------------
    # Kontext-Builder: Baut das Dict für Jinja2-Templates
    # ------------------------------------------------------------------

    def _prepare_context(
        self,
        analysis_data: dict[str, Any],
        aggregated_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Baut den vollständigen Template-Kontext.

        Extrahiert alle relevanten Daten aus Analyse und Aggregation
        und bereitet sie für die Jinja2-Templates auf:
          - Profil-Informationen (Name, Alter, Wohnort, Interessen)
          - Risiko-Bewertung (Score, Farbe, Stufe, Angriffsflächen)
          - Plattform-Daten für JavaScript-Charts
          - Base64-Avatar (mit Fallback)
          - Generierungszeitpunkt

        Args:
            analysis_data: Risikoanalyse-Dict.
            aggregated_data: Aggregierte OSINT-Daten.

        Returns:
            Vollständiger Context-Dict für Jinja2.
        """
        username = aggregated_data.get("username", "Unbekannt")
        distribution = aggregated_data.get("distribution", {})

        # === Profil-Daten ===
        profile = {
            "name": username,
            "alter": "Unbekannt",
            "wohnort": "Nicht ermittelt",
            "interessen": self._extract_interests(aggregated_data),
        }

        # === Risiko-Daten ===
        risk = {
            "score": analysis_data.get("final_score", 50),
            "ai_score": analysis_data.get("ai_score", 50),
            "quant_score": analysis_data.get("quant_score", 0.0),
            "color": analysis_data.get("color", "#eab308"),
            "level": analysis_data.get("risk_level", "mittel"),
            "level_class": analysis_data.get("risk_level_class", "risk-mid"),
            "attack_surface": analysis_data.get("attack_surface", []),
            "summary": analysis_data.get("summary", "Keine Zusammenfassung verfügbar."),
        }

        # === Plattform-Daten für Chart.js (Einzel-Plattformen) ===
        platforms_chart = self._build_chart_data(
            distribution=distribution,
            platforms_detail=aggregated_data.get("platforms", {}),
        )

        # === Kategorie-Daten für Chart.js (gruppiert) ===
        category_chart = self._build_category_chart_data(
            category_distribution=aggregated_data.get("category_distribution", {}),
        )

        # === Avatar: ZUERST echtes Profilbild aus Sherlock-Ergebnissen, DANN Fallback ===
        avatar_base64 = self._get_avatar_base64(aggregated_data)

        # === Generierungszeitpunkt ===
        now = datetime.datetime.now()
        generated_at = now.strftime("%d.%m.%Y %H:%M:%S")

        # === Gesamt-Kontext ===
        context: dict[str, Any] = {
            "profile": profile,
            "risk": risk,
            "platforms": platforms_chart,
            "categories": category_chart,
            "avatar_base64": avatar_base64,
            "generated_at": generated_at,
            "generated_year": str(now.year),
            "total_profiles": aggregated_data.get("total_profiles", 0),
            "total_platforms": len(distribution),
            "username": username,
            # Roh-Daten für erweiterte Templates
            "_raw_analysis": analysis_data,
            "_raw_aggregated": aggregated_data,
        }

        return context

    # ------------------------------------------------------------------
    # Avatar: Base64-Kodierung mit SVG-Fallback
    # ------------------------------------------------------------------

    def _get_avatar_base64(self, aggregated_data: dict[str, Any] | None = None) -> str:
        """
        Lädt das Avatar-Bild. Priorität:
          1. Echtes Profilbild aus Sherlock-Ergebnissen (aggregated_data)
          2. hacker_avatar.png aus static/img/
          3. SVG-Platzhalter
        """
        # Priorität 1: Echtes Profilbild aus Sherlock-Scan
        if aggregated_data:
            platforms = aggregated_data.get("platforms", {})
            for _url, info in platforms.items():
                avatar = info.get("avatar_base64")
                if avatar and len(avatar) > 50:
                    logger.debug("Echtes Profilbild verwendet: %s", _url[:50])
                    return avatar

        # Priorität 2: Lokales hacker_avatar.png
        avatar_path = self.static_dir / "img" / "hacker_avatar.png"
        try:
            if avatar_path.exists() and avatar_path.stat().st_size > 0:
                raw_bytes = avatar_path.read_bytes()
                b64_string = base64.b64encode(raw_bytes).decode("ascii")
                return f"data:image/png;base64,{b64_string}"
        except (OSError, IOError) as exc:
            logger.warning("Avatar-Fehler: %s", exc)

        # SVG-Fallback: Hacker-Silhouette als Data-URI
        svg_bytes = _SVG_PLACEHOLDER.encode("utf-8")
        b64_svg = base64.b64encode(svg_bytes).decode("ascii")
        return f"data:image/svg+xml;base64,{b64_svg}"

    # ------------------------------------------------------------------
    # Chart-Daten für JavaScript (Chart.js / ApexCharts)
    # ------------------------------------------------------------------

    def _build_chart_data(
        self,
        distribution: dict[str, int],
        platforms_detail: dict[str, dict],
    ) -> dict[str, Any]:
        """
        Baut die Datenstruktur für das Plattform-Verteilungsdiagramm.

        Erzeugt drei parallele Arrays (labels, data, colors), die
        direkt in JavaScript-Chart-Bibliotheken verwendet werden können.

        Reihenfolge: Absteigend nach Häufigkeit sortiert.

        Args:
            distribution: {platform_name: count}
            platforms_detail: {normalized_url: {platform, color, ...}}

        Returns:
            {
                "labels": ["GitHub", "Reddit", ...],
                "data": [3, 2, ...],
                "colors": ["#181717", "#FF4500", ...],
                "total": 7,
                "has_data": True
            }

        Edge Case (keine Daten):
            {"labels": ["Keine Daten"], "data": [0],
             "colors": ["#6b7280"], "total": 0, "has_data": False}
        """
        if not distribution:
            return {
                "labels": ["Keine Daten"],
                "data": [0],
                "colors": ["#6b7280"],
                "total": 0,
                "has_data": False,
            }

        # Nach Häufigkeit sortieren
        sorted_items = sorted(
            distribution.items(), key=lambda kv: kv[1], reverse=True
        )

        labels: list[str] = []
        data: list[int] = []
        colors: list[str] = []

        # Farb-Mapping aus platforms_detail extrahieren
        color_map: dict[str, str] = {}
        for _, info in platforms_detail.items():
            name = info.get("platform", "")
            color = info.get("color", "#6b7280")
            if name:
                color_map[name] = color

        for name, count in sorted_items:
            labels.append(name)
            data.append(count)
            colors.append(color_map.get(name, "#6b7280"))

        return {
            "labels": labels,
            "data": data,
            "colors": colors,
            "total": sum(data),
            "has_data": True,
        }

    def _build_category_chart_data(
        self,
        category_distribution: dict[str, int],
    ) -> dict[str, Any]:
        """
        Baut Chart-Daten für die Kategorie-Verteilung (gruppiert).

        Farben pro Kategorie werden aus platforms.json geladen.
        Reihenfolge: Absteigend nach Häufigkeit sortiert.

        Args:
            category_distribution: {category_name: count}

        Returns:
            {
                "labels": ["Social Media", "Business / Tech", ...],
                "data": [5, 2, ...],
                "colors": ["#E4405F", "#0A66C2", ...],
                "total": 7,
                "has_data": True
            }
        """
        import json as _json
        from pathlib import Path as _Path

        if not category_distribution:
            return {
                "labels": ["Keine Daten"],
                "data": [0],
                "colors": ["#6b7280"],
                "total": 0,
                "has_data": False,
            }

        # Kategorie-Farben aus platforms.json laden
        cat_colors: dict[str, str] = {}
        try:
            config_path = _Path(__file__).resolve().parent.parent.parent / "config" / "platforms.json"
            with open(config_path, "r", encoding="utf-8") as fh:
                data = _json.load(fh)
            for cat_name, cat_info in data.get("categories", {}).items():
                cat_colors[cat_name] = cat_info.get("color", "#6b7280")
        except (FileNotFoundError, _json.JSONDecodeError):
            pass

        # Nach Häufigkeit sortieren
        sorted_items = sorted(
            category_distribution.items(), key=lambda kv: kv[1], reverse=True
        )

        labels: list[str] = []
        chart_data: list[int] = []
        colors: list[str] = []

        for name, count in sorted_items:
            labels.append(name)
            chart_data.append(count)
            colors.append(cat_colors.get(name, "#6b7280"))

        return {
            "labels": labels,
            "data": chart_data,
            "colors": colors,
            "total": sum(chart_data),
            "has_data": True,
        }

    # ------------------------------------------------------------------
    # Hilfsmethoden
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_interests(aggregated_data: dict[str, Any]) -> list[str]:
        """
        Extrahiert Interessen-Hinweise aus den Plattform-Daten.

        Leitet aus den Plattform-Typen plausible Interessen ab
        (z.B. GitHub → "Softwareentwicklung", Twitch → "Gaming").

        Args:
            aggregated_data: Aggregierte OSINT-Daten.

        Returns:
            Liste von Interessen-Strings (maximal 5).
        """
        platforms: dict[str, dict] = aggregated_data.get("platforms", {})
        platform_names = {
            info.get("platform", "").lower()
            for info in platforms.values()
        }

        interest_map: dict[str, str] = {
            "github": "Softwareentwicklung",
            "instagram": "Fotografie",
            "youtube": "Video-Content",
            "snapchat": "Social Media",
            "pinterest": "Visuelle Inspiration",
            "twitter / x": "Microblogging",
            "reddit": "Community-Diskussion",
            "tiktok": "Kurzvideo-Content",
            "linkedin": "Berufliches Networking",
            "twitch": "Gaming & Streaming",
        }

        interests: list[str] = []
        for name in platform_names:
            mapped = interest_map.get(name)
            if mapped and mapped not in interests:
                interests.append(mapped)

        return interests[:5]  # Maximal 5 Interessen
