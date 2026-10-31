# Layout-Dokumentation des Spieltagsberichts

Diese Datei beschreibt das vollständige visuelle und strukturelle Layout von
`docs/index.html`. Die kompaktere App-Variante `docs/index_app.html` teilt sich
viele Basiskomponenten mit dem Bericht und setzt `--font-scale` auf `0.75`, hat
im aktuellen Stand aber nicht den zusätzlichen Matchcenter-Rahmen mit
Sprungnavigation und großem Hero-Header. Beide HTML-Dateien werden aus
`src/usc_kommentatoren/report.py` generiert. Dauerhafte Layoutänderungen müssen
daher in der Generatorvorlage erfolgen und anschließend neu generiert werden.

> **Geltungsbereich:** Beschrieben wird der Spieltagsbericht beziehungsweise das
> Matchcenter. Die eigenständigen Seiten `aufstellungen.html`,
> `germany_vnl.html` und `internationale_spiele.html` besitzen eigene Layouts.

## 1. Gestaltungsziel

Das Matchcenter ist eine responsive, kartenbasierte Einzelseite für die
Vorbereitung und Begleitung eines Volleyballspiels. Das Layout kombiniert:

- eine stets erreichbare Sprungnavigation,
- einen großformatigen Spiel-Header,
- kompakte Kennzahlen,
- einen bedienbaren Produktionsbereich mit Countdown und Stoppuhr,
- Informationskarten für Spiele, Kader, Transfers, News und Statistiken sowie
- eine druckoptimierte Darstellung.

Die Heimteam-Inhalte sind türkis/grün markiert, Inhalte des Gegners blau. Weiß
und sehr helle Grün- beziehungsweise Blautöne bilden die Kartenflächen. Große
Radien, weiche Schatten und farbige Oberkanten erzeugen die visuelle Hierarchie.

## 2. Dokument- und Seitenrahmen

### 2.1 HTML-Grundlage

- Dokumenttyp: HTML5 (`<!DOCTYPE html>`)
- Dokumentsprache: Deutsch (`lang="de"`)
- Zeichensatz: UTF-8
- Viewport: `width=device-width, initial-scale=1`
- Farbschema: hell und dunkel über `color-scheme: light dark`
- Theme-Farbe/PWA-Farbe: standardmäßig `#0f766e`
- Favicon, Apple-Touch-Icon und Web-App-Manifest werden aus `docs/` geladen.

### 2.2 Breite und Außenabstände

Der finale Seitenrahmen wird durch die am Ende des Stylesheets stehende
Matchcenter-Ebene definiert:

```css
main,
.wrap {
  width: min(1240px, calc(100% - 32px));
  max-width: none;
  margin: 0 auto;
  padding: 0;
}
```

- Maximale Inhaltsbreite: **1240 px**.
- Standardmäßiger horizontaler Mindestabstand: **16 px je Seite**.
- Bis 720 px Viewportbreite wird der Mindestabstand auf **10 px je Seite**
  reduziert (`width: min(100% - 20px, 1240px)`).
- Der Header-Hintergrund läuft über die gesamte Viewportbreite; sein Inhalt
  bleibt innerhalb von `.wrap`.
- Der Hauptinhalt wird horizontal zentriert.

### 2.3 Seitenhintergrund

Der helle Hintergrund besteht aus zwei radialen Farbflächen und einem linearen
Verlauf:

1. mintgrüner Schein links oben,
2. hellblauer Schein rechts oben,
3. Verlauf von `#f8fffc` über Weiß zu `#eefcf6`.

Damit heben sich die überwiegend weißen Karten ab, ohne dass harte
Flächengrenzen entstehen.

## 3. Design-Tokens

### 3.1 Finale Matchcenter-Tokens

| Variable | Standardwert | Verwendung |
|---|---:|---|
| `--ink` | `#0f172a` | Primäre Textfarbe |
| `--paper` | `#f7fffb` | Sehr heller Flächenhintergrund |
| `--white` | `#ffffff` | Karten und Kontrastflächen |
| `--usc-deep` | `#004c54` | Dunkles Heimteam-Türkis |
| `--usc` | `#0f766e` | Primär-/Heimteam-Farbe |
| `--usc-bright` | `#10b981` | Helles Grün für Verläufe/Akzente |
| `--mint` | `#dcfce7` | Heimteam-Hinterlegung |
| `--sky` | `#e0f2fe` | Gegner-Hinterlegung |
| `--blue` | `#1d4ed8` | Gegner-Akzent |
| `--muted` | `#64748b` | Sekundärtext |
| `--line` | `rgba(0,76,84,.14)` | Standardrahmen |
| `--soft-shadow` | `0 14px 35px rgba(0,76,84,.10)` | Karten-Schatten |
| `--shadow` | `0 22px 54px rgba(0,76,84,.18)` | Starker Header-Schatten |
| `--radius` | `24px` | Standardradius großer Flächen |

