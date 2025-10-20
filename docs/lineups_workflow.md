# Workflow: Startaufstellungen aus Spielberichtsbögen

Dieser Workflow beschreibt, wie die Startaufstellungen der beiden letzten Bundesliga-Partien des USC Münster aus den offiziellen Spielberichtsbögen extrahiert und für die Webseite aufbereitet werden.

## Überblick

1. **Spielplan abrufen:** Die CSV-Exportdatei der Volleyball Bundesliga wird heruntergeladen. Sie enthält alle Spieltermine inklusive Spielnummer (`#`), Datum, Uhrzeit, Heim- und Auswärtsteam.
2. **USC-Spiele filtern:** Aus dem Spielplan werden die jüngsten zwei Begegnungen ermittelt, in denen der USC Münster beteiligt ist und für die bereits ein Ergebnis vorliegt.
3. **PDF-Links bestimmen:** Die öffentliche Spielplan-Seite der VBL wird geparst, um zu jeder Spielnummer den Link auf den offiziellen Spielberichtsbogen (`scoresheet/pdf/.../<Matchnummer>`) zu ermitteln.
4. **Spielberichtsbögen laden:** Die betreffenden PDF-Dateien werden heruntergeladen und lokal unter `data/lineups/<Matchnummer>.pdf` abgelegt.
5. **Startaufstellungen extrahieren:** Mit `pdfplumber` werden aus jedem Spielbericht pro Satz die sechs Startpositionen von USC und Gegner identifiziert. Satz 5 besitzt eine leicht abweichende Tabellenstruktur – hierfür greift eine speziell angepasste Ausleselogik.
6. **Kaderdaten ergänzen:** Für alle beteiligten Teams lädt der Generator die offiziellen Kader-CSV-Exporte (Caching unter `data/rosters/`). Aus den Rollenangaben wird automatisch erkannt, welche Rückennummer(n) als Zuspielerinnen geführt werden.
7. **Datensatz schreiben:** Sämtliche Informationen werden als JSON nach `docs/data/aufstellungen.json` exportiert. Zusätzlich werden Metadaten wie Wettbewerb, Spielort, Ergebnis und Zeitpunkt der Datengenerierung festgehalten.
8. **Frontend aktualisieren:** Die Seite `docs/aufstellungen.html` lädt das JSON und rendert die Startaufstellungen dynamisch.

## Skripte & Automatisierung

### Manuelle Aktualisierung

Für lokale Aktualisierungen steht das Hilfsskript `scripts/update_lineups.py` zur Verfügung. Es kümmert sich um die korrekte `PYTHONPATH`-Konfiguration und ruft das Lineup-Modul mit den passenden Standardpfaden auf.

```bash
python scripts/update_lineups.py
```

Optional lassen sich Parameter wie die Anzahl der Spiele (`--limit`), alternative Datenquellen oder ein anderer Ausgabeort übergeben. Mit `--cache-dir` und `--roster-dir` können die Ablageorte für Spielberichtsbögen (`data/lineups/`) bzw. Kaderexporte (`data/rosters/`) überschrieben werden. Das Skript wertet standardmäßig die beiden letzten USC-Partien **und** die zwei jüngsten Begegnungen des kommenden Gegners aus und erzeugt daraus einen gemeinsamen Datensatz mit Trennung nach Fokus-Team.

### Tägliche Ausführung via GitHub Actions

Der Workflow `.github/workflows/update-lineups.yml` startet täglich um 04:30 Uhr (UTC) sowie auf manuellen Workflow-Dispatch. Er installiert die Python-Abhängigkeiten, führt `python scripts/update_lineups.py` aus und erstellt bei Änderungen automatisch einen Pull Request mit dem aktualisierten Datensatz `docs/data/aufstellungen.json`.

## Abhängigkeiten

- [`requests`](https://pypi.org/project/requests/) für HTTP-Abfragen
- [`beautifulsoup4`](https://www.crummy.com/software/BeautifulSoup/) zum Parsen der Spielplan-Seite
- [`pdfplumber`](https://github.com/jsvine/pdfplumber) zur strukturierten Auswertung der Spielberichtsbögen

Die benötigten Pakete sind in `requirements.txt` hinterlegt.

## Fehlerbehandlung & Hinweise

- Liefert die VBL-Seite noch keinen Spielberichtsbogen (fehlender Link), bricht das Skript mit einem Hinweis auf die betroffene Spielnummer ab.
- Die PDF-Auswertung enthält Fallback-Logik für abweichende Tabellenlayouts (insbesondere für Satz 5).
- Das JSON enthält ausschließlich Startaufstellungen. Wechselinformationen stehen derzeit nicht zur Verfügung und werden in der Darstellung mit `–` markiert.
- Für jede Startformation werden neben den Rückennummern auch die im Spielbericht geführten Namen (gekürzt auf den Nachnamen) gespeichert, sodass die HTML-Ansicht Feldaufstellungen wie im Screenshot rendern kann.
- Die Markierung der Zuspielerin basiert auf den offiziellen Kaderrollen. Falls ein Team ohne abrufbaren Kader exportiert wird, entfällt die Hervorhebung automatisch.

