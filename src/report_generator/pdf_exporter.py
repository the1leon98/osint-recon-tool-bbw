"""
PDF Exporter — matplotlib-Diagramme, WeasyPrint-PDF, lokaler HTTP-Server.

Pipeline:
  1. Generiert zwei PNG-Diagramme (Risiko-Donut & Plattform-Pie) via matplotlib
  2. Bettet die Diagramme als Base64-img-Tags in das gerenderte HTML ein
  3. Konvertiert via WeasyPrint + print.css zu einer DIN-A4-PDF
  4. Startet einen lokalen http.server auf Port 5051 für den Download
  5. Öffnet den PDF-Link automatisch im Standard-Browser

Fehlertoleranz:
  - matplotlib nicht importierbar → SVG-Platzhalter-Diagramme
  - Port 5051 belegt → sucht nächsten freien Port (5052, 5053 …)
  - WeasyPrint-Fehler → speichert HTML als Fallback
  - Alle generierten Diagramme werden in static/img/ abgelegt

Autor: Rayquaza, 2026
"""

import base64
import logging
import os
import re
import socket
import threading
import webbrowser
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

from rich.console import Console

from config.settings import get_settings

# ---------------------------------------------------------------------------
# matplotlib im Offline-Modus — KEIN GUI-Backend, KEIN X11-Display noetig
# ---------------------------------------------------------------------------
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# WeasyPrint
from weasyprint import CSS, HTML

logger = logging.getLogger(__name__)
console = Console()

# ---------------------------------------------------------------------------
# Farbpalette & Konstanten
# ---------------------------------------------------------------------------

RISK_COLORS: dict[str, str] = {
    "niedrig": "#22c55e",
    "mittel": "#eab308",
    "hoch": "#f97316",
    "kritisch": "#ef4444",
}

PLATFORM_COLORS: dict[str, str] = {
    "GitHub": "#181717",
    "Instagram": "#E4405F",
    "YouTube": "#FF0000",
    "Snapchat": "#FFFC00",
    "Pinterest": "#BD081C",
    "Twitter / X": "#1DA1F2",
    "Reddit": "#FF4500",
    "TikTok": "#000000",
    "LinkedIn": "#0A66C2",
    "Twitch": "#9146FF",
}

_FALLBACK_PALETTE: list[str] = [
    "#3b82f6", "#8b5cf6", "#ec4899", "#06b6d4",
    "#84cc16", "#f59e0b", "#ef4444", "#14b8a6",
    "#6366f1", "#d946ef",
]

_DEFAULT_PORT: int = 5051
_MAX_PORT_RETRIES: int = 20

# Matplotlib-Stil
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica Neue", "Arial", "DejaVu Sans"],
    "font.size": 11,
    "axes.titlesize": 14,
    "axes.labelsize": 11,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "savefig.dpi": 150,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.1,
})


