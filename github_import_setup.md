# Anleitung: Repository-Import und GitHub-Einrichtung für einen anderen Frauen-Volleyball-Bundesliga-Verein

Diese Anleitung beschreibt, wie du dieses Repository in der **letzten Version** übernimmst und in GitHub so einrichtest, dass es für einen anderen Verein (z. B. SSC Palmberg Schwerin, Dresdner SC, Allianz MTV Stuttgart usw.) stabil läuft.

## 1) Repository in GitHub importieren

1. In GitHub oben rechts auf **+ → Import repository** gehen.
2. Als Quelle dieses Repository angeben.
3. Ziel-Owner (Organisation oder Benutzer) wählen.
4. Namen für das neue Repository festlegen (z. B. `dsc-streaminginfos`).
5. Import starten und warten, bis der Vorgang abgeschlossen ist.

> Alternativ: `git clone --mirror` + `git push --mirror` funktioniert ebenfalls, der GitHub-Importer ist aber meist am schnellsten.

## 1.1 Kontinuierliche Übernahme deiner Änderungen (wichtig)

Ja, das geht – aber **nicht** mit „Import repository“ allein.

Der Import erstellt eine einmalige Kopie (Snapshot). Wenn ein anderes Repo die späteren Änderungen automatisch übernehmen soll, nutze stattdessen einen dieser Wege:

### Option A (empfohlen): Fork verwenden

Wenn möglich, erstelle das Ziel-Repo als **Fork** des Ursprungs-Repos. Vorteile:

- Upstream-Beziehung ist in GitHub direkt sichtbar.
- Änderungen aus dem Original können über **Sync fork** oder Pull Requests übernommen werden.
- Eigene Anpassungen bleiben trotzdem im Fork möglich.

### Option B: Import + Upstream-Remote setzen

Wenn das Repo bereits importiert wurde, kannst du trotzdem dauerhaft synchronisieren:

1. Lokales Ziel-Repo klonen.
2. Ursprungs-Repo als `upstream` hinzufügen.
3. Regelmäßig Änderungen von `upstream/main` holen und in `main` mergen/rebasen.

Beispiel:

```bash
git remote add upstream https://github.com/<quelle>/<repo>.git
git fetch upstream
git checkout main
git merge upstream/main
# alternativ: git rebase upstream/main
```

### Automatisierung der Synchronisierung

Optional kann ein geplanter GitHub-Action-Workflow (z. B. täglich) `upstream` fetchen und automatisch einen PR mit den Upstream-Änderungen erstellen. Das ist der sauberste Weg, wenn mehrere Teams zusammenarbeiten.

> Empfehlung: Für Vereine mit eigenen Branding-/Content-Anpassungen ist „Import + Upstream-Sync per PR“ meist am stabilsten, weil Konflikte kontrolliert geprüft werden können.

## 2) Technischen Benutzer für Automatisierung anlegen

Wenn Commits über GitHub Actions in den `main`-Branch geschrieben werden sollen, ist ein dedizierter Bot-/Service-User sinnvoll.

1. Neuen GitHub-Benutzer erstellen (z. B. `verein-stream-bot`).
2. In der Ziel-Organisation den Benutzer hinzufügen.
3. Dem Benutzer mindestens **Write**-Rechte auf das neue Repository geben.
4. Optional: Feingranulare Rollen verwenden (nur dieses Repo).

## 3) Unbedingt in GitHub einstellen (nach dem Import)

## 3.1 Repository-Einstellungen

Unter **Settings → General**:

- Standardbranch prüfen: `main`.
- **Issues/Discussions/Projects** nur aktivieren, wenn benötigt.
- Optional: Repository-Beschreibung und Topics setzen (z. B. `volleyball`, `bundesliga`, `streaming`).

## 3.2 Actions aktivieren und Rechte setzen

Unter **Settings → Actions → General**:

- Actions für das Repository erlauben (mindestens „Allow all actions and reusable workflows“ oder eure Org-Policy).
- Bei „Workflow permissions“ auf **Read and write permissions** stellen, wenn Workflows zurück in das Repo committen sollen.
- Option „Allow GitHub Actions to create and approve pull requests“ nach Bedarf aktivieren (nur relevant bei PR-basierten Workflows).

## 3.3 Branch Protection für `main`

Unter **Settings → Branches** eine Regel für `main` anlegen:

Empfohlen:

- `Require a pull request before merging` (mind. 1 Review) für Team-Repos.
- `Require status checks to pass` (falls CI-Checks verpflichtend sein sollen).
- `Do not allow force pushes` aktivieren.
- Falls Workflows direkt in `main` committen sollen: Schutzregeln so gestalten, dass der Bot weiterhin schreiben darf (z. B. über Ausnahmen/Bypass gemäß Org-Policy).

## 3.4 GitHub Pages konfigurieren

Wenn HTML aus `docs/` veröffentlicht werden soll:

1. **Settings → Pages** öffnen.
2. Source auf **Deploy from a branch** stellen.
3. Branch `main` und Ordner `/docs` wählen.
4. Speichern.

Danach ist die Seite unter `https://<owner>.github.io/<repo>/` erreichbar.

## 3.5 Secrets und Variablen prüfen

Unter **Settings → Secrets and variables → Actions**: Keine Einstellungen notwendig.


## 3.6 Sicherheits- und Wartungseinstellungen

Unter **Settings → Security** (je nach Plan/Org-Verfügbarkeit):

- Dependabot Alerts aktivieren.
- Secret Scanning aktivieren.
- Optional Dependabot Updates für Python-Abhängigkeiten konfigurieren.

## 4) Vereinswechsel fachlich konfigurieren

Der Import allein reicht nicht: Die Vereinsparameter müssen angepasst werden.

1. `config.json` auf den neuen Verein anpassen (Teamname, URLs, Social-Links, IDs etc.).
2. Prüfen, ob die verwendete Spielplan-URL für den Zielverein korrekt ist.
3. Bei Bedarf statische Texte in `docs/` (Titel, Branding) anpassen.

## 5) Erste Inbetriebnahme

1. Einen manuellen Workflow-Run in **Actions** starten.
2. Prüfen, ob `docs/index.html` (und ggf. `docs/index_app.html`) aktualisiert wird.
3. Prüfen, ob der Commit durch den richtigen technischen Benutzer erscheint.
4. GitHub-Pages-URL öffnen und Darstellung prüfen.

## 6) Betriebsmodell festlegen (wichtig)

Entscheide früh, welches Modell ihr nutzen wollt:

- **Direkter Commit durch Workflow**: Schnell und simpel, braucht passende Schreibrechte.
- **PR-basierter Flow**: Sicherer für Teams mit Freigabeprozess, aber etwas mehr Aufwand.

## 7) Checkliste (Kurzfassung)

- [ ] Repo importiert
- [ ] Technischer Benutzer angelegt und berechtigt
- [ ] Actions erlaubt + Write Permissions gesetzt
- [ ] Branch Protection passend konfiguriert
- [ ] Pages (`main` + `/docs`) aktiviert
- [ ] `config.json` auf Zielverein angepasst
- [ ] Erster Workflow-Lauf erfolgreich
- [ ] Öffentliche URL geprüft

---

Wenn du möchtest, kann diese Anleitung im nächsten Schritt auf einen konkreten Verein (z. B. Dresden, Stuttgart oder Schwerin) mit konkreten `config.json`-Feldwerten heruntergebrochen werden.