### 3.2 Semantische Teamfarben

Zusätzlich existieren semantische Variablen für Accordion-, Tabellen-, Karten-,
MVP- und Legendenzustände:

- Heimteam/USC: Hintergründe `#dcfce7`, Text `#047857`, Punkt `#16a34a`.
- Gegner: Hintergründe `#e0f2fe`, Text `#1d4ed8`, Punkt `#2563eb`.
- Das konfigurierbare Primärthema ist standardmäßig `#0f766e` und wird unter
  anderem für `--theme-color`, `--home-accent` und
  `--mvp-overview-summary-bg` eingesetzt.

### 3.3 Typografie

Die proportionale Font-Kaskade lautet:

```text
Inter, Segoe UI, -apple-system, BlinkMacSystemFont,
Helvetica Neue, Arial, sans-serif
```

Für Zeitwerte der Stoppuhr wird eine Monospace-Kaskade verwendet:

```text
Fira Mono, SFMono-Regular, Menlo, Consolas, monospace
```

- Fließtext: `clamp(0.95rem, 1.8vw, 1.05rem)`, Zeilenhöhe `1.6`.
- Haupttitel im finalen Header: `clamp(42px, 7vw, 82px)`, Zeilenhöhe `.92`,
  Laufweite `-.08em`, Gewicht `1000`.
- Blocküberschriften: `clamp(24px, 3vw, 32px)`, Laufweite `-.04em`.
- Untertitel im Header: `clamp(16px, 2vw, 21px)`, Zeilenhöhe `1.45`.
- Sekundär- und Beschriftungstexte sind häufig 11–13 px groß, fett und in
  Versalien mit erhöhter Laufweite gesetzt.
- `--font-scale` skaliert die Ausgabevariante; `--font-context-scale` wird im
  Standalone-/Fullscreen-PWA-Modus auf `1.25` gesetzt.

## 4. Vertikale Seitenstruktur

Die Reihenfolge der sichtbaren Hauptbereiche ist fest:

1. Sticky-Sprungnavigation `.jumpbar`
2. Spiel-Header `header#top`
3. Kurzbriefing `.notice`
4. Schnellübersicht `.quickstats`
5. Live-Regie und Sendeablauf `#live-regie`
6. Spiele des Gegners `#spiele-gegner`
7. Spiele des USC `#spiele-usc`
8. Direkter Vergleich `#direktvergleich`
9. Kompakte Kaderlisten `#kader`
10. Kompakte Wechselbörse `#wechsel`
11. News `#news`
12. MVP-Rankings `#mvp`
13. Instagram-Links `#instagram`
14. Saisonergebnisse `#saison`
15. Aktualisierungshinweis im Footer

Ankerziele erhalten `scroll-margin-top: 70px`, damit sie nach einem Sprung nicht
von der sticky Navigation verdeckt werden.

## 5. Komponenten im Detail

### 5.1 Sticky-Sprungnavigation

`.jumpbar` bleibt mit `position: sticky`, `top: 0` und `z-index: 1000` am oberen
Rand. Sie besitzt:

- fast deckenden Hintergrund `rgba(0,76,84,.95)`,
- `backdrop-filter: blur(16px)`,
- eine feine helle Unterkante und einen tiefen Schatten,
- eine zweispaltige innere Grid-Struktur aus Links und Countdown,
- vertikal 6 px Innenabstand.

Die Links sind horizontal scrollbar, ohne sichtbare Scrollbar. Jeder Link ist
eine kompakte Pill mit 12 px Schrift, 6/10 px Innenabstand und vollständig
gerundetem Rand. Hover und Tastaturfokus erhöhen Grünanteil und Rahmenkontrast.

Der Countdown rechts ist mindestens 112 px breit, verwendet tabellarische
Ziffern und kann die Zustände `.is-urgent` und `.is-done` darstellen. Auf
Mobilgeräten wird er in eine zweite Zeile gesetzt und zentriert.

### 5.2 Hero-/Spiel-Header

