#!/usr/bin/env python3
"""
OSINT BBW Tool v2.0 — Haupteinstiegspunkt.

3-Phasen-OSINT-Pipeline:
  1. Sherlock-Scan    – Profilprüfung auf 10 Plattformen
  2. Google-Dorking   – Erweiterte Suche + DuckDuckGo-Fallback
  3. KI-Analyse       – Risikobewertung via Ollama/OpenAI
  → Terminal-Report   – Ergebnisse direkt im Terminal

Autor: Rayquaza, 2026
"""

import logging
import sys

from rich.console import Console
from rich.traceback import install as install_rich_traceback

from config.settings import get_settings
from src.ai_analyser.ai_client import AIClient
from src.ai_analyser.prompt_templates import build_risk_prompt
from src.ai_analyser.risk_calculator import calculate_risk
from src.cli.input_handler import parse_args
from src.cli.terminal_banner import (
    print_banner, print_status, print_phase_header,
)
from src.osint_engine.google_dorker import GoogleDorker
from src.osint_engine.result_aggregator import ResultAggregator
from src.osint_engine.sherlock_scanner import SherlockScanner
from src.report_generator.terminal_report import render_terminal_report

install_rich_traceback(show_locals=False, width=120)
console = Console()


def main() -> None:
    print_banner()
    args = parse_args()
    settings = get_settings()

    log_level = logging.DEBUG if (args.verbose or settings.debug) else logging.INFO
    logging.basicConfig(level=log_level, format="%(asctime)s [%(levelname)-7s] %(name)s: %(message)s", datefmt="%H:%M:%S")

    target = args.target_full
    target_url = args.target_single

    # ================================================================
    # PHASE 1: SHERLOCK
    # ================================================================
    print_phase_header(1, 3, "Sherlock-Profilscan")
    sherlock_results = []
    scanner = None
    try:
        platform_filter = [p.strip() for p in args.platforms.split(",") if p.strip()] if args.platforms else None
        scanner = SherlockScanner(platforms_filter=platform_filter)
        sherlock_results = scanner.scan(target_url)
        found = sum(1 for r in sherlock_results if r.get("exists"))
        with_avatar = sum(1 for r in sherlock_results if r.get("avatar_base64"))
        print_status("PHASE 1/3", f"Sherlock-Scan abgeschlossen: {found} Profile gefunden ({with_avatar} mit Avatar)", "ok")
    except Exception as e:
        print_status("PHASE 1/3", f"Fehler: {e}", "error")

    # ================================================================
    # PHASE 2: GOOGLE-DORKING
    # ================================================================
    print_phase_header(2, 3, "Google-Dorking & DuckDuckGo")
    dork_results = []
    try:
        dorker = GoogleDorker()
        dork_results = dorker.dork(target, args.keywords or [], scanner.platforms if scanner else [])
        if len(dork_results) < 3 and args.keywords:
            print_status("PHASE 2/3", "Wenige Google-Treffer – DuckDuckGo-Fallback...", "warning")
            dork_results.extend(dorker.duckduckgo_fallback(target, args.keywords))
        print_status("PHASE 2/3", f"Dorking abgeschlossen: {len(dork_results)} URLs gefunden", "ok")
    except Exception as e:
        print_status("PHASE 2/3", f"Fehler: {e}", "error")

    # ================================================================
    # PHASE 3: AGGREGATION + KI
    # ================================================================
    print_phase_header(3, 3, "KI-Risikoanalyse")
    aggregator = ResultAggregator()
    aggregated = aggregator.aggregate(target, sherlock_results, dork_results)
    stats = aggregator.get_statistics(aggregated)
    console.print(f"  [dim]{aggregated['total_profiles']} Profile auf {stats['unique_platforms']} Plattformen[/]")

    risk_data = {
        "final_score": 0, "ai_score": 0, "quant_score": 0.0,
        "color": "#94a3b8", "risk_level": "unbekannt", "risk_level_class": "",
        "attack_surface": ["Keine KI-Analyse"], "summary": "Keine Analyse."
    }

    if not args.no_ai:
        try:
            prompt = build_risk_prompt(aggregated)
            ai_client = AIClient()
            ai_response = ai_client.analyse(prompt)
            risk_data = calculate_risk(ai_response, aggregated)
            print_status("PHASE 3/3", f"KI-Analyse: {risk_data['final_score']}% – {risk_data['risk_level'].upper()}", "ok")
        except Exception as e:
            print_status("PHASE 3/3", f"KI-Fehler – Fallback: {e}", "warning")
    else:
        risk_data["attack_surface"] = [f"{aggregated.get('total_profiles',0)} Profile auf {len(aggregated.get('platforms',{}))} Plattformen"]
        print_status("PHASE 3/3", "KI deaktiviert (--no-ai)", "info")

    # ================================================================
    # TERMINAL-REPORT
    # ================================================================
    try:
        render_terminal_report(
            target=target,
            sherlock_results=sherlock_results,
            dork_results=dork_results,
            aggregated=aggregated,
            risk_data=risk_data,
            stats=stats,
        )
        print_status("REPORT", "Terminal-Report fertig", "ok")
    except Exception as e:
        print_status("REPORT", f"Fehler: {e}", "error")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]🛑 Abgebrochen.[/]")
        sys.exit(0)
    except Exception as exc:
        console.print(f"\n[bold red]❌ Fehler:[/] {exc}")
        if "--verbose" in sys.argv or "-v" in sys.argv:
            raise
        sys.exit(1)
