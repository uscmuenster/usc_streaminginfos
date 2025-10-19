# usc_kommentatoren

Dieses Repository erzeugt täglich eine schlanke HTML-Seite zum Frauen-Bundesligateam des USC Münster. Die Seite zeigt den
nächsten Heimgegner des USC als Überschrift und listet die beiden letzten Ergebnisse sowohl des USC als auch des kommenden
Gegners auf. Alle Informationen stammen ausschließlich aus dem öffentlichen CSV-Spielplan der Volleyball Bundesliga – es wird
kein API-Schlüssel benötigt.

## Voraussetzungen

* Python 3.12 oder neuer
* Abhängigkeiten installieren mit `pip install -r requirements.txt`

## Manuelle Ausführung

Das Paket stellt einen kleinen Helfer bereit, der den offiziellen Spielplan lädt und die HTML-Datei erzeugt. Beispiel:

```bash
PYTHONPATH=src python -m usc_kommentatoren --output usc_report.html
```

Optional lässt sich eine andere Quelle angeben oder die Anzahl der vergangenen Partien anpassen:

```bash
PYTHONPATH=src python -m usc_kommentatoren \
  --schedule-url "https://www.volleyball-bundesliga.de/servlet/league/PlayingScheduleCsvExport?matchSeriesId=776311171" \
  --recent-limit 3 \
  --output usc_report.html
```

Die HTML-Datei enthält:

* Überschrift mit dem nächsten Heimgegner des USC Münster
* Spieltermin und Austragungsort
* Die beiden letzten Ergebnisse des USC Münster
* Die beiden letzten Ergebnisse des anstehenden Gegners

## Automatisierung mit GitHub Actions

Der Workflow `.github/workflows/ci.yml` kann manuell gestartet werden (`workflow_dispatch`) und läuft zusätzlich jede Nacht um
03:00 Uhr deutscher Zeit (`cron: "0 1 * * *"` in UTC). Bei jedem Lauf werden die Abhängigkeiten installiert, das Modul
kompiliert und anschließend der HTML-Bericht erzeugt. Das Ergebnis wird als Artefakt `usc-report` bereitgestellt und kann über
den jeweiligen Workflow-Run heruntergeladen werden.

## Nächste Schritte

Dieser erste Schritt konzentriert sich ausschließlich auf die automatische HTML-Ausgabe. Weitere Auswertungen (z. B.
Langzeitstatistiken, News-Sammlungen oder zusätzliche Layouts) können darauf aufbauen.