`header#top` ist eine vollbreite, überlaufgeschützte Farbfläche mit 54 px
Innenabstand oben und 42 px unten. Der Hintergrund ist ein kantiger Verlauf von
dunklem Türkis über Primärtürkis zu Grün. Bestandteile:

- `.eyebrow`: USC-Kontext in Mint, Versalien und großer Laufweite,
- `h1`: weißer Haupttitel; der Gegnername im `span` ist hellmint,
- `.subtitle`: erklärender Text mit maximal 850 px Breite,
- `.meta-row`: umbrechende Flex-Zeile mit 10 px Abstand,
- `.pill`: Spielmetadaten als halbtransparente, weiße Pills mit 9/12 px Padding.

### 5.3 Kurzbriefing und Schnellübersicht

`.notice` ist eine helle Verlaufskarte mit 24 px Radius, 18/20 px Innenabstand,
Rahmen und weichem Schatten. Sie fasst Termin, Ort, Wettbewerb und
Schiedsgericht als eine kompakte Textzeile zusammen.

`.quickstats` ist standardmäßig ein Grid aus **fünf gleich breiten Spalten** mit
12 px Abstand. Jede `.stat`-Karte hat 20 px Radius und 16 px Innenabstand. Der
Wert ist groß und eng gesetzt; die Bezeichnung steht darunter in 12 px,
Versalien und Sekundärfarbe.

### 5.4 Allgemeine Inhaltsblöcke

Die meisten Bereiche nutzen `.block`:

- `position: relative`,
- 24 px Radius und Innenabstand,
- 22 px vertikaler Außenabstand,
- heller vertikaler Verlauf,
- feiner Rahmen und weicher Schatten,
- 7 px hohe Akzentkante oben.

Die Standard-Akzentkante verläuft von dunklem Türkis über Türkis nach Grün.
Gegnerblöcke verwenden Dunkelblau, Blau und Hellblau. Karten in Instagram-,
Saison- und Ergebnislisten folgen demselben Prinzip.

### 5.5 Live-Regie, Countdown und Stoppuhr

`.hero-layout` besteht auf großen Viewports aus zwei Spalten:

```css
grid-template-columns:
  minmax(0, clamp(20rem, 34vw, 28rem))
  minmax(0, 1fr);
```

- Linke Spalte: Spielmetadaten, Links und Stoppuhr.
- Rechte Spalte: Sendeablauf und Countdown.
- Abstand: `clamp(1rem, 3vw, 1.8rem)`.
- Unter 70 rem beziehungsweise in der finalen Ebene unter 1050 px werden die
  Spalten untereinander angeordnet.

`.broadcast-box` ist eine weiße Karte mit 22 px Radius. Ihr `details/summary`
macht Stoppuhr und Ablauf aufklappbar. Der runde Indikator dreht sich im offenen
Zustand um 90 Grad. Ein sichtbarer Fokusrahmen stellt Tastaturbedienbarkeit her.

Die Stoppuhr:

- zeigt eine zentrierte, fette Monospace-Zeit,
- nutzt einen helltürkisen Hintergrund,
- erhält im laufenden Zustand einen Türkis-Blau-Verlauf und stärkeren Schatten,
- ordnet Start, Stopp und Zurücksetzen als umbrechende Flex-Zeile an,
- stellt Schaltflächen als voll gerundete Türkis-Blau-Verlaufspills dar.

Der Ablauf liegt in einer horizontal scrollbareren Tabellenhülle. Zeit,
Countdown und Dauer bleiben kompakt; der Programmpunkt erhält den verfügbaren
Restplatz. In breiten Ansichten können Ablauf und Dauer-/Countdown-Felder mit
festen beziehungsweise begrenzten Breiten dargestellt werden. Unter 50 rem
werden Schrift, Zellabstände und Spaltenbreiten reduziert.

### 5.6 Spielkarten

Die Gegner- und Heimteamspiele sind getrennte Blöcke. Ergebniszeilen und Karten
verwenden:

- Teamfarbe als Seiten-/Oberkantenakzent,
- flexible beziehungsweise Grid-basierte Metadatenzeilen,
- Badges für Wettbewerb, Ergebnis und Status,
- hervorgehobene MVP-Informationen,
- Listen ohne Standard-Aufzählungszeichen.

Heimteam-Zeilen nutzen Mint/Grün, Gegner-Zeilen Himmelblau/Blau. Lange Namen und
Metadaten dürfen umbrechen; tabellarische Werte bleiben visuell kompakt.

### 5.7 Direkter Vergleich

