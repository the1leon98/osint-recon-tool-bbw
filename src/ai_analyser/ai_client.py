"""
KI-Client — Defensive OpenAI-Integration mit JSON-Validierung.

Abstrahiert OpenAI-kompatible API-Calls mit mehreren
Sicherheitsschichten gegen unzuverlässige LLM-Antworten:

1. response_format={"type": "json_object"} → erzwingt JSON-Modus
2. json.loads() → parst die Response, fängt Malformed-JSON
3. Schema-Validierung → prüft risk_score 0-100, attack_surface-Liste
4. Retry-Logik → 3 Versuche bei Parse/Schema-Fehlern
5. Fallback → deterministische Default-Antwort wenn API nicht erreichbar

Design-Prinzip: "Trust but verify". Selbst wenn OpenAI JSON-Modus
garantiert, validieren wir jede Antwort — LLMs können trotzdem
halluzinieren oder unerwartete Strukturen liefern.

Autor: Rayquaza
Datum: 2026-06-29
"""

import json
import logging
import time
from typing import Any

from openai import APIError, OpenAI, RateLimitError
from rich.console import Console

from config.settings import get_settings
from src.ai_analyser.prompt_templates import SYSTEM_PROMPT

logger = logging.getLogger(__name__)
console = Console()


class AIClient:
    """
    Defensiver OpenAI-Client für OSINT-Risikoanalyse.

    Kapselt die OpenAI-API mit automatischen Retries, JSON-Validierung
    und einem deterministischen Fallback bei Fehlern. Gibt NIEMALS
    Roh-API-Fehler an den Nutzer weiter — jeder Fehler wird geloggt
    und durch eine sinnvolle Fallback-Antwort ersetzt.

    Attributes:
        client: OpenAI-Client-Instanz (mit API-Key aus Settings).
        model: Verwendetes Modell (Default: gpt-4o-mini).
        max_retries: Maximale Wiederholungen (0-basiert, 2 = 3 Versuche).
        settings: Gecachte Settings-Instanz.
    """

    def __init__(self) -> None:
        """
        Initialisiert den OpenAI-Client mit Settings.

        Liest API-Key und Modell aus den Settings (via get_settings()).
        Validiert NICHT den Key — das passiert erst beim ersten API-Call
        (fail-fast bei ungültigem Key, aber kein Pre-Flight-Check).
        """
        self.settings = get_settings()
        # Ollama braucht keinen echten Key, aber der OpenAI-Client
        # verweigert die Verbindung mit leerem String. "ollama" als Dummy.
        api_key = self.settings.openai_api_key or "ollama"
        self.client = OpenAI(
            api_key=api_key,
            base_url=self.settings.llm_base_url,
        )
        self.model: str = self.settings.model_name
        self.max_retries: int = 2  # 3 Versuche insgesamt (0, 1, 2)
        self.console: Console = console

        logger.info(
            "AIClient initialisiert: model=%s, base_url=%s",
            self.model,
            self.settings.llm_base_url,
        )

    # ------------------------------------------------------------------
    # Öffentliche API
    # ------------------------------------------------------------------

    def analyse(self, prompt: str) -> dict[str, Any]:
        """
        Führt eine KI-gestützte Analyse durch und validiert das Ergebnis.

        Sendet den Prompt mit SYSTEM_PROMPT an das LLM, erzwingt JSON-
        Ausgabe, validiert das Ergebnis gegen das erwartete Schema und
        wiederholt bei Fehlern bis zu self.max_retries Mal.

        Args:
            prompt: Der vollständige User-Prompt (aus prompt_templates.py).

        Returns:
            Validiertes Analyse-Dict:
            {
                "risk_score": int,          # 0-100
                "attack_surface": list[str], # Angriffsflächen
                "summary": str,              # Zusammenfassung
            }

            Bei Fehlern: Fallback-Dict mit risk_score=50.
        """
        for attempt in range(self.max_retries + 1):
            attempt_label = f"Versuch {attempt + 1}/{self.max_retries + 1}"
            self.console.print(f"[dim]🤖 KI-Analyse — {attempt_label}...[/]")

            try:
                # === API-Call ===
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.3,  # Niedrig = konsistent, deterministisch
                    max_tokens=500,
                )

                content = response.choices[0].message.content

                # === JSON parsen ===
                if content is None:
                    raise ValueError("Leere API-Antwort (content is None)")

                result = json.loads(content)

                # === Schema-Validierung ===
                self._validate_response(result)

                # === Token-Usage loggen ===
                usage = response.usage
                if usage:
                    logger.debug(
                        "API-Usage: prompt=%d, completion=%d, total=%d",
                        usage.prompt_tokens,
                        usage.completion_tokens,
                        usage.total_tokens,
                    )
                    self.console.print(
                        f"[dim]   ↳ Tokens: {usage.total_tokens} "
                        f"(Prompt: {usage.prompt_tokens}, "
                        f"Completion: {usage.completion_tokens})[/]"
                    )

                self.console.print("[bold green]✓[/] KI-Analyse erfolgreich.")
                return result

            except json.JSONDecodeError as exc:
                # LLM hat kein valides JSON geliefert (trotz json_object-Modus)
                logger.warning("JSON-Parse-Fehler bei Versuch %d: %s", attempt + 1, exc)
                if attempt >= self.max_retries:
                    self.console.print(
                        f"[yellow]⚠[/] KI-Analyse fehlgeschlagen: "
                        f"JSON-Parse-Fehler nach {self.max_retries + 1} "
                        f"Versuchen. Nutze Fallback."
                    )
                    return self._fallback_response()
                self.console.print(
                    f"[dim]   ↳ JSON-Fehler — wiederhole "
                    f"(Versuch {attempt + 2})...[/]"
                )
                time.sleep(1)

            except ValueError as exc:
                # Schema-Validierung fehlgeschlagen
                logger.warning("Schema-Validierungsfehler bei Versuch %d: %s", attempt + 1, exc)
                if attempt >= self.max_retries:
                    self.console.print(
                        f"[yellow]⚠[/] KI-Analyse fehlgeschlagen: "
                        f"Schema-Fehler nach {self.max_retries + 1} "
                        f"Versuchen: {exc}. Nutze Fallback."
                    )
                    return self._fallback_response()
                self.console.print(
                    f"[dim]   ↳ Schema-Fehler ({exc}) — wiederhole "
                    f"(Versuch {attempt + 2})...[/]"
                )
                time.sleep(1)

            except RateLimitError as exc:
                # OpenAI Rate-Limit — exponentielles Backoff
                backoff = 2 ** (attempt + 1)  # 2s, 4s, 8s
                logger.warning("Rate-Limit bei Versuch %d: %s. Backoff %ds.", attempt + 1, exc, backoff)
                if attempt >= self.max_retries:
                    self.console.print(
                        f"[yellow]⚠[/] KI-Analyse fehlgeschlagen: "
                        f"Rate-Limit nach {self.max_retries + 1} "
                        f"Versuchen. Nutze Fallback."
                    )
                    return self._fallback_response()
                self.console.print(
                    f"[yellow]⏳ Rate-Limit — warte {backoff}s "
                    f"(Versuch {attempt + 2})...[/]"
                )
                time.sleep(backoff)

            except APIError as exc:
                # Allgemeiner API-Fehler (Auth, Server, etc.)
                logger.error("API-Fehler bei Versuch %d: %s", attempt + 1, exc)
                if attempt >= self.max_retries:
                    self.console.print(
                        f"[yellow]⚠[/] KI-Analyse fehlgeschlagen: "
                        f"API-Fehler nach {self.max_retries + 1} "
                        f"Versuchen: {exc}. Nutze Fallback."
                    )
                    return self._fallback_response()
                backoff = 2 ** attempt
                time.sleep(backoff)

            except Exception as exc:
                # Unerwarteter Fehler — sofort Fallback
                logger.exception("Unerwarteter Fehler bei KI-Analyse: %s", exc)
                self.console.print(
                    f"[yellow]⚠[/] Unerwarteter Fehler: {exc}. "
                    f"Nutze Fallback."
                )
                return self._fallback_response()

        # Sollte nie erreicht werden (Fallback in jedem except-Zweig),
        # aber defensiv trotzdem hier.
        return self._fallback_response()

    # ------------------------------------------------------------------
    # Interne Methoden
    # ------------------------------------------------------------------

    def _validate_response(self, data: dict[str, Any]) -> bool:
        """
        Validiert das LLM-Antwort-Dict gegen das erwartete Schema.

        Prüfungen:
            1. risk_score muss existieren, numerisch sein (int oder float),
               und im Bereich 0-100 liegen.
            2. attack_surface muss eine Liste von Strings sein.
            3. summary muss ein nicht-leerer String sein.

        Args:
            data: Das aus JSON geparste Antwort-Dict.

        Returns:
            True, wenn alle Prüfungen bestanden wurden.

        Raises:
            ValueError: Mit spezifischer Fehlermeldung, wenn eine
                        Prüfung fehlschlägt.
        """
        # --- risk_score ---
        risk = data.get("risk_score")
        if risk is None:
            raise ValueError("risk_score fehlt in der API-Antwort")

        if not isinstance(risk, (int, float)):
            raise ValueError(
                f"risk_score ist kein numerischer Wert: {type(risk).__name__}"
            )

        # Float in Integer konvertieren, wenn möglich (LLMs liefern oft 72.0 statt 72)
        if isinstance(risk, float):
            if risk == int(risk):
                data["risk_score"] = int(risk)
                risk = int(risk)
            else:
                # Runden auf ganze Zahl
                data["risk_score"] = round(risk)
                risk = round(risk)

        if not (0 <= risk <= 100):
            raise ValueError(
                f"risk_score außerhalb 0-100: {risk}"
            )

        # --- attack_surface ---
        surfaces = data.get("attack_surface")
        if surfaces is None:
            raise ValueError("attack_surface fehlt in der API-Antwort")

        if not isinstance(surfaces, list):
            raise ValueError(
                f"attack_surface ist keine Liste: {type(surfaces).__name__}"
            )

        # Jedes Element muss ein String sein
        for i, item in enumerate(surfaces):
            if not isinstance(item, str):
                raise ValueError(
                    f"attack_surface[{i}] ist kein String: "
                    f"{type(item).__name__} = {item!r}"
                )

        # --- summary ---
        summary = data.get("summary")
        if summary is None:
            raise ValueError("summary fehlt in der API-Antwort")

        if not isinstance(summary, str):
            raise ValueError(
                f"summary ist kein String: {type(summary).__name__}"
            )

        if len(summary.strip()) == 0:
            raise ValueError("summary ist ein leerer String")

        return True

    def _fallback_response(self) -> dict[str, Any]:
        """
        Liefert eine deterministische Fallback-Antwort.

        Wird verwendet, wenn:
        - Die API nicht erreichbar ist
        - Alle Retries fehlgeschlagen sind
        - Das LLM persistent ungültiges JSON liefert

        Returns:
            Dict mit neutralen Default-Werten (risk_score=50 = mittel).
            attack_surface enthält einen Hinweis auf manuelle Prüfung.
        """
        logger.info("Verwende Fallback-Antwort für KI-Analyse.")
        return {
            "risk_score": 50,
            "attack_surface": [
                "KI-Analyse nicht verfügbar — manuelle Prüfung empfohlen",
            ],
            "summary": (
                "Die automatische Analyse konnte nicht durchgeführt werden. "
                "Bitte die gefundenen Profile manuell auf sensible Daten prüfen."
            ),
        }