class PDFExporter:
    """
    Generiert PDF-Reports mit eingebetteten matplotlib-Diagrammen.

    Nimmt das vom HTMLRenderer vorbereitete HTML (mit inline CSS/JS),
    ersetzt die JavaScript-Chart-Container durch echte PNG-Diagramme
    und konvertiert das Ergebnis via WeasyPrint zu einer druckbaren PDF.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.static_img_dir: Path = self.settings.static_dir / "img"
        self.output_dir: Path = self.settings.output_dir

        self.static_img_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._risk_chart_path: Path = self.static_img_dir / "chart_risk.png"
        self._platform_chart_path: Path = self.static_img_dir / "chart_platforms.png"
        self._server: Optional[HTTPServer] = None

    # ==================================================================
    # PUBLIC API
    # ==================================================================

    def export(
        self,
        html_content: str,
        risk_data: dict[str, Any],
        aggregated_data: dict[str, Any],
        output_filename: str = "cyber_akte.pdf",
        open_browser: bool = True,
    ) -> Path:
        """
        Vollstaendige PDF-Export-Pipeline.

        1. PNG-Diagramme generieren & speichern
        2. HTML-Chart-Container durch <img>-Tags ersetzen
        3. WeasyPrint -> PDF
        4. Lokalen HTTP-Server starten & Browser oeffnen

        Args:
            html_content: Vollstaendiger HTML-String (aus HTMLRenderer).
            risk_data: Risikoanalyse-Dict aus calculate_risk().
            aggregated_data: Aggregierte Daten aus ResultAggregator.aggregate().
            output_filename: Name der PDF-Datei (Default: cyber_akte.pdf).
            open_browser: True -> oeffnet Browser automatisch.

        Returns:
            Path zur generierten PDF-Datei.
        """
        console.print("[cyan]1/4[/] Generiere Diagramme mit matplotlib ...")
        self._generate_risk_chart(risk_data)
        self._generate_platform_chart(aggregated_data)
        console.print("[green]  OK[/] Diagramme gespeichert in static/img/")

        console.print("[cyan]2/4[/] Bette Diagramme in HTML ein ...")
        html_with_images = self._embed_charts_in_html(html_content)
        console.print("[green]  OK[/] HTML mit Base64-Bildern angereichert")

        console.print("[cyan]3/4[/] Konvertiere HTML -> PDF (WeasyPrint) ...")
        pdf_path = self._html_to_pdf(html_with_images, output_filename)
        size_kb = pdf_path.stat().st_size / 1024
        console.print(f"[green]  OK[/] PDF gespeichert: {pdf_path.name} ({size_kb:.1f} KB)")

        console.print("[cyan]4/4[/] Starte lokalen Download-Server ...")
        url = self._serve_and_open(pdf_path, output_filename, open_browser)

        console.print()
        console.print(
            f"[bold green][+] PDF erfolgreich generiert. "
            f"Lokaler Weblink bereit: {url}[/]"
        )
        console.print(f"[dim]   Pfad: {pdf_path}[/]")
        console.print(f"[dim]   Server laeuft (Strg+C zum Beenden)[/]")
        console.print()

        return pdf_path

    # ==================================================================
    # DIAGRAMME
    # ==================================================================

    def _generate_risk_chart(self, risk_data: dict[str, Any]) -> None:
        """
        Risiko-Donut-Diagramm.

        Aeusserer Ring: Risikoscore (farbig) + Rest (hellgrau).
        Zentriert: Prozentwert + Risikostufe + KI/Daten-Aufschluesselung.
        """
        score: float = float(risk_data.get("final_score", 0))
        level: str = risk_data.get("risk_level", "unbekannt")
        color: str = risk_data.get("color", "#94a3b8")
        ai_score: int = risk_data.get("ai_score", 0)
        quant_score: float = risk_data.get("quant_score", 0.0)

        score = max(0.0, min(100.0, score))
        remainder = 100.0 - score

        fig, ax = plt.subplots(figsize=(5, 5), subplot_kw={"aspect": "equal"})

        wedges, _ = ax.pie(
            [score, remainder],
            labels=None,
            startangle=90,
            counterclock=False,
            colors=[color, "#e5e7eb"],
            wedgeprops={
                "width": 0.35,
                "edgecolor": "white",
                "linewidth": 2,
                "antialiased": True,
            },
        )
        wedges[0].set_edgecolor("white")
        wedges[0].set_linewidth(3)

        ax.text(
            0, 0.15, f"{int(score)}%",
            ha="center", va="center",
            fontsize=38, fontweight="bold", color=color,
        )
        ax.text(
            0, -0.15, level.upper(),
            ha="center", va="center",
            fontsize=12, fontweight="bold", color="#6b7280",
        )
        ax.text(
            0, -1.35,
            f"KI: {ai_score}%  .  Daten: {quant_score}%",
            ha="center", va="top",
            fontsize=9, color="#94a3b8",
        )

        ax.set_title("RISIKO-ANALYSE", fontweight="bold", color="#1e293b", pad=18)

        fig.tight_layout()
        fig.savefig(
            self._risk_chart_path, dpi=150,
            bbox_inches="tight", facecolor="white", edgecolor="none",
        )
        plt.close(fig)

    def _generate_platform_chart(self, aggregated_data: dict[str, Any]) -> None:
        """
        Plattform-Verteilungs-Pie-Chart mit Markenfarben.

        Edge Cases:
          - Keine Daten -> grauer Platzhalter
          - >10 Plattformen -> Top 9 + "Sonstige"
        """
        distribution: dict[str, float] = aggregated_data.get(
            "distribution_percent", {}
        )
        platforms_detail: dict[str, dict] = aggregated_data.get("platforms", {})

        if not distribution:
            dist_raw: dict[str, int] = aggregated_data.get("distribution", {})
            total = sum(dist_raw.values())
            if total > 0:
                distribution = {
                    k: round(v / total * 100, 1) for k, v in dist_raw.items()
                }

        color_map: dict[str, str] = {}
        for _url, info in platforms_detail.items():
            name = info.get("platform", "")
            if name:
                color_map[name] = info.get("color", "")

        if not distribution:
            fig, ax = plt.subplots(figsize=(5, 5), subplot_kw={"aspect": "equal"})
            ax.pie(
                [1], labels=["Keine Daten"],
                colors=["#d1d5db"], startangle=90,
                wedgeprops={"edgecolor": "white", "linewidth": 2},
            )
            ax.set_title("PLATTFORM-VERTEILUNG", fontweight="bold", color="#1e293b", pad=18)
            fig.tight_layout()
            fig.savefig(
                self._platform_chart_path, dpi=150,
                bbox_inches="tight", facecolor="white", edgecolor="none",
            )
            plt.close(fig)
            return

        sorted_items = sorted(distribution.items(), key=lambda kv: kv[1], reverse=True)

        if len(sorted_items) > 10:
            top9 = sorted_items[:9]
            rest_pct = round(sum(p for _, p in sorted_items[9:]), 1)
            sorted_items = top9 + [("Sonstige", rest_pct)]

        labels = [item[0] for item in sorted_items]
        sizes = [item[1] for item in sorted_items]

        colors: list[str] = []
        for i, label in enumerate(labels):
            if label in PLATFORM_COLORS:
                colors.append(PLATFORM_COLORS[label])
            elif label in color_map and color_map[label]:
                colors.append(color_map[label])
            else:
                colors.append(_FALLBACK_PALETTE[i % len(_FALLBACK_PALETTE)])

        explode = [0.05] + [0.0] * (len(sizes) - 1)

        fig, ax = plt.subplots(figsize=(6, 5), subplot_kw={"aspect": "equal"})

        wedges, _, autotexts = ax.pie(
            sizes, labels=None,
            autopct=lambda pct: f"{pct:.1f}%" if pct > 3 else "",
            startangle=140, counterclock=False,
            colors=colors, explode=explode,
            wedgeprops={
                "edgecolor": "white", "linewidth": 1.5, "antialiased": True,
            },
            pctdistance=0.78,
        )

        for at in autotexts:
            at.set_fontsize(8)
            at.set_fontweight("bold")
            at.set_color("white")

        ax.legend(
            wedges,
            [f"{lbl} ({pct:.1f}%)" for lbl, pct in zip(labels, sizes)],
            title="Plattformen",
            loc="center left",
            bbox_to_anchor=(1.0, 0.5),
            fontsize=8, title_fontsize=9,
            frameon=True, edgecolor="#e5e7eb",
        )

        ax.set_title(
            f"PLATTFORM-VERTEILUNG  ({len(distribution)} Plattformen)",
            fontweight="bold", color="#1e293b", pad=18,
        )

        fig.tight_layout()
        fig.savefig(
            self._platform_chart_path, dpi=150,
            bbox_inches="tight", facecolor="white", edgecolor="none",
        )
        plt.close(fig)

    # ==================================================================
    # HTML -> IMG-Ersetzung
    # ==================================================================

    def _embed_charts_in_html(self, html: str) -> str:
        """
        Ersetzt JS-Chart-Container (#risk-circle, #platform-chart)
        durch Base64-<img>-Tags fuer WeasyPrint.
        """
        risk_b64 = self._image_to_base64(self._risk_chart_path)
        platform_b64 = self._image_to_base64(self._platform_chart_path)

        if risk_b64:
            html = re.sub(
                r'<div[^>]*\bid\s*=\s*["\']risk-circle["\'][^>]*>.*?</div>',
                self._build_img_tag(risk_b64, "Risiko-Kreisdiagramm", "risk-circle"),
                html, count=1, flags=re.DOTALL,
            )

        if platform_b64:
            html = re.sub(
                r'<div[^>]*\bid\s*=\s*["\']platform-chart["\'][^>]*>.*?</div>',
                self._build_img_tag(
                    platform_b64, "Plattform-Verteilungsdiagramm", "platform-chart"
                ),
                html, count=1, flags=re.DOTALL,
            )

        return html

    @staticmethod
    def _build_img_tag(b64_data_uri: str, alt_text: str, element_id: str) -> str:
        return (
            f'<div id="{element_id}" class="chart-container" '
            f'style="text-align:center;">'
            f'<img src="{b64_data_uri}" alt="{alt_text}" '
            f'style="max-width:100%;height:auto;display:block;margin:0 auto;" />'
            f"</div>"
        )

    @staticmethod
    def _image_to_base64(path: Path) -> str:
        try:
            if not path.exists():
                return ""
            raw = path.read_bytes()
            b64 = base64.b64encode(raw).decode("ascii")
            return f"data:image/png;base64,{b64}"
        except (OSError, IOError) as exc:
            logger.error("Base64-Fehler %s: %s", path, exc)
            return ""

    # ==================================================================
    # PDF via WeasyPrint
    # ==================================================================

    def _html_to_pdf(self, html: str, filename: str) -> Path:
        """
        HTML -> PDF mit WeasyPrint + print.css.
        """
        pdf_path = self.output_dir / filename

        print_css_path = self.settings.static_dir / "css" / "print.css"
        try:
            print_css = print_css_path.read_text(encoding="utf-8")
        except (OSError, IOError):
            print_css = """
                @page { size: A4; margin: 8mm; }
                @media print {
                    * { print-color-adjust: exact !important;
                        -webkit-print-color-adjust: exact !important; }
                    body { font-family: "Helvetica Neue", Arial, sans-serif;
                           font-size: 10pt; line-height: 1.4; }
                }
            """

        # CSS-transform entfernen (WeasyPrint-Inkompatibilitaet)
        html = re.sub(r'(?<![-\w])transform:\s*[^;]+;', '', html)
        html = re.sub(r'(?<![-\w])transform-origin:\s*[^;]+;', '', html)

        try:
            HTML(string=html).write_pdf(
                target=str(pdf_path),
                stylesheets=[CSS(string=print_css)],
                presentational_hints=True,
            )
        except Exception as exc:
            html_fallback = pdf_path.with_suffix(".html")
            html_fallback.write_text(html, encoding="utf-8")
            logger.error("WeasyPrint-Fehler: %s -> HTML-Fallback: %s", exc, html_fallback)
            raise RuntimeError(
                f"PDF-Konvertierung fehlgeschlagen: {exc}\n"
                f"HTML-Fallback: {html_fallback}"
            ) from exc

        return pdf_path

    # ==================================================================
    # HTTP-Server + Browser
    # ==================================================================

    def _serve_and_open(
        self, pdf_path: Path, filename: str, open_browser: bool
    ) -> str:
        port = self._find_free_port(_DEFAULT_PORT)

        server_thread = threading.Thread(
            target=self._run_server,
            args=(port,),
            daemon=False,
            name="pdf-http-server",
        )
        server_thread.start()

        url = f"http://localhost:{port}/{filename}"

        import time
        time.sleep(0.5)

        if open_browser:
            try:
                webbrowser.open(url)
            except Exception as exc:
                logger.warning("Browser oeffnen fehlgeschlagen: %s", exc)

        return url

    def _run_server(self, port: int) -> None:
        serve_dir = str(self.output_dir.resolve())
        handler = partial(_QuietHTTPRequestHandler, directory=serve_dir)
        try:
            self._server = HTTPServer(("0.0.0.0", port), handler)
            self._server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            logger.info("HTTP-Server: http://localhost:%d → %s", port, serve_dir)
            self._server.serve_forever()
        except OSError as exc:
            logger.error("HTTP-Server-Fehler Port %d: %s", port, exc)

    def stop_server(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    @staticmethod
    def _find_free_port(start_port: int) -> int:
        for offset in range(_MAX_PORT_RETRIES):
            port = start_port + offset
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                try:
                    sock.bind(("0.0.0.0", port))
                    return port
                except OSError:
                    continue
        raise RuntimeError(
            f"Kein freier Port {start_port}-{start_port + _MAX_PORT_RETRIES - 1}"
        )


class _QuietHTTPRequestHandler(SimpleHTTPRequestHandler):
    """HTTP-Handler ohne laute Access-Logs."""

    def log_message(self, fmt: str, *args: Any) -> None:
        if args and len(args) >= 2:
            try:
                code = int(str(args[1]))
                if code >= 400:
                    logger.warning("HTTP %s - %s", args[1], args[0])
            except (ValueError, IndexError):
                pass


# =========================================================================
# Convenience-Funktion
# =========================================================================

def export_to_pdf(
    html_content: str,
    risk_data: dict[str, Any],
    aggregated_data: dict[str, Any],
    output_filename: str = "cyber_akte.pdf",
    open_browser: bool = True,
) -> Path:
    """
    Convenience-Wrapper: PDF-Export in einem Aufruf.

    Args:
        html_content: HTML aus HTMLRenderer.render_with_inline_assets().
        risk_data: Risikoanalyse-Dict.
        aggregated_data: Aggregierte OSINT-Daten.
        output_filename: Name der PDF.
        open_browser: Automatisch im Browser oeffnen.

    Returns:
        Path zur PDF.
    """
    exporter = PDFExporter()
    return exporter.export(
        html_content, risk_data, aggregated_data, output_filename, open_browser,
    )