Der Vergleich nutzt zusammengehörige Karten für Bilanz, letzte Duelle und
Mannschaftszuordnung. Teambezogene Werte übernehmen die semantischen Heim- und
Gegnerfarben. Die Liste „Alle Duelle“ ist als eigener untergeordneter Bereich
mit `h3` ausgezeichnet. Auf kleinen Viewports werden mehrspaltige
Vergleichsflächen einspaltig und Kennzahlen neu umgebrochen.

### 5.8 Kompakte Kader

Der gesamte Kaderbereich ist ein offenes `.compact-details`. Dessen Summary ist
eine türkis getönte Kopfzeile; ein automatisch erzeugtes Badge zeigt
„aufklappen“ oder „zuklappen“.

`.compact-two-grid` enthält zwei gleich breite Karten:

- `.compact-card--opponent`: blauer Rahmen/Akzent und sehr heller Blauverlauf,
- `.compact-card--usc`: türkiser Rahmen/Akzent und sehr heller Grünverlauf.

Eine Spielerzeile besitzt im Desktoplayout fünf Spalten:

```text
54 px Nummer | 46 px Position | flexibler Name | 48 px Größe | 44 px Alter
```

Die Zeile ist pillenförmig, knapp gepolstert und 12,5 px groß. Namen werden bei
Platzmangel mit Ellipse abgeschnitten. Untergeordnete `details` enthalten Staff
in drei Spalten: Rolle, Name und Detailangaben.

### 5.9 Kompakte Wechselbörse

Die Wechselbörse folgt dem Zweikartenraster der Kader. Desktopzeilen bestehen
aus fünf Spalten:

```text
Name (flexibel) | Position 45 px | Nation 52 px |
Status (flexibel) | vorheriger/nächster Verein (flexibel)
```

Kategorien und linke Farbkanten kodieren den Status:

- Zugang: grün,
- Abgang: rot,
- weiterhin im Kader: gelb,
- Trainer: türkis.

Lange Vertrags- und Vereinsangaben werden einzeilig mit Ellipse gekürzt. Der
vollständige Inhalt bleibt über das `title`-Attribut der Zeile verfügbar.

### 5.10 News und Accordions

News beider Teams werden als native `details`-Accordions ausgegeben. Die
Summary-Zeilen erhalten teambezogene Hintergründe. Der Inhaltsbereich nutzt eine
vertikale Linkliste; Quelle und Zeitpunkt stehen als zurückgenommene Metazeile
unter dem Titel. Links verwenden die Primärfarbe und besitzen klare
Hover-/Fokuszustände.

### 5.11 MVP-Rankings

`details.mvp-overview` umschließt alle Kategorien. Darin befinden sich:

- Erläuterungstext,
- Teamlegende mit farbigen Punkten,
- einzelne aufklappbare `.mvp-category`-Bereiche,
- geordnete `.mvp-list`-Listen.

Eine `.mvp-entry` teilt sich in Rang, flexiblen Spielerinnenblock und rechts
ausgerichteten Wert. Der Spielerinnenblock enthält Namen sowie Position, Team,
Sätze und Spiele als Metatext. Grün markiert USC-Einträge, Blau Einträge des
Gegners. Auf schmalen Displays werden Einträge dichter und Metatexte dürfen
mehrzeilig werden.

### 5.12 Instagram und Saison

Instagram- und Saisonbereiche nutzen responsive Karten-Grids. Jede Karte hat
20 px Radius, Rahmen und farbige Oberkante. Listen sind vertikal strukturiert.
Der Saisonbereich besitzt zusätzlich einen Kopf, je eine Teamkarte und einen
Block mit weiterführenden Links.

### 5.13 Footer

Der Footer liegt innerhalb des zentrierten Hauptinhalts. `.update-note` meldet
den letzten Aktualisierungszeitpunkt und ist mit `role="status"` für
Assistenztechnologien ausgezeichnet. Er verwendet Sekundärfarbe und geringere
visuelle Gewichtung als die Inhaltsblöcke.

## 6. Responsive Verhalten

Die Styles enthalten mehrere Breakpoints. Bei Überschneidungen gilt die später
im Stylesheet stehende Regel.

