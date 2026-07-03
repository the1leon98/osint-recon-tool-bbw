"""
CLI Input Handler – Kommandozeilen-Parsing & Validierung v2.0.

Parsed Benutzereingaben via argparse, validiert den Zielnamen streng.
Unterstützt Vor- und Nachnamen (1-2 Wörter).

--target statt username (professioneller)
target_full = "Justin Bieber" (für Google-Dorks)
target_single = "justinbieber" (für Profil-URLs)

Autor: Rayquaza
Datum: 2026-06-29
"""

import argparse
import re
import sys
from typing import List, Optional

from rich.console import Console

console = Console()


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "BBW OSINT Tool v2.0 — "
            "Automatisierte Open-Source-Intelligence-Recherche\n\n"
            "Durchsucht Social-Media-Plattformen nach einem Zielnamen, "
            "führt Google-Dorking durch und erstellt "
            "eine KI-gestützte Risikoanalyse direkt im Terminal."
        ),
        epilog="Ethische Nutzung: Nur für eigene Profile und autorisierte Sicherheitsaudits.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "target", type=str,
        help="Zu recherchierender Name (1-2 Wörter). Erlaubt: Buchstaben, Bindestrich, Apostroph. Beispiel: 'Justin Bieber'",
    )
    parser.add_argument("--keywords", "-k", nargs="+", type=str, default=None, help="Zusätzliche Suchbegriffe")
    parser.add_argument("--platforms", "-p", type=str, default=None, help="Komma-separierte Plattformen")
    parser.add_argument("--no-ai", action="store_true", dest="no_ai", default=False, help="KI-Analyse deaktivieren")
    parser.add_argument("--verbose", "-v", action="store_true", dest="verbose", default=False, help="Debug-Ausgaben")

    if argv is not None:
        args = parser.parse_args(argv)
    else:
        args = parser.parse_args()

    target = args.target.strip()
    validate_target(target)

    args.target_full = target
    args.target_single = re.sub(r'[^a-zA-Z0-9]', '', target).lower()
    args.target_words = target.split()

    console.print(f"[bold green]✓[/] Ziel validiert: [cyan]{target}[/cyan] → URL: [dim]{args.target_single}[/dim]")
    return args


def validate_target(target: str) -> None:
    if not target or len(target.strip()) == 0:
        console.print("[bold red]Fehler:[/] Zielname darf nicht leer sein.")
        sys.exit(1)
    target = target.strip()
    if len(target) < 2:
        console.print(f"[bold red]Fehler:[/] Zielname zu kurz: {len(target)} Zeichen.")
        sys.exit(1)
    if "http://" in target.lower() or "https://" in target.lower():
        console.print("[bold red]Fehler:[/] Zielname darf keine URL sein.\n  ➤ Beispiel: 'Justin Bieber'")
        sys.exit(1)
    words = target.split()
    if len(words) > 2:
        console.print("[bold red]Fehler:[/] Maximal 2 Wörter (Vor- und Nachname).\n  ➤ Für zusätzliche Begriffe: --keywords")
        sys.exit(1)
    for word in words:
        if not re.match(r"^[a-zA-Z0-9äöüßÄÖÜ._'-]+$", word):
            illegal = set(word) - set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789äöüßÄÖÜ._'-")
            console.print(f"[bold red]Fehler:[/] Ungültige Zeichen: [red]{''.join(sorted(illegal))}[/red]")
            sys.exit(1)
