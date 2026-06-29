"""
Terminal Report — Vollständiger Report direkt im Terminal.

Rendert alle OSINT-Ergebnisse, Risikoanalyse und Profilbilder
als farbige Rich-Komponenten — kein PDF nötig.

Autor: Rayquaza
Datum: 2026-06-29
"""

import base64
import os
import sys
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.layout import Layout
from rich import box

console = Console()

# Farben
CYAN = "#00ffff"
GREEN = "#00ff00"
YELLOW = "#ffaa00"
RED = "#ff4444"
WHITE = "#ffffff"
DIM = "#666666"

PLATFORM_EMOJIS = {
    "GitHub": "🐙", "Instagram": "📸", "YouTube": "▶️", "Snapchat": "👻",
    "Pinterest": "📌", "Twitter / X": "🐦", "Reddit": "🤖", "TikTok": "🎵",
    "LinkedIn": "💼", "Twitch": "🎮",
}


def render_terminal_report(
    target: str,
    sherlock_results: list[dict],
    dork_results: list[dict],
    aggregated: dict[str, Any],
    risk_data: dict[str, Any],
    stats: dict[str, Any],
) -> None:
    """
    Rendert den kompletten OSINT-Report im Terminal.
    """
    console.clear()
    
    # ═══════════════════════════════════════
    # HEADER
    # ═══════════════════════════════════════
    console.print()
    console.print(Panel(
        f"[bold {CYAN}]OSINT BBW TOOL v2.0[/] — [bold white]Rayquaza[/]\n"
        f"[dim]Automatisierte Open-Source-Intelligence Recherche[/]",
        border_style=CYAN, padding=(1, 2)
    ))
    
    # ═══════════════════════════════════════
    # ZIEL & RISIKO
    # ═══════════════════════════════════════
    risk_color = risk_data.get("color", YELLOW)
    risk_score = risk_data.get("final_score", 0)
    risk_level = risk_data.get("risk_level", "unbekannt").upper()
    
    # Risiko-Balken (ASCII-Art)
    bar_width = 40
    filled = int(bar_width * risk_score / 100)
    bar = f"[{risk_color}]" + "█" * filled + "[/]" + "░" * (bar_width - filled)
    
    header_table = Table(box=box.ROUNDED, show_header=False, border_style=CYAN, padding=(0, 2))
    header_table.add_column("k", style="bold white", width=15)
    header_table.add_column("v", style="white")
    header_table.add_row("🎯 ZIEL:", target)
    header_table.add_row("📊 RISIKO:", f"[{risk_color}]{risk_score}% — {risk_level}[/]")
    header_table.add_row("", bar)
    header_table.add_row("📱 PROFILE:", f"{aggregated.get('total_profiles', 0)} gefunden auf {stats.get('unique_platforms', 0)} Plattformen")
    header_table.add_row("🔍 DORKING:", f"{len(dork_results)} URLs via Google/DDG")
    console.print(header_table)
    
    # ═══════════════════════════════════════
    # PROFILBILD (iTerm2 inline image)
    # ═══════════════════════════════════════
    _show_profile_image(aggregated)
    
    # ═══════════════════════════════════════
    # PLATTFORMEN
    # ═══════════════════════════════════════
    console.print()
    console.print(f"[bold {CYAN}]📱 GEFUNDENE PLATTFORMEN[/]")
    
    platform_table = Table(box=box.SIMPLE, border_style=DIM, padding=(0, 2))
    platform_table.add_column("Plattform", style="white")
    platform_table.add_column("Status", style="green")
    platform_table.add_column("URL", style="dim", max_width=50)
    platform_table.add_column("Avatar", style="dim")
    
    for r in sherlock_results:
        emoji = PLATFORM_EMOJIS.get(r.get("platform", ""), "🔗")
        status = "[green]✓[/]" if r.get("exists") else "[red]✗[/]"
        url = r.get("url", "")[:45]
        avatar = "[green]📷[/]" if r.get("avatar_base64") else ""
        platform_table.add_row(f"{emoji} {r.get('platform', '?')}", status, url, avatar)
    
    console.print(platform_table)
    
    # ═══════════════════════════════════════
    # KI-ANALYSE
    # ═══════════════════════════════════════
    console.print()
    console.print(f"[bold {CYAN}]🧠 KI-RISIKOANALYSE[/]")
    
    analysis = Table(box=box.ROUNDED, border_style=risk_color, padding=(1, 2))
    analysis.add_column("", style="bold white", width=20)
    analysis.add_column("", style="white")
    analysis.add_row("KI-Score:", f"[{risk_color}]{risk_data.get('ai_score', 0)}%[/]")
    analysis.add_row("Quant. Score:", f"[dim]{risk_data.get('quant_score', 0)}%[/]")
    analysis.add_row("Final Score:", f"[bold {risk_color}]{risk_score}%[/]")
    analysis.add_row("Risikostufe:", f"[bold {risk_color}]{risk_level}[/]")
    console.print(analysis)
    
    # ═══════════════════════════════════════
    # ANGRIFFSFLÄCHEN
    # ═══════════════════════════════════════
    surfaces = risk_data.get("attack_surface", [])
    if surfaces:
        console.print()
        console.print(f"[bold {RED}]⚠ ANGRIFFSFLÄCHEN[/]")
        for i, s in enumerate(surfaces, 1):
            console.print(f"  [{RED}]{i}.[/] {s}")
    
    # Zusammenfassung
    summary = risk_data.get("summary", "")
    if summary:
        console.print()
        console.print(Panel(
            summary, title="📋 Zusammenfassung",
            border_style=CYAN, padding=(1, 2)
        ))
    
    # ═══════════════════════════════════════
    # VERTEILUNG (ASCII-Balken)
    # ═══════════════════════════════════════
    distribution = aggregated.get("distribution_percent", {})
    if distribution:
        console.print()
        console.print(f"[bold {CYAN}]📊 VERTEILUNG[/]")
        for name, pct in sorted(distribution.items(), key=lambda x: x[1], reverse=True):
            bar_w = max(1, int(pct / 2))
            emoji = PLATFORM_EMOJIS.get(name, "🔗")
            console.print(f"  {emoji} {name:15s} [dim]{'█' * bar_w}[/] {pct}%")
    
    console.print()
    console.print(f"[dim]{'─' * 60}[/]")
    console.print(f"[dim]OSINT BBW Tool v2.0 — Rayquaza — 2026-06-29[/]")
    console.print()