| Breakpoint | Layoutänderung |
|---|---|
| Standalone/Fullscreen | `--font-context-scale: 1.25` |
| bis 70 rem | Live-Regie wird einspaltig |
| ab 60 rem | Breite Tabellen-/Kartenanordnung wird aktiviert |
| bis 50 rem | Sendeablauftabelle wird kompakter |
| ab 48 rem | Bestimmte Kartenlisten wechseln in Mehrspaltenraster |
| bis 40 rem | Ergebnis-/Statistikkomponenten werden verdichtet |
| bis 38 rem | Mobile Karten- und MVP-Anpassungen |
| bis 30 rem | Kleinste Abstände und Schriftgrößen |
| bis 1050 px | Live-Regie und Zweikartenraster einspaltig; Quickstats zweispaltig |
| 721–1050 px | Kader bleibt in geeigneten Teilrastern zweispaltig, Zeilen werden enger |
| bis 720 px | 10 px Seitenrand, Navigation zweizeilig, Quickstats einspaltig |
| bis 430 px | Kaderkarten und Spielerzeilen nochmals kompakter |

### 6.1 Mobil bis 720 px

- `.jumpbar-inner` wird einspaltig; der Countdown nimmt die volle Breite ein.
- `.quickstats` wird einspaltig.
- `.block` erhält 18 statt 24 px Innenabstand.
- Kader- und Transfer-Tabellenköpfe werden ausgeblendet.
- Kaderzeilen verwenden `46 / 38 / flexibel / 42 / 38 px`.
- Transferzeilen nutzen drei Spalten und zwei Zeilen mit benannten Grid-Areas:
  Position, Nation und Name oben; Status und Verein unten.
- Staff-Details springen unter Rolle und Name in die zweite Spalte.

### 6.2 Sehr schmal bis 430 px

- Innenabstand des Zweikartenbereichs: 12 px.
- Karten-Innenabstand: 14 px vertikal und 10 px horizontal.
- Kaderzeilen: `42 / 34 / flexibel / 38 / 34 px`.
- Namen werden mit 12 px dargestellt.

## 7. Interaktion und Zustände

### 7.1 Native Offen-/Geschlossen-Zustände

Stoppuhr, Sendeplan, Kader, Wechselbörse, News und MVP-Kategorien verwenden
`details`/`summary`. Dadurch bleiben sie ohne JavaScript grundsätzlich
bedienbar. CSS ändert Indikatoren, Beschriftung und Rahmen anhand von `[open]`.

### 7.2 JavaScript-gebundene Elemente

Die Struktur verwendet `data-*`-Attribute statt präsentationsbezogener IDs für
das Verhalten:

- `data-jump-countdown`: Countdown in der Navigation,
- `data-countdown-banner`, `data-countdown-display`, `data-countdown-heading`:
  Hauptcountdown,
- `data-stopwatch` und `data-stopwatch-*`: Stoppuhr,
- `data-kickoff`: ISO-Zeitpunkt des Spielbeginns,
- `data-timezone`: relevante Zeitzone.

Der Countdown besitzt Standard-, dringenden, Live- und abgelaufenen Zustand.
Die Stoppuhr setzt beim Laufen eine visuell hervorgehobene Klasse.

### 7.3 Fokus, Hover und aktive Zustände

- Interaktive Elemente erhalten sichtbare `:focus-visible`-Konturen.
- Navigation und Links ändern Hintergrund beziehungsweise Textdekoration.
- Buttons werden bei Hover heller und werfen einen stärkeren Schatten.
- Beim Drücken verschieben sich Buttons minimal nach unten.
- Status darf nie ausschließlich durch Farbe vermittelt werden; Textlabels wie
  „Zugänge“, „Abgänge“ und Countdowntexte bleiben erhalten.

## 8. Dark Mode

Bei `prefers-color-scheme: dark` wird die Basisebene dunkel dargestellt:

- dunkler Seitenhintergrund und helle Textfarbe,
- Karten erhalten dunkle Blau-/Schieferflächen,
- Rahmen und Schatten werden kontrastgerecht angepasst,
- Links werden helltürkis,
- Countdown- und Teamakzente bleiben semantisch erhalten,
- der Live-Countdown wechselt zu einem kräftigen Rot-/Orangeverlauf.

Die am Ende ergänzte Matchcenter-Ebene definiert teilweise wieder helle
Kartenflächen. Bei Änderungen muss deshalb stets die **resultierende Cascade**
im Browser geprüft werden und nicht nur der frühere Dark-Mode-Block isoliert.

## 9. Drucklayout

`@media print` entfernt nicht benötigte Bedienoberflächen:

- Sprungnavigation,
- Stoppuhr-Buttons,
- Broadcast-Eingaben,
- Teamfoto-Umschalter.

