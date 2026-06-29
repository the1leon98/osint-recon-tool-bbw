"""
Sherlock-basierter Username-Scanner — Eigenständige Implementierung.

Durchsucht konfigurierte Social-Media-Plattformen nach einem gegebenen
Benutzernamen und verifiziert die Profil-Existenz via HTTP-Statuscodes
und Redirect-Analyse.

Design-Entscheidungen:
- KEIN externes Sherlock-Paket — die Logik ist eigenständig und
  vollständig nachvollziehbar (kein Black-Box-Dependency).
- Defensive HTTP-Requests: Timeout, ConnectionError, unerwartete
  Statuscodes — jeder Fehler wird protokolliert, nie als Crash.
- Redirect-Erkennung: Leitet die Plattform auf /login oder /signin
  um, existiert das Profil NICHT (false positive vermeiden).
- Connection-Pooling via requests.Session für bis zu 30 % weniger
  Latenz bei mehreren Requests zur gleichen Domain.
- User-Agent-Rotation via fake_useragent gegen Fingerprinting.
- Fortschrittsanzeige mit rich.Progress (Live-Display).

Autor: Rayquaza
Datum: 2026-06-29
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional

import requests
from fake_useragent import UserAgent
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn

from config.settings import get_settings

logger = logging.getLogger(__name__)
console = Console()

# Redirect-Indikatoren: Enthält die finale URL eines dieser Muster,
# wurde der Request vermutlich auf eine Login-Seite umgeleitet →
# Profil existiert nicht (oder ist privat).
_LOGIN_REDIRECT_PATTERNS: tuple[str, ...] = (
    "/login", "/signin", "/signup", "/register",
    "/auth", "/account", "/accounts", "/landing",
    "?return_to=", "?redirect=",
)

# HTTP-Statuscodes, die NICHT auf ein existierendes Profil hindeuten,
# selbst wenn sie 200 sind (z.B. Soft-404 oder Login-Seite).
# 403/404/410 → definitiv nicht vorhanden.
# 429 → Rate-Limited, in diesem Lauf als "unsicher" markiert.
_NON_EXISTENT_STATUSES: frozenset[int] = frozenset({403, 404, 410, 451})


class SherlockScanner:
    """
    Eigenständiger Username-Scanner für Social-Media-Plattformen.

    Lädt Plattform-Konfigurationen aus platforms.json, prüft jede
    Plattform via HTTP-GET auf Profil-Existenz und liefert eine
    strukturierte Ergebnisliste mit Konfidenzwerten.

    Attributes:
        platforms: Liste der zu prüfenden Plattform-Dicts (gefiltert).
        settings: Gecachte Settings-Instanz (Singleton).
        session: requests.Session mit Connection-Pooling.
        ua: fake_useragent-Instanz für User-Agent-Rotation.
    """

    def __init__(self, platforms_filter: Optional[list[str]] = None) -> None:
        """
        Initialisiert den Scanner mit Plattform-Konfiguration.

        Args:
            platforms_filter: Optionale Liste von Plattform-Namen (case-insensitive).
                              Nur diese Plattformen werden gescannt.
                              None = alle Plattformen aus platforms.json.
        """
        self.settings = get_settings()

        # Plattformen aus JSON laden
        config_path = (
            Path(__file__).resolve().parent.parent.parent
            / "config"
            / "platforms.json"
        )
        with open(config_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        all_platforms: list[dict] = data.get("platforms", [])

        # Filtern, falls gewünscht
        if platforms_filter:
            filter_set = {p.lower().strip() for p in platforms_filter}
            self.platforms = [
                p for p in all_platforms if p["name"].lower() in filter_set
            ]
            if not self.platforms:
                logger.warning(
                    "Keine Plattformen nach Filter übrig. Filter: %s",
                    platforms_filter,
                )
        else:
            self.platforms = all_platforms

        # Sortieren nach Gewicht (höchste zuerst) für sinnvolle Progress-Reihenfolge
        self.platforms.sort(key=lambda p: p.get("weight", 0.0), reverse=True)

        # Session mit Connection-Pooling (wiederverwendet TCP-Verbindungen)
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
        })

        # User-Agent-Rotation
        self.ua = UserAgent(
            browsers=["chrome", "firefox", "safari", "edge"],
            os=["windows", "macos", "linux"],
            min_version=100.0,
        )

        logger.info(
            "SherlockScanner initialisiert: %d Plattform(en) geladen.",
            len(self.platforms),
        )

    def scan(self, username: str) -> list[dict]:
        """
        Führt einen vollständigen Scan über alle Plattformen aus.

        Iteriert mit rich.Progress über jede Plattform, prüft die
        Profil-URL und sammelt die Ergebnisse.

        Args:
            username: Der zu prüfende Benutzername (bereits CLI-validiert).

        Returns:
            Liste von Ergebnis-Dicts mit folgender Struktur:
            {
                "platform": str,       # Name der Plattform (z.B. "GitHub")
                "url": str,            # Geprüfte URL (z.B. "https://github.com/user")
                "exists": bool,        # True wenn Profil gefunden
                "status_code": int,    # HTTP-Statuscode (0 bei Netzwerkfehler)
                "confidence": float,   # 0.0 (kein Profil) bis 1.0 (sicher gefunden)
                "final_url": str,      # URL nach Redirects (zur Diagnose)
                "response_time_ms": int,  # Antwortzeit in Millisekunden
                "error": str | None,   # Fehlermeldung oder None
            }
        """
        results: list[dict] = []
        total = len(self.platforms)

        console.print(
            f"\n[bold cyan]🔍 Starte Scan für [yellow]{username}[/yellow] "
            f"auf {total} Plattform(en)...[/]\n"
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console,
            transient=False,
        ) as progress:
            task = progress.add_task(
                "[cyan]Plattformen prüfen...", total=total
            )

            for platform in self.platforms:
                progress.update(
                    task,
                    description=f"[cyan]Prüfe {platform['name']}...",
                )

                result = self._check_platform(username, platform)
                results.append(result)

                # Status-Icon basierend auf Ergebnis
                if result["exists"]:
                    icon = "[green]✓[/]"
                elif result["error"]:
                    icon = "[yellow]?[/]"
                else:
                    icon = "[red]✗[/]"

                progress.console.print(
                    f"  {icon} {platform['name']:12s} → "
                    f"HTTP {result['status_code']} "
                    f"({result['response_time_ms']}ms)"
                )

                progress.advance(task)

                # Rate-Limiting zwischen Requests
                if platform != self.platforms[-1]:  # kein Sleep nach der letzten
                    time.sleep(self.settings.rate_limit_delay)

        # Statistik
        found = sum(1 for r in results if r["exists"])
        failed = sum(1 for r in results if r["error"])
        not_found = total - found - failed

        console.print(
            f"\n[bold]Scan abgeschlossen:[/] "
            f"[green]{found} gefunden[/] · "
            f"[red]{not_found} nicht gefunden[/] · "
            f"[yellow]{failed} Fehler[/] "
            f"({total} gesamt)\n"
        )

        return results

    def scan_single(self, username: str, platform_name: str) -> dict:
        """
        Prüft eine einzelne Plattform (nützlich für Demo/Debug).

        Args:
            username: Zu prüfender Benutzername.
            platform_name: Exakter Plattform-Name (z.B. "GitHub").

        Returns:
            Ergebnis-Dict (gleiche Struktur wie scan()).

        Raises:
            ValueError: Wenn die Plattform nicht in der Konfiguration existiert.
        """
        platform = next(
            (p for p in self.platforms if p["name"].lower() == platform_name.lower()),
            None,
        )
        if platform is None:
            available = [p["name"] for p in self.platforms]
            raise ValueError(
                f"Plattform '{platform_name}' nicht gefunden. "
                f"Verfügbar: {', '.join(available)}"
            )

        return self._check_platform(username, platform)

    def _check_platform(self, username: str, platform: dict) -> dict:
        """
        Kernlogik: Prüft eine Plattform-URL auf Profil-Existenz.

        Defensive HTTP-Prüfung mit:
          - User-Agent-Rotation pro Request
          - Timeout (aus Settings)
          - Redirect-Analyse (Login-Seite = kein Profil)
          - Statuscode-Heuristik (200 != garantiert existent)
          - Fehlertoleranz (Timeout/ConnectionError → confidence 0.0)

        Args:
            username: Der zu prüfende Benutzername.
            platform: Plattform-Dict aus platforms.json.

        Returns:
            Ergebnis-Dict (siehe scan() für Struktur).
        """
        url = platform["check_url"].format(username=username)
        base_result: dict = {
            "platform": platform["name"],
            "url": url,
            "exists": False,
            "status_code": 0,
            "confidence": 0.0,
            "final_url": url,
            "response_time_ms": 0,
            "error": None,
        }

        headers = {"User-Agent": self.ua.random}

        try:
            start = time.monotonic()
            response = self.session.get(
                url,
                headers=headers,
                timeout=self.settings.request_timeout,
                allow_redirects=True,
            )
            elapsed_ms = int((time.monotonic() - start) * 1000)
            base_result["response_time_ms"] = elapsed_ms
            base_result["status_code"] = response.status_code
            base_result["final_url"] = response.url

            # --- Heuristik: Profil existiert? ---

            # Fall 1: Statuscode deutet auf nicht-existent hin (404, 403, etc.)
            if response.status_code in _NON_EXISTENT_STATUSES:
                base_result["exists"] = False
                base_result["confidence"] = 0.95
                return base_result

            # Fall 2: Rate-Limited → unsicher, als "nicht gefunden" mit 0.5
            if response.status_code == 429:
                base_result["exists"] = False
                base_result["confidence"] = 0.5
                base_result["error"] = "Rate-limited (HTTP 429)"
                logger.warning("Rate-limited bei %s → %s", platform["name"], url)
                return base_result

            # Fall 3: Status 200 — aber ist es wirklich das Profil?
            if response.status_code == 200:
                # Prüfe auf Redirect zur Login-Seite (Soft-404)
                final_url_lower = response.url.lower()
                if any(pattern in final_url_lower for pattern in _LOGIN_REDIRECT_PATTERNS):
                    base_result["exists"] = False
                    base_result["confidence"] = 0.85
                    logger.debug(
                        "Redirect zu Login erkannt: %s → %s",
                        url, response.url,
                    )
                    return base_result

                # Kein Login-Redirect → Profil existiert sehr wahrscheinlich
                base_result["exists"] = True
                base_result["confidence"] = 0.95
                # Profilbild extrahieren (best-effort)
                try:
                    avatar = self._extract_profile_image(response.text, response.url)
                    if avatar:
                        base_result["avatar_base64"] = avatar
                except Exception:
                    pass  # Bild-Extraktion ist optional
                return base_result

            # Fall 4: Alles andere (301, 302, 500, ...) → unsicher
            base_result["exists"] = False
            base_result["confidence"] = 0.3
            logger.debug(
                "Unerwarteter Status %d bei %s → %s",
                response.status_code, platform["name"], url,
            )
            return base_result

        except requests.exceptions.Timeout:
            base_result["error"] = f"Timeout nach {self.settings.request_timeout}s"
            logger.warning("Timeout bei %s: %s", platform["name"], url)
            return base_result

        except requests.exceptions.ConnectionError as exc:
            base_result["error"] = f"Verbindungsfehler: {exc}"
            logger.warning("ConnectionError bei %s: %s — %s", platform["name"], url, exc)
            return base_result

        except requests.exceptions.TooManyRedirects:
            base_result["error"] = "Zu viele Redirects"
            logger.warning("TooManyRedirects bei %s: %s", platform["name"], url)
            return base_result

        except requests.exceptions.RequestException as exc:
            base_result["error"] = f"Netzwerkfehler: {type(exc).__name__}"
            logger.error(
                "Unbekannter Request-Fehler bei %s: %s — %s",
                platform["name"], url, exc,
            )
            return base_result

        except Exception as exc:
            # Letzter Fallback — sollte nie passieren, aber defensiv
            base_result["error"] = f"Unerwarteter Fehler: {exc}"
            logger.exception(
                "Unerwarteter Fehler bei %s: %s", platform["name"], url
            )
            return base_result

    def _extract_profile_image(self, html: str, page_url: str) -> Optional[str]:
        """Extrahiert og:image oder Profilbild aus HTML via regex + base64-Kodierung."""
        import base64 as b64
        import re as _re
        patterns = [
            r'<meta\s+property="og:image"\s+content="([^"]+)"',
            r'<meta\s+name="twitter:image"\s+content="([^"]+)"',
            r'<img[^>]+class="[^"]*profile[^"]*"[^>]+src="([^"]+)"',
            r'<img[^>]+src="([^"]*avatar[^"]*)"',
        ]
        img_url = None
        for pat in patterns:
            m = _re.search(pat, html, _re.IGNORECASE)
            if m:
                img_url = m.group(1)
                break
        if not img_url:
            return None
        if img_url.startswith("/"):
            from urllib.parse import urljoin
            img_url = urljoin(page_url, img_url)
        try:
            resp = self.session.get(img_url, timeout=5)
            if resp.status_code == 200 and len(resp.content) > 100:
                ct = resp.headers.get("content-type", "image/jpeg")
                return f"data:{ct};base64,{b64.b64encode(resp.content).decode()}"
        except Exception:
            pass
        return None
