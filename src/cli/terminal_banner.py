"""
Terminal Banner & Status Display für BBW OSINT v2.0.

Professionelles Terminal-Branding mit ASCII-Art-Logo,
farbigen Statusmeldungen und Rich-Komponenten.

Autor: Rayquaza
Datum: 2026-06-29
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

console = Console()

# Farbpalette
CYAN = "#00ffff"
GREEN = "#00ff00"
YELLOW = "#ffaa00"
RED = "#ff4444"
MAGENTA = "#ff00ff"
BLUE = "#4488ff"
DIM = "#666666"


def print_banner() -> None:
    """Zeigt das farbige BBW OSINT ASCII-Art-Logo beim Start."""
    logo = f"""
[bold {CYAN}]╔═══════════════════════════════════════════════════════════╗
║  ██████╗  ██████╗  ██╗    ██╗                             ║
║  ██╔══██╗ ██╔══██╗ ██║    ██║                             ║
║  ██████╔╝ ██████╔╝ ██║ █╗ ██║                             ║
║  ██╔══██╗ ██╔══██╗ ██║███╗██║                             ║
║  ██████╔╝ ██████╔╝ ╚███╔███╔╝                             ║
║  ╚═════╝  ╚═════╝   ╚══╝╚══╝                              ║
║                                                           ║
║   ██████╗  ███████╗  ██╗   ███╗   ██╗  ████████╗          ║
║  ██╔═══██╗ ██╔════╝  ██║   ████╗  ██║  ╚══██╔══╝          ║
║  ██║   ██║ ███████╗  ██║   ██╔██╗ ██║     ██║             ║
║  ██║   ██║ ╚════██║  ██║   ██║╚██╗██║     ██║             ║
║  ╚██████╔╝ ███████║  ██║   ██║ ╚████║     ██║             ║
║   ╚═════╝  ╚══════╝  ╚═╝   ╚═╝  ╚═══╝     ╚═╝             ║
║                                                           ║
║         OSINT BBW TOOL v2.0 — Rayquaza                    ║
╚═══════════════════════════════════════════════════════════╝[/]"""

    console.print(logo)
    console.print()


def print_status(phase: str, message: str, status: str = "running") -> None:
    """
    Zeigt eine farbige Statusmeldung im professionellen Format.

    Args:
        phase: Phasen-Beschriftung (z.B. "PHASE 1/4")
        message: Beschreibung (z.B. "Sherlock-Scan...")
        status: "running", "ok", "error", "warning", "info"
    """
    icons = {
        "running": f"[{CYAN}]⏳[/]",
        "ok": f"[{GREEN}]✓[/]",
        "error": f"[{RED}]✗[/]",
        "warning": f"[{YELLOW}]⚠[/]",
        "info": f"[{BLUE}]ℹ[/]",
    }
    icon = icons.get(status, icons["running"])

    phase_styles = {
        "1": "🔍",
        "2": "🕵️",
        "3": "🧠",
    }
    phase_emoji = phase_styles.get(phase.split("/")[0].split()[-1][0], "•")

    console.print(
        f"  {icon} [{CYAN}]{phase_emoji} {phase}[/] {message}"
    )


def print_result_panel(
    target: str,
    risk_score: int,
    risk_level: str,
    risk_color: str,
    total_profiles: int,
    total_platforms: int,
) -> None:
    """
    Zeigt eine farbige Zusammenfassung als Rich Panel.

    Args:
        target: Ziel-Name
        risk_score: Risiko-Score 0-100
        risk_level: "niedrig"|"mittel"|"hoch"|"kritisch"
        risk_color: Hex-Farbe
        total_profiles: Anzahl gefundener Profile
        total_platforms: Anzahl Plattformen
    """
    table = Table(box=box.ROUNDED, show_header=False, border_style=CYAN)
    table.add_column("key", style=f"bold {CYAN}", width=16)
    table.add_column("value", style="white")

    table.add_row("🎯 ZIEL:", target)
    table.add_row(
        "📊 RISIKO:",
        f"[{risk_color}]{risk_score}% ({risk_level.upper()})[/]",
    )
    table.add_row(
        "📱 PLATTFORMEN:",
        f"{total_profiles} Profile auf {total_platforms} Plattformen",
    )

    console.print()
    console.print(Panel(table, border_style=CYAN, padding=(1, 2)))
    console.print()


def print_phase_header(phase_num: int, total: int, name: str) -> None:
    """Zeigt einen Phasen-Header."""
    bar = "█" * phase_num + "░" * (total - phase_num)
    console.print(
        f"\n  [{CYAN}]┌─ PHASE {phase_num}/{total}: {name}[/]"
    )
    console.print(f"  [{CYAN}]│ [{BAR_COLOR}]{bar}[/] [{DIM}]{phase_num}/{total}[/]")
    console.print(f"  [{CYAN}]└" + "─" * 40)


# Dynamische Farbe für Fortschrittsbalken
BAR_COLOR = GREEN
