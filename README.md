# USC Streaminginfos

Dieses Repository erzeugt täglich eine schlanke HTML-Seite zum Frauen-Bundesligateam des USC Münster und stellt zusätzliche Datensichten für Streams oder Social-Media-Betreuung bereit. Alle Informationen werden aus frei zugänglichen Quellen geladen – der Spielplan kommt aus dem öffentlichen CSV-Export der Volleyball Bundesliga, News werden von den Vereinsseiten sowie den VBL-Portalen geholt und internationale Partien direkt von der CEV aggregiert.

## Funktionsumfang

### Spieltagsbericht (`docs/index.html` / `docs/index_app.html`)

Der Kern des Projekts ist der automatisch erzeugte Spieltagsbericht. Er liefert alle relevanten Informationen zum nächsten USC-Heimspiel in einem responsiven Layout (inklusive App-optimierter Variante mit skalierter Schrift). Enthalten sind unter anderem:

* Überschrift mit dem nächsten Heimgegner des USC Münster inklusive Datum, Uhrzeit und Austragungsort.
* Verlinkungen auf die offiziellen Vereinsseiten, die Tabellenübersicht der Volleyball Bundesliga sowie veröffentlichte Spielinfos/Statistiken der VBL, sobald verfügbar. 【F:src/usc_kommentatoren/report.py†L2336-L2388】【F:src/usc_kommentatoren/report.py†L1893-L1900】
* Die letzten Ergebnisse und das jeweils nächste Spiel sowohl des USC als auch des kommenden Gegners – inklusive Satzergebnisse, Ballpunkte, MVP-Ehrungen, Schiedsrichter*innen und Zuschauerzahlen, sofern die VBL diese Daten liefert. 【F:src/usc_kommentatoren/report.py†L1850-L1905】【F:src/usc_kommentatoren/report.py†L2331-L2344】【F:src/usc_kommentatoren/__main__.py†L73-L213】
* Geburtstags-Hinweise für Spielerinnen in einem sieben­tägigen Fenster rund um den Spieltag. 【F:src/usc_kommentatoren/report.py†L2052-L2128】
* Aufklappbare Kaderübersichten beider Teams mit inline eingebundenem Mannschaftsfoto, Positions- und Größenangaben sowie separaten Blöcken für Trainer*innen/Staff. 【F:src/usc_kommentatoren/report.py†L2294-L2330】
* Wechselbörse-Sektionen je Team, die Zu- und Abgänge aus der offiziellen VBL-Wechselbörse sammeln. 【F:src/usc_kommentatoren/report.py†L2279-L2330】【F:src/usc_kommentatoren/report.py†L1736-L1848】
* News-, Instagram- und Saisonrückblick-Abschnitte, die aktuelle Artikel, Social-Media-Links und optional externe Saisonzusammenfassungen bündeln. 【F:src/usc_kommentatoren/report.py†L1945-L2068】【F:src/usc_kommentatoren/report.py†L2134-L2245】
* Einen eigenen Bereich „Sendeablauf“, der für Streams die geplanten Programmpunkte mit Countdown, Uhrzeit und Dauer als kompakte Tabelle aufbereitet. 【F:src/usc_kommentatoren/report.py†L3536-L3579】

Die App-Ansicht wird automatisch erzeugt (Schriftfaktor standardmäßig 0,75), kann aber über die CLI-Optionen skaliert oder deaktiviert werden.

### Aufstellungs-Datensatz (`docs/data/aufstellungen.json`)

Das Skript `scripts/update_lineups.py` lädt PDF-Spielberichtsbögen des USC sowie der jüngsten Partien des nächsten Gegners, extrahiert Startaufstellungen je Satz und schreibt alles als JSON. Der Datensatz enthält pro Spiel:

* Metadaten (Matchnummer, Datum, Wettbewerb, Spielort) aus dem offiziellen Spielplan. 【F:scripts/update_lineups.py†L33-L58】【F:src/usc_kommentatoren/lineups.py†L24-L121】
* Verlinkungen zu den Original-PDFs sowie die Positionscodes der VBL. 【F:src/usc_kommentatoren/lineups.py†L640-L706】
* Startsechs, Satzstände und zugehörige Kaderinformationen zur schnellen Wiederverwendung in Streams oder Social Posts. 【F:src/usc_kommentatoren/lineups.py†L744-L825】

Aufrufbeispiel:

```bash
python scripts/update_lineups.py --limit 3
```

Die PDFs werden standardmäßig unter `data/lineups/` gecacht, Kaderexporte in `data/rosters/` gespeichert und das JSON nach `docs/data/aufstellungen.json` geschrieben.

### Internationale Spiele (`docs/internationale_spiele.html`)

Mit `scripts/update_international_matches.py` aggregierst du Champions-League-, Cup- und Challenge-Cup-Partien deutscher Teams direkt von der CEV. Das Ergebnis ist eine eigenständige HTML-Seite mit:

