# usc_kommentatoren

Dieses Repository erzeugt täglich eine schlanke HTML-Seite zum Frauen-Bundesligateam des USC Münster. Die Seite zeigt den
nächsten Heimgegner des USC als Überschrift, listet die beiden letzten Ergebnisse sowohl des USC als auch des kommenden Gegners
auf und sammelt aktuelle Artikel von den Team-Homepages sowie der Volleyball Bundesliga. Alle Spielinformationen stammen aus dem
öffentlichen CSV-Spielplan der Volleyball Bundesliga – es wird kein API-Schlüssel benötigt.

## Voraussetzungen

* Python 3.12 oder neuer
* Abhängigkeiten installieren mit `pip install -r requirements.txt`

## Manuelle Ausführung

Das Paket stellt einen kleinen Helfer bereit, der den offiziellen Spielplan lädt, aktuelle Vereins- und VBL-Meldungen sammelt
und die HTML-Datei erzeugt. Standardmäßig schreibt der Befehl die Ausgabe nach `docs/index.html`, damit sie direkt von GitHub
Pages oder einem anderen statischen Hoster ausgeliefert werden kann. Beispiel:

```bash
PYTHONPATH=src python -m usc_kommentatoren
```

Wenn du bereits weißt, unter welcher öffentlichen Adresse der Bericht erreichbar sein soll (z. B. eine GitHub-Pages-URL),
kannst du sie optional mitgeben, damit sie in der HTML-Datei verlinkt wird:

```bash
PYTHONPATH=src python -m usc_kommentatoren \
  --public-url "https://example.com/usc-report.html"
```

Beim ersten Aufruf (und bei jeder späteren Aktualisierung) lädt das Skript den CSV-Spielplan herunter und speichert ihn unter
`data/schedule.csv`. Wenn bereits eine lokale Kopie existiert, wird sie überschrieben. Der Pfad kann mit `--schedule-path`
angepasst werden. Optional lassen sich außerdem Zielpfad, Quelle, Anzahl der vergangenen Partien sowie der News-Zeitraum ändern:

```bash
PYTHONPATH=src python -m usc_kommentatoren \
  --schedule-url "https://www.volleyball-bundesliga.de/servlet/league/PlayingScheduleCsvExport?matchSeriesId=776311171" \
  --schedule-path data/custom_schedule.csv \
  --recent-limit 3 \
  --news-lookback 10 \
  --output docs/custom_report.html \
  --public-url "https://example.com/usc-report.html"
```

Die HTML-Datei enthält:

* Überschrift mit dem nächsten Heimgegner des USC Münster
* Spieltermin und Austragungsort
* Die beiden letzten Ergebnisse des USC Münster inklusive Gesamt- und Satzergebnissen
* Die beiden letzten Ergebnisse des anstehenden Gegners inklusive Gesamt- und Satzergebnissen
* Einen direkten Link auf die offizielle Bundesligatabelle
* Verlinkungen auf die Vereins-Homepages des USC Münster und des kommenden Gegners mit sprechenden Linktexten (z. B. "Homepage USC Münster")
* Einen News-Block unter jedem Ergebnisabschnitt mit aktuellen Artikeln der letzten zwei Wochen von den Vereinsseiten sowie den VBL-News- und Pressespiegel-Seiten – gefiltert auf Beiträge zu den beiden Teams
* Ein responsives Layout, das sich auf Smartphones und großen Displays gut lesen lässt

## Automatisierung mit GitHub Actions

Der Workflow `.github/workflows/ci.yml` kann manuell gestartet werden (`workflow_dispatch`) und läuft zusätzlich jede Nacht um
03:00 Uhr deutscher Zeit (`cron: "0 1 * * *"` in UTC). Bei einem manuellen Lauf kannst du optional eine öffentliche URL
eingeben, die in den Bericht aufgenommen wird. Bei jedem Lauf werden die Abhängigkeiten installiert, der aktuelle
CSV-Spielplan nach `data/schedule.csv` heruntergeladen, das Modul kompiliert und anschließend der HTML-Bericht erzeugt. Das
Ergebnis wird als Artefakt `usc-report` bereitgestellt, in `docs/index.html` geschrieben, bei Änderungen automatisch in den
`main`-Branch eingecheckt **und** direkt über GitHub Pages veröffentlicht.

Nach dem ersten erfolgreichen Workflow-Lauf ist der Bericht unter
`https://<dein-account>.github.io/<repository-name>/` öffentlich abrufbar – vergleichbar mit
[`https://uscmuenster.github.io/USC-Spielplaene2526/index_trainer.html`](https://uscmuenster.github.io/USC-Spielplaene2526/index_trainer.html). Eine separate Aktivierung von GitHub Pages ist nicht mehr nötig; das Deployment erledigt der Workflow.

## Nächste Schritte

Der Bericht bündelt bereits Spielplan, Ergebnisse und aktuelle Artikel. Wenn du mehr brauchst, kannst du darauf aufbauend
weitere Auswertungen ergänzen – etwa zusätzliche Statistiken, alternative Layouts oder tiefergehende Analysen einzelner Teams.
