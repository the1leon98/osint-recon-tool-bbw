"""
Google Dorking Modul — Erweiterte OSINT-Suchanfragen v2.1.

Erzeugt Google-Dork-Queries mit Advanced Search Operators (site:, inurl:)
und parst die Ergebnisse mit BeautifulSoup. Automatischer DuckDuckGo-
Fallback bei Google-Rate-Limiting (HTTP 429).

Ethische Leitplanken:
- Jeder Request respektiert Rate-Limits.
- Proxy-Rotation verteilt die Last.
- Keine automatisierten Massen-Scans.

Autor: Rayquaza
Datum: 2026-06-29
"""

import logging
import random
import time
import urllib.parse
from typing import Optional
from urllib.parse import quote, urlparse

import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from rich.console import Console

from config.settings import get_settings

logger = logging.getLogger(__name__)
console = Console()

ETHIK_HINWEIS = (
    "# Ethische Nutzung: Nur für eigene Profile und autorisierte "
    "Sicherheitsaudits. Rate-Limits respektieren."
)

_CAPTCHA_PATTERNS: tuple[str, ...] = (
    "unusual traffic", "our systems have detected unusual traffic",
    "captcha", "recaptcha", "g-recaptcha", "i'm not a robot",
)

_SOCIAL_MEDIA_DOMAINS: frozenset[str] = frozenset({
    "github.com", "instagram.com", "youtube.com", "snapchat.com",
    "pinterest.com", "twitter.com", "x.com", "reddit.com",
    "tiktok.com", "linkedin.com", "twitch.tv",
})


class RateLimitException(Exception):
    """Wird geworfen, wenn Google mit HTTP 429 antwortet."""
    pass


