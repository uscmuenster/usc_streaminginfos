# usc_kommentatoren

Werkzeuge zum automatisierten Einsammeln von Informationen rund um die 1. Volleyball-Bundesliga der Frauen. Die Sammlung umfasst Tabellenstände, Spielpläne sowie aktuelle Berichte von der VBL-Webseite und den Homepages der Vereine. Die Datenbereitstellung nutzt die offizielle REST-API der Volleyball Bundesliga (SAMS) sowie frei zugängliche RSS-Feeds.

## Voraussetzungen

* Python 3.12 oder neuer
* Ein gültiger API-Schlüssel für die VBL-REST-API (`X-Api-Key`). Der Schlüssel kann bei der Volleyball Bundesliga angefragt werden.

Installiere die benötigten Bibliotheken mit:

```bash
pip install -r requirements.txt
```

## Konfiguration

Alle Einstellungen werden über eine YAML-Datei vorgenommen. Die Datei `sample_config.yml` dient als Vorlage und enthält folgende Werte:

```yaml
api:
  api_key: "DEIN_API_KEY"
  league_uuid: "UUID_DER_LIGA"
  team_uuid: "UUID_DES_TEAMS"
  season_uuid: "UUID_DER_SAISON"  # optional
news_sources:
  - name: "Volleyball Bundesliga News"
    type: rss
    url: "https://www.volleyball-bundesliga.de/rss/articleFeed.xhtml?categoryIds=..."
    limit: 10
  - name: "USC Münster"
    type: rss
    url: "https://usc-muenster.de/feed/"
    limit: 10
```

### League- und Team-UUIDs ermitteln

Mit einem gültigen API-Schlüssel lassen sich die benötigten Kennungen über die REST-API abfragen:

1. **Ligastruktur auflisten**
   ```bash
   curl -H "X-Api-Key: $SAMS_API_KEY" "https://www.volleyball-bundesliga.de/api/v2/leagues?page=0&size=100" | jq '.content[] | {name, uuid}'
   ```
2. **Team nach Namen suchen**
   ```bash
   curl -H "X-Api-Key: $SAMS_API_KEY" "https://www.volleyball-bundesliga.de/api/v2/teams?page=0&size=100" | jq '.content[] | select(.name=="USC Münster") | {name, uuid}'
   ```

Notiere die gefundenen UUIDs in der Konfigurationsdatei.

## Nutzung

Der CLI-Einstieg befindet sich im Modul `usc_kommentatoren.cli`. Ein typischer Aufruf lautet:

```bash
PYTHONPATH=src python -m usc_kommentatoren.cli --config config.yml --format markdown --limit 15 --next-games 5
```

Der Parameter `--format` akzeptiert `markdown`, `json` oder `html`. Mit `--output` kann die Ausgabe direkt in eine Datei
geschrieben werden. Ein Beispiel für einen HTML-Bericht lautet:

```bash
PYTHONPATH=src python -m usc_kommentatoren.cli \
  --config config.yml \
  --format html \
  --limit 15 \
  --next-games 5 \
  --output reports/usc-report.html
```

Der Befehl erzeugt wahlweise Markdown-, HTML- oder JSON-Ausgaben mit:

* **Tabellenstand** der 1. Bundesliga Frauen
* **Aktuelle Spielpläne** (Limit konfigurierbar)
* **Kommende Spiele des USC Münster**
* **Artikelübersicht** aggregiert aus allen konfigurierten Quellen

Bei fehlendem API-Schlüssel werden Tabellen- und Spielplandaten übersprungen, die News-Sammlung funktioniert unabhängig davon.

## Automatisierte HTML-Erstellung via GitHub Actions

Das Repository enthält einen Workflow `.github/workflows/ci.yml`, der bei jedem Push, Pull Request **und einmal täglich**
(`cron: "0 5 * * *"`, UTC) ausgeführt wird. Neben Kompilierungs- und Smoketests erzeugt der Workflow einen HTML-Bericht auf
Basis der Beispielkonfiguration und stellt ihn als Build-Artefakt zur Verfügung. Du findest den Download nach jedem Lauf im
Bereich "Actions" des GitHub-Repositories.

## Erweiterungsideen

* Zusätzliche News-Feeds für weitere Vereine ergänzen
* Automatisierte Speicherung der Ergebnisse in einer Datenbank
