"""
PDF Exporter v2.0 – Direkter PDF-Export + HTTP-Download-Server.

Autor: Rayquaza
Datum: 2026-06-29
"""

import logging
import os
import re
import socket
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Optional

from rich.console import Console

logger = logging.getLogger(__name__)
console = Console()


def _check_weasyprint() -> bool:
    try:
        from weasyprint import HTML  # noqa: F401
        return True
    except (ImportError, OSError) as e:
        console.print(f"[yellow]⚠ WeasyPrint nicht verfügbar: {e}[/]")
        console.print("[dim]  brew install pango cairo gdk-pixbuf libffi[/]")
        return False


class PDFExporter:
    def __init__(self) -> None:
        self.output_dir = Path("output")
        self.output_dir.mkdir(exist_ok=True)
        self._server: Optional[HTTPServer] = None

    def export_to_pdf(self, html_content: str, filename: str) -> Path:
        pdf_path = self.output_dir / f"{filename}.pdf"
        if _check_weasyprint():
            from weasyprint import HTML
            cleaned = self._clean_css_for_weasyprint(html_content)
            try:
                HTML(string=cleaned).write_pdf(str(pdf_path))
            except (AssertionError, Exception) as e:
                # WeasyPrint fehlgeschlagen → Fallback mit Minimal-CSS
                logger.warning("WeasyPrint failed: %s — retry with minimal CSS", e)
                fallback = self._build_fallback_html(html_content)
                HTML(string=fallback).write_pdf(str(pdf_path))
            size_kb = pdf_path.stat().st_size / 1024
            console.print(f"[bold green]✓[/] PDF erstellt: [cyan]{pdf_path.name}[/] ({size_kb:.1f} KB)")
        else:
            html_path = self.output_dir / f"{filename}.html"
            html_path.write_text(html_content, encoding="utf-8")
            console.print(f"[yellow]⚠ PDF nicht möglich – HTML: {html_path}[/]")
            return html_path
        return pdf_path

    def _build_fallback_html(self, original_html: str) -> str:
        """Baut Fallback-HTML mit garantiert WeasyPrint-kompatiblem CSS."""
        import re
        # Extrahiere den Body-Inhalt
        body_match = re.search(r'<body[^>]*>(.*?)</body>', original_html, re.DOTALL)
        body = body_match.group(1) if body_match else '<h1>OSINT BBW Tool</h1>'
        # Extrahiere Username aus dem Titel
        title_match = re.search(r'<title>(.*?)</title>', original_html)
        title = title_match.group(1) if title_match else 'OSINT Report'
        return f'''<!DOCTYPE html><html lang="de"><head><meta charset="UTF-8"><title>{title}</title>
<style>
@page {{ size: A4; margin: 15mm; }}
body {{ font-family: Helvetica, Arial, sans-serif; color: #1e293b; font-size: 11pt; line-height: 1.5; }}
h1 {{ font-size: 20pt; color: #1e293b; border-bottom: 2px solid #3b82f6; padding-bottom: 5mm; }}
h2 {{ font-size: 14pt; color: #334155; margin-top: 8mm; }}
p, li {{ font-size: 10pt; }}
.risk-section {{ border: 2px solid #e2e8f0; border-radius: 8px; padding: 5mm; margin: 5mm 0; }}
table {{ width: 100%; border-collapse: collapse; margin: 5mm 0; }}
th, td {{ text-align: left; padding: 3mm; border-bottom: 1px solid #e2e8f0; }}
th {{ color: #64748b; font-size: 9pt; text-transform: uppercase; }}
</style></head><body>{body}</body></html>'''

    def _clean_css_for_weasyprint(self, html: str) -> str:
        """
        Minimales CSS-Cleaning für WeasyPrint 69.
        - transform/transform-origin entfernen
        - @page A4 hinzufügen
        """
        import re

        # CSS-transform (nicht text-transform!)
        html = re.sub(r'(?<![-\w])transform:\s*[^;]+;', '', html)
        html = re.sub(r'(?<![-\w])transform-origin:\s*[^;]+;', '', html)

        # conic-gradient → solid
        html = re.sub(r'background:\s*conic-gradient\([^)]+\);?', 'background: #e2e8f0;', html)

        # @page A4 in den ersten <style>-Tag einfügen (für Seitengröße)
        html = html.replace('</style>', '\n@page { size: A4; margin: 10mm; }\n</style>', 1)

        return html

    def start_download_server(self, pdf_path: Path, port: int = 8080) -> str:
        os.chdir(str(self.output_dir))
        handler = SimpleHTTPRequestHandler
        # Socket-Option: Port sofort nach Schließen wiederverwendbar
        HTTPServer.allow_reuse_address = True
        self._server = HTTPServer(("0.0.0.0", port), handler)
        self._server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        t = threading.Thread(target=self._server.serve_forever, daemon=True)
        t.start()
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            ip = "127.0.0.1"
        url = f"http://{ip}:{port}/{pdf_path.name}"
        console.print(f"[bold cyan]📥 PDF-Download:[/] [link={url}]{url}[/]")
        console.print("[dim]Server läuft. Drücke Ctrl+C zum Beenden.[/]")
        return url

    def stop_server(self) -> None:
        if self._server:
            self._server.server_close()
            self._server = None
