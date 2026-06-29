"""
Zentrale Konfiguration mit pydantic-settings.

Lädt Umgebungsvariablen aus .env-Datei und stellt typed settings
mit Validierung, Constraints und dokumentierten Defaults bereit.

Singleton-Pattern via @lru_cache: Settings werden nur einmal beim
ersten Aufruf geladen und danach aus dem Cache bedient. Das verhindert
mehrfaches I/O-Parsing der .env-Datei und garantiert konsistente Werte.

Alle Pfade sind relativ zum Projekt-Root (zweimal parent von dieser Datei:
config/settings.py → config/ → Projekt-Root). Keine hartkodierten Pfade.

Autor: Rayquaza
Datum: 2026-06-29
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Typisierte, selbst-dokumentierende Konfiguration für das OSINT BBW Tool.

    Jedes Feld hat:
      - Einen exakten Typ (str, int, float, bool, Path)
      - Einen Default-Wert oder ... (required)
      - Validierungs-Constraints (ge, le)
      - Eine description für IDE-Intellisense und self-documenting code
    """

    # === Pfade (relativ zum Projekt-Root) ===
    project_root: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parent.parent,
        description="Projekt-Root-Verzeichnis (automatisch ermittelt)",
    )

    output_dir: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parent.parent / "output",
        description="Ausgabeverzeichnis für generierte Reports (HTML und PDF)",
    )

    template_dir: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parent.parent
        / "src"
        / "report_generator"
        / "templates",
        description="Verzeichnis mit Jinja2-HTML-Templates für die Report-Generierung",
    )

    static_dir: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parent.parent
        / "src"
        / "report_generator"
        / "static",
        description="Verzeichnis mit statischen Assets (CSS, JS, Bilder) für Reports",
    )

    # === OpenAI / LLM-Konfiguration ===
    openai_api_key: str = Field(
        default="",
        description="OpenAI API-Key (nur für OpenAI nötig). Bei Ollama LEER lassen.",
    )

    model_name: str = Field(
        default="llama3.2:3b",
        description="LLM-Modell. Ollama (kostenlos): llama3.2:3b, mistral:7b. OpenAI: gpt-4o-mini.",
    )

    llm_base_url: str = Field(
        default="http://localhost:11434/v1",
        description="LLM-API-URL. Ollama: http://localhost:11434/v1 | OpenAI: https://api.openai.com/v1",
    )

    # === HTTP & Netzwerk ===
    request_timeout: int = Field(
        default=10,
        ge=5,
        le=60,
        description="HTTP-Request-Timeout in Sekunden. Minimum 5s (langsame Proxies), Maximum 60s (kein Endlos-Hängen).",
    )

    max_retries: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximale Wiederholungen bei Netzwerkfehlern (5xx, Timeout). Exponentielles Backoff zwischen Retries.",
    )

    rate_limit_delay: float = Field(
        default=2.0,
        ge=0.5,
        le=10.0,
        description="Pause in Sekunden zwischen zwei OSINT-Requests. Verhindert IP-Blocking durch zu schnelle Anfragen.",
    )

    proxy_list: str = Field(
        default="",
        description="Optionale, komma-separierte HTTP-Proxy-Liste für Google-Dorking. Leer lassen für Direktzugriff.",
    )

    # === Logging & Debugging ===
    debug: bool = Field(
        default=False,
        description="Debug-Modus: true = vollständige Stacktraces und Request-Logs. In Produktion IMMER false!",
    )

    log_level: str = Field(
        default="INFO",
        description="Logging-Level: DEBUG | INFO | WARNING | ERROR | CRITICAL. Steuert die Ausführlichkeit der Konsolenausgabe.",
    )

    class Config:
        """
        pydantic-settings Konfiguration.

        - env_file: Pfad zur .env-Datei (relativ zum CWD bei Ausführung).
          Für Produktion: absoluten Pfad setzen oder über ENV_FILE env-var steuern.
        - env_file_encoding: UTF-8 für Umlaute und Sonderzeichen in Werten.
        - case_sensitive: False → OPENAI_API_KEY und openai_api_key sind identisch.
          Erlaubt sowohl Groß- als auch Kleinschreibung in .env-Dateien.
        """

        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        protected_namespaces = ("settings_",)

    def validate_paths(self) -> None:
        """
        Validiert, dass alle konfigurierten Verzeichnisse existieren.

        Erstellt fehlende Verzeichnisse automatisch (output_dir, ggf. Unterordner).
        Wirft FileNotFoundError, wenn template_dir oder static_dir fehlen —
        diese MÜSSEN im Repo vorhanden sein (keine automatische Erstellung).
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if not self.template_dir.exists():
            raise FileNotFoundError(
                f"Template-Verzeichnis nicht gefunden: {self.template_dir}\n"
                f"Bitte Repository-Integrität prüfen — templates/ muss vorhanden sein."
            )
        if not self.static_dir.exists():
            raise FileNotFoundError(
                f"Static-Verzeichnis nicht gefunden: {self.static_dir}\n"
                f"Bitte Repository-Integrität prüfen — static/ muss vorhanden sein."
            )


@lru_cache()
def get_settings() -> Settings:
    """
    Singleton-Factory für die Settings-Klasse.

    Durch @lru_cache wird die Settings-Instanz nur einmal beim ersten
    Aufruf erstellt und danach aus dem Cache zurückgegeben. Das spart
    I/O (kein erneutes .env-Parsing) und garantiert identische Werte
    in allen Modulen.

    Verwendung:
        from config.settings import get_settings
        settings = get_settings()
        print(settings.output_dir)

    Returns:
        Settings: Die einzige, gecachte Settings-Instanz.
    """
    settings = Settings()
    settings.validate_paths()
    return settings