* Wettbewerbsübersichten inklusive Quellenlink zur jeweiligen CEV-Landingpage.
* Auflistungen kommender und abgeschlossener Spiele pro Team, inklusive Terminangaben, Austragungsort, Match-Centre-Links und Satzergebnissen. 【F:scripts/update_international_matches.py†L91-L226】【F:scripts/update_international_matches.py†L228-L324】

Standardmäßig landet die Datei unter `docs/internationale_spiele.html` und kann ebenso über GitHub Pages bereitgestellt werden.

## Projektstruktur

Zur Orientierung findest du hier die wichtigsten Verzeichnisse des Projekts im Überblick:

* `src/usc_kommentatoren/`: Python-Paket mit dem CLI-Einstiegspunkt, der Spielplan, News, Kader und Statistiken zusammenzieht und den HTML-Bericht rendert.【F:src/usc_kommentatoren/__main__.py†L1-L129】【F:src/usc_kommentatoren/report.py†L3290-L3342】
* `scripts/`: Hilfsprogramme für wiederkehrende Aufgaben wie die Aktualisierung des Lineup-Datensatzes oder das Sammeln internationaler Spiele.【F:scripts/update_lineups.py†L1-L78】【F:scripts/update_international_matches.py†L1-L64】
* `docs/`: Ausgabeordner für generierte HTML-Seiten, JSON-Datensätze und ergänzende Dokumentation rund um die Datenpipelines.【F:docs/lineups_workflow.md†L1-L37】
* `.github/workflows/`: Automatisierte GitHub-Actions, die Berichte und Datensätze regelmäßig erzeugen und veröffentlichen.【F:.github/workflows/update-lineups.yml†L1-L34】

## Voraussetzungen

* Python 3.12 oder neuer
* Abhängigkeiten installieren mit `pip install -r requirements.txt`

## Schnelleinstieg für die lokale Entwicklung

1. Erstelle dir am besten eine virtuelle Umgebung, um alle Abhängigkeiten vom System zu trennen:

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
   ```

2. Installiere anschließend die benötigten Pakete:

   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. Für einmalige Testläufe kannst du die wichtigsten Skripte direkt über `PYTHONPATH=src` aufrufen. Häufige Beispiele:

   ```bash
   PYTHONPATH=src python -m usc_kommentatoren --help
   PYTHONPATH=src python scripts/update_lineups.py --limit 1
   ```

4. Wenn du Änderungen am Code testen möchtest, lösche bei Bedarf die Cache-Verzeichnisse in `data/` oder starte die Skripte mit geänderten `--schedule-path`- bzw. `--roster-dir`-Argumenten, damit neue Daten geladen werden.

5. Für ein tägliches Update kannst du den bestehenden GitHub-Action-Workflow lokal simulieren, indem du `scripts/`-Befehle hintereinander ausführst oder `python -m usc_kommentatoren` in einem Cronjob einplanst.

## Manuelle Ausführung

Das Paket stellt einen kleinen Helfer bereit, der den offiziellen Spielplan lädt, aktuelle Vereins- und VBL-Meldungen sammelt und die HTML-Dateien erzeugt. Standardmäßig schreibt der Befehl sowohl `docs/index.html` (normale Ansicht) als auch `docs/index_app.html` (Schriftgrößen ca. 75 % für die App-Einbindung), damit beide Varianten direkt von GitHub Pages oder einem anderen statischen Hoster ausgeliefert werden können. Beispiel:

```bash
PYTHONPATH=src python -m usc_kommentatoren
```

Beim ersten Aufruf (und bei jeder späteren Aktualisierung) lädt das Skript den CSV-Spielplan herunter und speichert ihn unter `data/schedule.csv`. Wenn bereits eine lokale Kopie existiert, wird sie überschrieben. Der Pfad kann mit `--schedule-path` angepasst werden. Zusätzlich lädt der Generator die offiziellen Teamkader als CSV-Export in `data/rosters/`, cacht Mannschaftsfotos im Verzeichnis `data/team_photos/`, ergänzt Saisonstatistiken aus `docs/data/season_results_2024_25.json` und wertet die Wechselbörse aus. Über `--app-output`, `--app-scale` und `--skip-app-output` steuerst du bei Bedarf, wohin die App-Variante geschrieben wird, wie stark die Schrift verkleinert werden soll oder ob sie komplett entfallen darf. Optional kannst du außerdem Zielpfad, Quelle, Anzahl der vergangenen Partien sowie den News-Zeitraum ändern:

```bash
PYTHONPATH=src python -m usc_kommentatoren \
  --schedule-url "https://www.volleyball-bundesliga.de/servlet/league/PlayingScheduleCsvExport?matchSeriesId=776311171" \
  --schedule-path data/custom_schedule.csv \
  --roster-dir data/kader \
  --photo-dir data/teamfotos \
  --recent-limit 3 \
  --news-lookback 10 \
  --output docs/custom_report.html \
  --app-output docs/custom_app.html \
  --app-scale 0.7 \
  --season-results docs/data/season_results_2024_25.json
