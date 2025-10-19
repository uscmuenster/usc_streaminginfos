# USC Streaminginfos

Dieses Repository erzeugt täglich eine schlanke HTML-Seite zum Frauen-Bundesligateam des USC Münster. Die Seite zeigt den
nächsten Heimgegner des USC als Überschrift, listet die letzten vier Ergebnisse sowohl des USC als auch des kommenden Gegners
auf und sammelt aktuelle Artikel von den Team-Homepages sowie der Volleyball Bundesliga. Alle Spielinformationen stammen aus dem
öffentlichen CSV-Spielplan der Volleyball Bundesliga – es wird kein API-Schlüssel benötigt.

## Voraussetzungen

* Python 3.12 oder neuer
* Abhängigkeiten installieren mit `pip install -r requirements.txt`

## Manuelle Ausführung

Das Paket stellt einen kleinen Helfer bereit, der den offiziellen Spielplan lädt, aktuelle Vereins- und VBL-Meldungen sammelt
und die HTML-Datei erzeugt. Standardmäßig schreibt der Befehl sowohl `docs/index.html` (normale Ansicht) als auch
`docs/index_app.html` (Schriftgrößen ca. 75 % für die App-Einbindung), damit beide Varianten direkt von GitHub Pages oder einem
anderen statischen Hoster ausgeliefert werden können. Beispiel:

```bash
PYTHONPATH=src python -m usc_kommentatoren
```

Beim ersten Aufruf (und bei jeder späteren Aktualisierung) lädt das Skript den CSV-Spielplan herunter und speichert ihn unter
`data/schedule.csv`. Wenn bereits eine lokale Kopie existiert, wird sie überschrieben. Der Pfad kann mit `--schedule-path`
angepasst werden. Zusätzlich lädt der Generator die offiziellen Teamkader als CSV-Export in `data/rosters/`, cacht Mannschafts-
fotos im Verzeichnis `data/team_photos/`, bindet sie inline in den Bericht ein, sortiert Spielerinnen nach Rückennummern und
ergänzt Offizielle direkt darunter. Auch die Wechselbörse wird ausgewertet; alle Zu- und Abgänge der beiden Teams landen als
eigene Accordion-Sektion im Bericht. Die Speicherorte lassen sich mit `--roster-dir`, `--photo-dir` sowie `--schedule-path`
anpassen. Über `--app-output`, `--app-scale` und `--skip-app-output` steuerst du bei Bedarf, wohin die App-Variante geschrieben
wird, wie stark die Schrift verkleinert werden soll oder ob sie komplett entfallen darf. Optional kannst du außerdem Zielpfad,
Quelle, Anzahl der vergangenen Partien sowie den News-Zeitraum ändern:

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
  --app-scale 0.7
```

Die HTML-Datei enthält:

* Überschrift mit dem nächsten Heimgegner des USC Münster
* Spieltermin und Austragungsort
* Die letzten vier Ergebnisse des USC Münster inklusive Gesamt- und Satzergebnissen (sofern vorhanden)
* Die letzten vier Ergebnisse des anstehenden Gegners inklusive Gesamt- und Satzergebnissen (sofern vorhanden)
* Einen direkten Link auf die offizielle Bundesligatabelle
* Eine "Bemerkungen"-Rubrik, die Spielerinnen mit Geburtstagen am Spieltag sowie aus den sieben Tagen davor hervorhebt – inklusive Datum und Alter
* Aufklappbare Kaderübersichten beider Teams inklusive lokal eingebundenem Mannschaftsfoto, sortierten Rückennummern sowie allen Spielerinnen-Details (Größe, Geburtstag inklusive Alter am Spieltag, Nation, Position) und den Offiziellen direkt darunter
* Eine zusätzliche Wechselbörse-Sektion pro Team mit den jüngsten Zu- und Abgängen aus der offiziellen VBL-Wechselbörse
* Verlinkungen auf die Vereins-Homepages des USC Münster und des kommenden Gegners mit sprechenden Linktexten (z. B. "Homepage USC Münster")
* Einen News-Block je Team unterhalb der Ergebnislisten – als aufklappbare Accordion-Sektion mit Artikeln der letzten zwei Wochen von den Vereinsseiten sowie den VBL-News- und Pressespiegel-Seiten, gefiltert auf Beiträge zu den beiden Teams
* Eine Instagram-Sektion mit Links zu den offiziellen Accounts und weiteren Treffern aus der Websuche für beide Mannschaften
* Ein responsives Layout, das sich auf Smartphones und großen Displays gut lesen lässt

## Automatisierung mit GitHub Actions

Der Workflow `.github/workflows/ci.yml` kann manuell gestartet werden (`workflow_dispatch`) und läuft zusätzlich jede Nacht um
03:00 Uhr deutscher Zeit (`cron: "0 1 * * *"` in UTC). Bei jedem Lauf werden die Abhängigkeiten installiert, der aktuelle
CSV-Spielplan nach `data/schedule.csv` heruntergeladen, das Modul kompiliert und anschließend der HTML-Bericht erzeugt. Das
Ergebnis wird als Artefakt `usc-report` bereitgestellt, in `docs/index.html` geschrieben, bei Änderungen automatisch in den
`main`-Branch eingecheckt **und** direkt über GitHub Pages veröffentlicht.

Nach dem ersten erfolgreichen Workflow-Lauf ist der Bericht unter
`https://<dein-account>.github.io/<repository-name>/` öffentlich abrufbar. Eine separate Aktivierung von GitHub Pages ist nicht mehr nötig; das Deployment erledigt der Workflow.

## Nächste Schritte

Der Bericht bündelt bereits Spielplan, Ergebnisse und aktuelle Artikel. Wenn du mehr brauchst, kannst du darauf aufbauend
weitere Auswertungen ergänzen – etwa zusätzliche Statistiken, alternative Layouts oder tiefergehende Analysen einzelner Teams.