class GoogleDorker:
    """Google-Dorking-Engine mit automatischem DuckDuckGo-Fallback."""

    def __init__(self, proxy_list: Optional[list[str]] = None) -> None:
        self.settings = get_settings()
        self.proxies: list[str] = proxy_list or []
        self.proxy_index: int = 0
        self.ua = UserAgent(browsers=["chrome", "firefox", "edge"], os=["windows", "macos"], min_version=110.0)
        self.session = self._build_session()
        self._rate_limited = False
        logger.info("GoogleDorker initialisiert. Proxies: %d, Timeout: %ds", len(self.proxies), self.settings.request_timeout)

    def dork(self, username: str, keywords: list[str], platforms: list[dict]) -> list[dict]:
        """Google-Dorking mit automatischem DuckDuckGo-Fallback bei Rate-Limiting."""
        if not platforms:
            return []

        results: list[dict] = []
        total = len(platforms)
        console.print(f"\n[bold cyan]🕵️ Google Dorking für [yellow]{username}[/yellow] auf {total} Plattform(en)...[/]\n")

        for idx, platform in enumerate(platforms, start=1):
            if self._rate_limited:
                break  # Google blockt – abbruch, Fallback übernimmt

            domain = urlparse(platform["base_url"]).netloc
            dork_template = platform.get("dork_template", 'site:{domain} "{username}"')
            dork_query = dork_template.format(username=username)
            if keywords:
                dork_query = f'{dork_query} {" ".join(keywords)}'

            console.print(f"  [{idx}/{total}] [cyan]{platform['name']}[/cyan] → [dim]{dork_query[:80]}{'...' if len(dork_query)>80 else ''}[/dim]")

            try:
                page_results = self._search_google(dork_query, domain)
                for r in page_results:
                    r["platform"] = platform["name"]
                    r["query"] = dork_query
                results.extend(page_results)
                console.print(f"    [green]✓ {len(page_results)} Treffer[/]" if page_results else "    [dim]Keine Treffer[/]")
            except RateLimitException:
                self._rate_limited = True
                console.print(f"    [yellow]⚠ HTTP 429 – Google rate-limited[/]")
                break
            except Exception as exc:
                logger.warning("Google-Dork-Fehler für %s: %s", platform["name"], exc)
                console.print(f"    [yellow]⚠ {exc}[/]")

            if idx < total:
                time.sleep(self.settings.rate_limit_delay + random.uniform(0.5, 2.0))

        # Automatischer DuckDuckGo-Fallback wenn Google blockt
        if self._rate_limited:
            console.print("\n[yellow]⚠ Google rate-limited → aktiviere DuckDuckGo-Fallback...[/]")
            try:
                ddg_results = self.duckduckgo_fallback(username, keywords)
                console.print(f"  [green]✓ DuckDuckGo-Fallback: {len(ddg_results)} Treffer[/]")
                results.extend(ddg_results)
            except Exception as exc:
                logger.exception("DDG-Fallback fehlgeschlagen: %s", exc)
                console.print(f"  [red]✗ DuckDuckGo-Fallback fehlgeschlagen: {exc}[/]")

        console.print(f"\n[bold]Dorking abgeschlossen:[/] [green]{len(results)} URLs[/] gefunden\n")
        return results

    def duckduckgo_fallback(self, username: str, keywords: list[str]) -> list[dict]:
        """DuckDuckGo-Fallback-Suche."""
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            logger.error("duckduckgo-search nicht installiert.")
            return []

        query_parts = [f'"{username}"']
        if keywords:
            query_parts.extend(keywords)
        query = " ".join(query_parts)

        console.print(f"  🦆 DuckDuckGo: [dim]{query}[/]")
        results: list[dict] = []

        try:
            from duckduckgo_search.exceptions import RatelimitException as DDGRateLimit
        except ImportError:
            DDGRateLimit = Exception

        try:
            with DDGS() as ddgs:
                for sr in ddgs.text(query, max_results=20):
                    href = sr.get("href", "")
                    if not href:
                        continue
                    domain = urlparse(href).netloc.lower()
                    for sm_domain in _SOCIAL_MEDIA_DOMAINS:
                        if domain == sm_domain or domain.endswith("." + sm_domain):
                            results.append({
                                "url": href,
                                "platform": self._domain_to_platform(domain),
                                "source": "duckduckgo_fallback",
                                "confidence": 0.6,
                                "query": query,
                                "snippet": sr.get("body", ""),
                            })
                            break
        except DDGRateLimit:
            logger.warning("DuckDuckGo rate-limited – keine Ergebnisse.")
        except Exception as exc:
            logger.exception("DDG-Fehler: %s", exc)

        return results

    def _search_google(self, query: str, domain_filter: str) -> list[dict]:
        encoded_query = quote(query)
        url = f"https://www.google.com/search?q={encoded_query}&num=20&hl=en"
        headers = self._get_headers()
        proxies = self._rotate_proxy()
        response = self.session.get(url, headers=headers, proxies=proxies, timeout=self.settings.request_timeout)
        if response.status_code == 429:
            raise RateLimitException("Google rate-limited (HTTP 429)")
        if not response.ok:
            return []
        if self._detect_captcha(response.text):
            raise RateLimitException("Google CAPTCHA – wie HTTP 429 behandelt")
        return self._parse_google_results(response.text, domain_filter)

    def _parse_google_results(self, html: str, domain_filter: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        results: list[dict] = []
        for a_tag in soup.find_all("a", href=True):
            href = a_tag.get("href", "")
            if not href.startswith(("http", "/url?")):
                continue
            if href.startswith("/url?"):
                parsed = urllib.parse.urlparse(href)
                qp = urllib.parse.parse_qs(parsed.query)
                href = qp.get("q", [None])[0]
                if not href:
                    continue
            if domain_filter not in urlparse(href).netloc:
                continue
            if any(r["url"] == href for r in results):
                continue
            results.append({"url": href, "source": "google_dork", "confidence": 0.7, "snippet": ""})
        return results

    def _detect_captcha(self, html: str) -> bool:
        html_lower = html.lower()
        return any(p in html_lower for p in _CAPTCHA_PATTERNS)

    def _rotate_proxy(self) -> Optional[dict]:
        if not self.proxies:
            return None
        proxy_url = self.proxies[self.proxy_index % len(self.proxies)]
        self.proxy_index += 1
        return {"http": proxy_url, "https": proxy_url}

    def _get_headers(self) -> dict:
        return {
            "User-Agent": self.ua.random,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": random.choice(["en-US,en;q=0.9", "de-DE,de;q=0.9,en-US;q=0.8"]),
            "Accept-Encoding": "gzip, deflate",
            "DNT": "1",
        }

    def _build_session(self) -> requests.Session:
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        session = requests.Session()
        retry_strategy = Retry(total=self.settings.max_retries, backoff_factor=1.0, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"], raise_on_status=False)
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10, max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    @staticmethod
    def _domain_to_platform(domain: str) -> str:
        domain = domain.lower().removeprefix("www.")
        mapping = {"github.com":"GitHub","instagram.com":"Instagram","youtube.com":"YouTube","snapchat.com":"Snapchat","pinterest.com":"Pinterest","twitter.com":"Twitter / X","x.com":"Twitter / X","reddit.com":"Reddit","tiktok.com":"TikTok","linkedin.com":"LinkedIn","twitch.tv":"Twitch"}
        return mapping.get(domain, "unknown")
