"""
Rate Limiter — Mathematisch präzises Request-Throttling mit Jitter.

Verhindert IP-Sperren durch kontrollierte Request-Frequenz mit
konfigurierbarer Mindestverzögerung. Der optionale Jitter-Mechanismus
addiert zufälliges Rauschen (±50 % der Mindestverzögerung), um den
Thundering-Herd-Effekt zu vermeiden: Wenn mehrere Instanzen oder Threads
exakt synchron warten, treffen alle Requests gleichzeitig ein und
erzeugen eine Lastspitze. Jitter verteilt sie im Zeitfenster.

Exponentielles Backoff (mit 60s-Cap) für automatische Wiederholungen
bei 429/5xx-Fehlern, konfiguriert über den urllib3-Retry-Adapter.

Nutzung als Context-Manager:
    with RateLimiter(min_delay=2.0) as rl:
        for platform in platforms:
            rl.wait()
            response = rl.get_session().get(url)

Autor: Rayquaza
Datum: 2026-06-29
"""

import logging
import random
import time
from types import TracebackType
from typing import Optional, Type

import requests
from fake_useragent import UserAgent
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config.settings import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Konstante: Default-Cap für exponentielles Backoff
# ---------------------------------------------------------------------------
_MAX_BACKOFF_SECONDS: float = 60.0


class RateLimiter:
    """
    Präzises Request-Throttling mit Jitter und exponentiellen Backoffs.

    Garantiert eine konfigurierbare Mindestpause zwischen Requests,
    zählt Requests mit und unterstützt das Context-Manager-Protokoll.

    Der Jitter-Mechanismus (aktiviert per Default) addiert bis zu
    50 % der Mindestverzögerung als zufälliges Rauschen. Das verhindert,
    dass mehrere Clients im Gleichtakt requests absetzen (Thundering Herd).

    Attributes:
        min_delay: Minimale Sekunden zwischen zwei Requests.
        jitter: Ob zufälliges Rauschen addiert wird.
        last_request: Timestamp des letzten Requests (monotonic).
        request_count: Anzahl der seit init/reset ausgeführten Requests.
    """

    def __init__(
        self,
        min_delay: Optional[float] = None,
        jitter: bool = True,
    ) -> None:
        """
        Initialisiert den RateLimiter.

        Args:
            min_delay: Minimale Pause zwischen Requests in Sekunden.
                       None = Wert aus Settings (rate_limit_delay).
            jitter: True → zufälliges Rauschen (±50 %) auf min_delay addieren.
                    False → exakte min_delay-Pause ohne Variation.
        """
        settings = get_settings()
        self.min_delay: float = min_delay if min_delay is not None else settings.rate_limit_delay
        self.jitter: bool = jitter
        self.last_request: float = 0.0
        self.request_count: int = 0

        logger.debug(
            "RateLimiter: min_delay=%.2fs, jitter=%s",
            self.min_delay,
            self.jitter,
        )

    # ------------------------------------------------------------------
    # Öffentliche API
    # ------------------------------------------------------------------

    def wait(self) -> None:
        """
        Blockiert, bis die Mindestverzögerung seit dem letzten Request
        verstrichen ist.

        Berechnet die Differenz zwischen aktueller Zeit und dem letzten
        Request-Timestamp. Wenn weniger als min_delay vergangen ist,
        wird die Restzeit geschlafen — plus optionalem Jitter.

        Jitter-Formel:
            sleep = (min_delay - elapsed) + random(0, min_delay * 0.5)

        Nach dem Warten werden last_request und request_count aktualisiert.
        """
        now = time.monotonic()
        elapsed = now - self.last_request

        if self.last_request > 0 and elapsed < self.min_delay:
            sleep_time = self.min_delay - elapsed

            if self.jitter:
                # Bis zu 50 % der min_delay als Rauschen addieren.
                # Verhindert Thundering-Herd: Clients wachen nicht synchron auf.
                jitter_amount = random.uniform(0, self.min_delay * 0.5)
                sleep_time += jitter_amount

            logger.debug(
                "Rate-Limit: Warte %.2fs (elapsed=%.2fs, min=%.2fs, jitter=%s)",
                sleep_time, elapsed, self.min_delay, self.jitter,
            )
            time.sleep(sleep_time)

        self.last_request = time.monotonic()
        self.request_count += 1

    def get_session(self) -> requests.Session:
        """
        Erzeugt eine requests.Session mit Retry-Adapter und User-Agent.

        Der Retry-Adapter konfiguriert automatische Wiederholungen bei
        transienten Fehlern (429, 5xx). Backoff-Faktor = 0.5 bedeutet:
        0.5s → 1.0s → 1.5s Wartezeit zwischen Retries.

        Returns:
            requests.Session mit konfiguriertem Retry-Adapter und
            zufälligem User-Agent-Header.
        """
        session = requests.Session()

        retry_strategy = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "HEAD"],
            raise_on_status=False,
        )

        adapter = HTTPAdapter(
            pool_connections=10,
            pool_maxsize=10,
            max_retries=retry_strategy,
        )

        session.mount("https://", adapter)
        session.mount("http://", adapter)

        # Zufälliger User-Agent bei jeder neuen Session
        session.headers.update({
            "User-Agent": UserAgent(
                browsers=["chrome", "firefox"],
                os=["windows", "macos"],
                min_version=100.0,
            ).random,
        })

        return session

    def exponential_backoff(self, attempt: int) -> float:
        """
        Berechnet exponentielle Wartezeit mit Cap bei 60 Sekunden.

        Formel:
            delay = min_delay * (2 ** attempt)
            return min(delay, 60.0)

        Beispiele (min_delay = 2.0):
            attempt 0 → 2.0s
            attempt 1 → 4.0s
            attempt 2 → 8.0s
            attempt 3 → 16.0s
            attempt 4 → 32.0s
            attempt 5 → 60.0s (gecapped)

        Args:
            attempt: Nullbasierter Wiederholungsversuch (0 = erster Retry).

        Returns:
            Wartezeit in Sekunden (maximal 60.0).
        """
        delay = self.min_delay * (2 ** max(attempt, 0))
        capped = min(delay, _MAX_BACKOFF_SECONDS)

        logger.debug(
            "Exponential Backoff: attempt=%d → %.1fs (raw=%.1fs)",
            attempt, capped, delay,
        )
        return capped

    def reset(self) -> None:
        """
        Setzt den Request-Zähler zurück.

        Nützlich für mehrphasige Scans, bei denen die Zählung pro
        Phase separat erfolgen soll. last_request wird NICHT
        zurückgesetzt — das Throttling läuft weiter.
        """
        self.request_count = 0
        logger.debug("RateLimiter: request_count zurückgesetzt.")

    # ------------------------------------------------------------------
    # Context-Manager-Protokoll (with RateLimiter() as rl: ...)
    # ------------------------------------------------------------------

    def __enter__(self) -> "RateLimiter":
        """
        Enter Context-Manager.

        Returns:
            self — die RateLimiter-Instanz.
        """
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        """
        Exit Context-Manager.

        Führt kein Cleanup durch (keine offenen Ressourcen).
        Exception-Propagation wird nicht unterdrückt (return None).
        """
        pass