def _show_profile_image(aggregated: dict) -> None:
    """Zeigt Profilbild im Terminal (iTerm2/Kitty) oder als Base64-Fallback."""
    platforms = aggregated.get("platforms", {})
    for url, info in platforms.items():
        avatar = info.get("avatar_base64", "")
        if avatar and len(avatar) > 100:
            # iTerm2 inline image protocol
            if os.environ.get("ITERM_SESSION_ID"):
                b64_data = avatar.split(",", 1)[-1]
                console.print(f"\n  [dim]📷 Profilbild von {info.get('platform', '?')}:[/]")
                sys.stdout.write(f"\033]1337;File=inline=1;width=200px:{b64_data}\a\n")
                console.print()
            else:
                console.print(f"\n  [dim]📷 Profilbild gefunden ({info.get('platform', '?')}) — {len(avatar)} Bytes Base64[/]")
            return
    console.print(f"\n  [dim]📷 Kein Profilbild gefunden[/]")


def render_quick_report(main_module_data: dict) -> None:
    """Quick-Report direkt nach dem Scan."""
    render_terminal_report(
        target=main_module_data.get("target", "?"),
        sherlock_results=main_module_data.get("sherlock_results", []),
        dork_results=main_module_data.get("dork_results", []),
        aggregated=main_module_data.get("aggregated", {}),
        risk_data=main_module_data.get("risk_data", {}),
        stats=main_module_data.get("stats", {}),
    )
