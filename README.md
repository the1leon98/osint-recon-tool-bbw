# 🕵️ OSINT Recon Tool – ShadowPhantom

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![Status](https://img.shields.io/badge/Status-Alpha-orange)
![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey)

> **Automatisierte OSINT-Recherche** mit Sherlock-Profilprüfung, Google-Dorking-Bypass und KI-Risikoanalyse. Generiert eine **druckbare Sicherheits-Karteikarte** als HTML/PDF.

---

## ✨ Features

| Feature | Beschreibung |
|---|---|
| 🔍 **Sherlock-Scanner** | Prüft 10 Social-Media-Plattformen auf Profil-Existenz via HTTP-Statuscodes & Redirect-Analyse |
| 🕵️ **Google-Dorking** | Erweiterte `site:`-Suchanfragen mit Proxy-Rotation & CAPTCHA-Erkennung |
| 🦆 **DuckDuckGo-Fallback** | Automatisch, wenn Google blockiert — nutzt die offizielle DDG-API |
| 🤖 **KI-Risikoanalyse** | GPT-4o-mini bewertet Angriffsflächen, erstellt Risk-Score (0–100) & Zusammenfassung |
| 📊 **SVG-Diagramme** | Animierte Donut-Charts (Vanilla JS, keine Abhängigkeiten) |
| 📄 **HTML-Report** | Selbsttragend — alle Bilder Base64-eingebettet, Dark-Mode, Responsive |
| 🖨️ **DIN-A4-Druck** | Optimiertes Print-CSS: Exakt eine Seite, `print-color-adjust: exact` |
| 🎨 **Rich-CLI** | Fortschrittsbalken, farbige Scores, Spinner — professionelles Terminal-UI |

---

## 📦 Installation

```bash
# Repository klonen
git clone https://github.com/the1leon98/osint-recon-tool-bbw.git
cd osint-recon-tool

# Virtuelle Umgebung erstellen & aktivieren
python -m venv venv
source venv/bin/activate        # Linux/macOS
# venv\Scripts\activate         # Windows

# Abhängigkeiten installieren
pip install -r requirements.txt

# Umgebungsvariablen konfigurieren
cp .env.example .env
# → .env mit EDITOR öffnen und OPENAI_API_KEY eintragen
```

### Systemabhängigkeiten (nur für PDF-Export)

```bash
# macOS
brew install pango cairo gdk-pixbuf libffi

# Linux (Debian/Ubuntu)
sudo apt install libpango-1.0-0 libcairo2 libgdk-pixbuf2.0-0 libffi-dev
```

---

## 🚀 Schnellstart

```bash
# Einfacher Scan (nur Sherlock)
python main.py max_mustermann

# Scan mit Google-Dorking + Keywords
python main.py max_mustermann --keywords "Max Mustermann" Berlin

# Nur bestimmte Plattformen
python main.py max_mustermann --platforms github,linkedin,reddit

# Ohne KI-Analyse (spart API-Kosten)
python main.py max_mustermann --no-ai

# Mit Debug-Ausgabe
python main.py max_mustermann --verbose

# Benutzerdefinierter Ausgabepfad
python main.py max_mustermann --output reports/mein_report.html
```

**Ausgabe:**
```
🕵️  OSINT Recon Tool v0.1.0

🎯 Ziel: max_mustermann

🔍 Phase 1/4: Sherlock-Scan...
  ✓ 7 Profile gefunden

🕵️ Phase 2/4: Google-Dorking...
  ✓ 12 URLs via Dorking gefunden

📊 Phase 3/4: Aggregation...
  ✓ 9 eindeutige Profile auf 4 Plattformen

🤖 Phase 4/4: KI-Analyse & Report...
  ✓ Report erstellt: output/report_max_mustermann_20260629_143000.html
  Risiko-Score: 58% — HOCH

✅ Fertig. 🕵️
```

---

## 📁 Projektstruktur

```
OSINT-TOOL-BBW/
├── main.py                  # Einstiegspunkt (4-Phasen-Pipeline)
├── requirements.txt         # Exakt gepinnte Abhängigkeiten
├── .env.example             # Vorlage für Umgebungsvariablen
├── config/
│   ├── settings.py          # Pydantic-Settings (Singleton)
│   └── platforms.json       # 10 Plattform-Konfigurationen
├── src/
│   ├── cli/
│   │   └── input_handler.py # Argparse + Input-Validierung
│   ├── osint_engine/
│   │   ├── sherlock_scanner.py   # HTTP-Profilprüfung
│   │   ├── google_dorker.py      # Google- & DuckDuckGo-Suche
│   │   ├── rate_limiter.py       # Jitter + exponentielles Backoff
│   │   └── result_aggregator.py  # Merge & Deduplizierung
│   ├── ai_analyser/
│   │   ├── prompt_templates.py   # LLM-Prompts (JSON-Only)
│   │   ├── ai_client.py          # OpenAI-Client (defensiv)
│   │   └── risk_calculator.py    # Hybrider Risk-Score
│   └── report_generator/
│       ├── html_renderer.py      # Jinja2-Template-Rendering
│       ├── pdf_exporter.py       # WeasyPrint PDF-Export
│       ├── static/               # CSS, JS, Bilder
│       └── templates/            # Jinja2-Templates + Partials
└── output/                  # Generierte HTML/PDF-Reports
```

---

## ⚙️ Konfiguration

Alle Einstellungen in `.env` (aus `.env.example` kopieren):

| Variable | Default | Beschreibung |
|---|---|---|
| `OPENAI_API_KEY` | *(Pflicht)* | API-Key von [platform.openai.com](https://platform.openai.com/api-keys) |
| `LLM_MODEL` | `gpt-4o-mini` | OpenAI-Modell (gpt-4o, gpt-3.5-turbo) |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | Für Azure/Lokale LLMs anpassen |
| `REQUEST_TIMEOUT` | `30` | HTTP-Timeout in Sekunden |
| `MAX_RETRIES` | `3` | Wiederholungen bei Netzwerkfehlern |
| `PROXY_LIST` | *(leer)* | Komma-separierte HTTP-Proxies |
| `DEBUG` | `false` | `true` = Stacktraces (nie in Produktion!) |
| `LOG_LEVEL` | `INFO` | DEBUG / INFO / WARNING / ERROR |

---

## 📊 Unterstützte Plattformen

| Plattform | Gewicht | URL-Struktur |
|---|---|---|
| LinkedIn | 1.6 | `linkedin.com/in/{username}` |
| GitHub | 1.5 | `github.com/{username}` |
| Reddit | 1.4 | `reddit.com/user/{username}` |
| Twitter / X | 1.3 | `twitter.com/{username}` |
| Instagram | 1.2 | `instagram.com/{username}` |
| TikTok | 1.0 | `tiktok.com/@{username}` |
| Snapchat | 0.9 | `snapchat.com/add/{username}` |
| YouTube | 0.8 | `youtube.com/@{username}` |
| Twitch | 0.8 | `twitch.tv/{username}` |
| Pinterest | 0.7 | `pinterest.com/{username}` |

> **Gewicht** = Sensitivität der Plattform (höher = mehr personenbezogene Daten).

---

## 🛡️ Ethische Richtlinie

**Dieses Tool darf NUR verwendet werden für:**

- ✅ Sicherheitsaudits des **eigenen** digitalen Fußabdrucks
- ✅ Autorisierte Penetrationstests mit **schriftlicher Genehmigung**
- ✅ Recherche zu **öffentlich zugänglichen** Informationen im legalen Rahmen
- ✅ Bildungszwecke & Security-Awareness-Training

**Dieses Tool darf NICHT verwendet werden für:**

- ❌ Stalking, Belästigung oder Einschüchterung
- ❌ Identitätsdiebstahl oder Social-Engineering-Angriffe
- ❌ Unbefugtes Ausspähen Dritter (verstößt gegen DSGVO & StGB §202a)
- ❌ Automatisierte Massen-Scans ohne Rate-Limits

> **Merksatz:** Nur weil Information öffentlich ist, heißt das nicht, dass ihre
> systematische Sammlung legal oder ethisch ist. Nutze dieses Tool verantwortungsvoll.

---

## 📄 Lizenz

MIT License — siehe [LICENSE](LICENSE)-Datei.

Copyright (c) 2026 rayquaza

---

## 👤 Autor

**rayquaza** — OSINT-Security-Researcher

- Projekt: `github.com/the1leon98/osint-recon-tool`
- Erstellt: 2026-06-29
- Python 3.11+ · OpenAI GPT-4o-mini · Vanilla JS SVG-Charts

---

*„Wissen ist Macht — aber mit großer Macht kommt große Verantwortung.“* 🕵️