Der Seitenhintergrund wird weiß. Schatten von Header, Blöcken, Hinweisen,
Broadcast-Karten und Kennzahlen werden entfernt. Inhalte und native
`details`-Zustände bleiben ansonsten entsprechend ihrem aktuellen Zustand
erhalten.

## 10. Barrierefreiheit

Folgende Regeln sind Bestandteil des Layoutvertrags:

- Semantische Elemente `nav`, `header`, `main`, `section`, `article`, `aside`,
  `table` und `footer` nicht ohne Grund durch generische `div` ersetzen.
- Die sichtbare Überschriftenhierarchie beginnt mit genau einem `h1`.
- Sprungnavigation und Steuerelementgruppen besitzen sprechende
  `aria-label`-Angaben.
- Dynamische Zeitwerte nutzen `aria-live="polite"`.
- Tabellenköpfe verwenden `scope="col"`, Zeilenköpfe `scope="row"`.
- Dekorative Pfeile und Abstandselemente sind mit `aria-hidden="true"`
  gekennzeichnet.
- Fokusmarkierungen dürfen nicht entfernt werden, sofern kein mindestens
  gleichwertiger Ersatz vorhanden ist.
- Text-/Hintergrundkontrast und Teamzuordnung müssen auch im Dark Mode und bei
  Farbsehschwäche nachvollziehbar bleiben.
- Horizontales Scrollen wird nur innerhalb breiter Tabellen und der Linkleiste
  erlaubt, nicht für die gesamte Seite.

## 11. Pflege- und Änderungsregeln

1. **Generator ändern:** Layoutänderungen in
   `src/usc_kommentatoren/report.py` vornehmen, nicht ausschließlich in der
   generierten `docs/index.html`.
2. **Beide Varianten erzeugen:** Nach Änderungen normale und App-Ausgabe
   regenerieren.
3. **Cascade beachten:** Das HTML enthält eine ältere Basisebene und eine später
   angehängte Matchcenter-Ebene. Gleich spezifische, spätere Regeln gewinnen.
4. **Tokens bevorzugen:** Wiederkehrende Farben, Schatten und Radien über
   Custom Properties statt als neue Einzelwerte ergänzen.
5. **Teamsemantik erhalten:** Heimteam grün/türkis, Gegner blau; Statusfarben
   für Zugänge/Abgänge/Verbleib nicht zweckentfremden.
6. **Responsive prüfen:** Mindestens bei 375, 720, 1050 und 1440 px testen.
7. **Interaktionen prüfen:** Navigation, alle `details`, Countdown, Stoppuhr und
   horizontale Tabellen-Scrollbereiche mit Maus und Tastatur testen.
8. **Druck und Farbschema prüfen:** Druckvorschau sowie helles und dunkles
   Betriebssystem-Farbschema kontrollieren.
9. **App-Variante gesondert prüfen:** Gemeinsame Basiskomponenten müssen in
   beiden Ausgaben funktionieren; Matchcenter-spezifische Elemente sind nur in
   `index.html` zu erwarten.
10. **Keine externen Layoutabhängigkeiten:** Das aktuelle Layout ist vollständig
   inline definiert und benötigt kein CSS-Framework oder Webfont-Netzwerk.

## 12. Abnahme-Checkliste

- [ ] Kein horizontaler Seitenüberlauf bei 375 px Breite.
- [ ] Navigation bleibt sticky und verdeckt keine angesprungenen Überschriften.
- [ ] Header, Kurzbriefing und Schnellübersicht zeigen aktuelle Spieldaten.
- [ ] Gegner- und Heimteamfarben sind konsistent.
- [ ] Live-Regie ist auf Desktop zweispaltig und mobil einspaltig.
- [ ] Countdown und Stoppuhr aktualisieren ihre sichtbaren sowie ARIA-Live-Werte.
- [ ] Sendeablauf lässt sich bei Platzmangel innerhalb seiner Hülle scrollen.
- [ ] Kader- und Transferköpfe verschwinden mobil; die Daten bleiben lesbar.
- [ ] Alle Accordions sind per Tastatur auf- und zuklappbar.
- [ ] Fokusrahmen sind auf allen interaktiven Elementen sichtbar.
- [ ] Dark Mode besitzt lesbare Texte und erkennbare Teamzuordnungen.
- [ ] Druckansicht blendet Bedienflächen aus und entfernt Kartenschatten.
- [ ] Gemeinsame Komponenten funktionieren in `index.html` und
  `index_app.html`; die abweichenden Seitenrahmen bleiben beabsichtigt.