```

### CLI-Optionen im Überblick

* `--schedule-url`: CSV-Quelle des Spielplans (Standard: offizieller VBL-Export). 【F:src/usc_kommentatoren/__main__.py†L34-L41】
* `--schedule-path`: Lokale Datei für den Spielplan-Cache (`data/schedule.csv`). 【F:src/usc_kommentatoren/__main__.py†L52-L58】
* `--roster-dir`, `--photo-dir`: Zwischenspeicher für Kaderexporte und Teamfotos (Standard: `data/rosters/`, `data/team_photos/`). 【F:src/usc_kommentatoren/__main__.py†L59-L77】
* `--season-results`: Optionaler JSON-Pfad für Saisonrückblicke. 【F:src/usc_kommentatoren/__main__.py†L78-L115】【F:src/usc_kommentatoren/report.py†L2134-L2245】
* `--recent-limit`, `--news-lookback`: Anzahl berücksichtigter Spiele und News-Tage. 【F:src/usc_kommentatoren/__main__.py†L88-L103】
* `--app-output`, `--app-scale`, `--skip-app-output`: Steuerung der App-optimierten HTML-Version. 【F:src/usc_kommentatoren/__main__.py†L42-L51】【F:src/usc_kommentatoren/__main__.py†L216-L233】

Weitere Optionen lassen sich über `PYTHONPATH=src python -m usc_kommentatoren --help` einsehen.

## Datenablage & Cache-Verzeichnisse

* `data/schedule.csv`: aktueller Spielplan-Export der VBL.
* `data/rosters/`: CSV-Kaderexporte der Teams (werden bei Bedarf aktualisiert).
* `data/team_photos/`: lokal eingebettete Teamfotos zur schnelleren Auslieferung.
* `data/lineups/`: gespeicherte PDF-Spielberichtsbögen für den Aufstellungs-Datensatz.

Alle Pfade lassen sich über die jeweiligen CLI-Argumente anpassen.

## Troubleshooting & Tipps für die tägliche Nutzung

* **Leere oder unvollständige Datenblöcke?** Starte das Skript mit `--recent-limit` beziehungsweise `--news-lookback`, um testweise mehr Partien oder einen längeren News-Zeitraum einzubeziehen. So lässt sich schnell prüfen, ob wirklich keine Inhalte vorhanden sind oder ob Filter greifen.
* **Fehlerhafte CSV-Quellen?** Mit `--schedule-path` kannst du einen lokal geprüften Spielplan einlesen, bevor du den offiziellen VBL-Export wieder aktivierst. Gerade vor Saisonstart ändern sich URLs erfahrungsgemäß häufiger.
* **Langsame Aktualisierungen?** Lösche bei Bedarf die Caches unter `data/` oder lege alternative Verzeichnisse via `--roster-dir`, `--photo-dir` und `--season-results` fest. Der Generator lädt fehlende Dateien automatisch nach, sobald der Cache leer ist.
* **App-Ansicht testen:** Nutze `--skip-app-output`, wenn du dich auf die Desktop-Variante konzentrieren möchtest. Umgekehrt erzwingt eine Kombination aus `--app-output` und `--app-scale`, dass nur die mobile Fassung regeneriert wird.
* **Log-Ausgaben beobachten:** Führe das Modul mit `PYTHONPATH=src python -m usc_kommentatoren` direkt im Terminal aus, um HTTP-Anfragen und Cache-Hinweise unmittelbar zu sehen. Kombiniert mit `--help` erkennst du außerdem schnell, welche Optionen für eine manuelle Fehleranalyse zur Verfügung stehen.

## Automatisierung mit GitHub Actions

Der Workflow `.github/workflows/ci.yml` kann manuell gestartet werden (`workflow_dispatch`) und läuft zusätzlich jede Nacht um 03:00 Uhr deutscher Zeit (`cron: "0 1 * * *"` in UTC). Bei jedem Lauf werden die Abhängigkeiten installiert, der aktuelle CSV-Spielplan nach `data/schedule.csv` heruntergeladen, das Modul kompiliert und anschließend der HTML-Bericht erzeugt. Das Ergebnis wird als Artefakt `usc-report` bereitgestellt, in `docs/index.html` geschrieben, bei Änderungen automatisch in den `main`-Branch eingecheckt **und** direkt über GitHub Pages veröffentlicht.

Nach dem ersten erfolgreichen Workflow-Lauf ist der Bericht unter `https://<dein-account>.github.io/<repository-name>/` öffentlich abrufbar. Eine separate Aktivierung von GitHub Pages ist nicht mehr nötig; das Deployment erledigt der Workflow.

## Nächste Schritte

Der Bericht bündelt bereits Spielplan, Ergebnisse, Kader, News und internationale Auftritte. Wenn du mehr brauchst, kannst du darauf aufbauend weitere Auswertungen ergänzen – etwa zusätzliche Statistiken, alternative Layouts oder tiefergehende Analysen einzelner Teams.
