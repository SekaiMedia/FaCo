# Facade Conductor (FaCo)

**Deutsch** · [English](#english)

Eine Zentrale für Rollläden, Vorhänge und Fenster in Home Assistant.

## Wozu

Wer Rollläden mit einzelnen Automationen steuert, kennt die Folgen: Befehle gehen Raum für
Raum nacheinander raus, Automationen überschreiben sich gegenseitig, und niemand weiß, warum
ein Rollladen gerade so steht. Facade Conductor ersetzt diese Automationen durch eine feste
Rangfolge je Raum:

1. Sicherheit (Alarm, Rauch, Stromausfall, Schutz vor Wind und Frost)
2. Handbetrieb
3. Fenster gekippt oder offen
4. Situationen managen, etwa Fernseher an, Kinomodus, Sturm, Regenseite, Schlafen und mehr
5. Schlafen
6. Hitzeschutz
7. Tagesablauf

Die oberste Stufe, die gerade zutrifft, gewinnt. Alle Räume werden im selben Takt entschieden,
gleiche Ziele fahren gleichzeitig, und jeder Raum zeigt als Entität, warum er so steht.

## Stand

Beta. Eingerichtet werden Haus und Räume, gerechnet wird mit Tagesablauf, Fenster, Schlafen,
Hitzeschutz und Handbetrieb. Je Raum gibt es Grund, Zielposition, Fenster, Schlafen und einen
Schalter für den Handbetrieb. Geht die letzte Person und eine gewählte Tür oder ein Fenster ist
offen, kommt eine Push-Meldung. Situationen wie „Fernseher an“ oder ein Kinomodus halten einen Raum
oder fahren ihn auf eine feste Position. Ist ein Raum abends warm, bleibt er zum Abkühlen offen.
Alarmanlage, Rauchmelder oder Stromausfall fahren alle Räume, getrennt für „jemand zu Hause“ und
„Haus leer“. Ein Wecker öffnet einen Raum zur Weckzeit. Eigene Rollladen-Gruppen fürs Haus, je
Etage und je Raum fahren auch per Sprache im Gleichlauf. Vorhänge werden erkannt und bekommen
eigene Regeln, die Fensterrichtung lässt sich auf einer Karte festlegen, und auf Wunsch kommen
Meldungen, wenn ein Rollladen nicht erreichbar ist. Noch nicht enthalten: Regenschutz, Wind,
Urlaubsmodus und Durchsagen.

Versionen folgen dem Kalender wie bei Home Assistant: `2026.11.0` ist die Version vom November,
`2026.11.0-beta.1` eine Beta dafür. Die Nummer sagt, wann eine Version erschien, nicht für welche
Home-Assistant-Version sie gilt. Eine Beta wird stabil, wenn sie mindestens eine Woche ohne
Eingriff im Betrieb lief, auch mit der neuen Home-Assistant-Version des Monats.

## Installation (Beta)

1. Dieses Repository in HACS beziehungsweise im Marketplace hinzufügen:
   1. HACS öffnen, oben rechts auf die drei Punkte tippen und „Benutzerdefinierte Repositories“
      wählen.
   2. Bei „Repository“ diesen Link einfügen:

      ```
      https://github.com/SekaiMedia/FaCo
      ```

   3. Bei „Typ“ die Kategorie „Integration“ wählen und auf „Hinzufügen“ tippen.
2. Facade Conductor herunterladen:
   1. In HACS nach „Facade Conductor“ suchen und öffnen.
   2. Auf „Herunterladen“ tippen, „Beta-Versionen anzeigen“ einschalten und die neueste Beta
      wählen.
3. Home Assistant neu starten.
4. Damit HACS auch spätere Betas als Update anbietet: unter Geräte und Dienste, HACS, Gerät
   Facade Conductor den Schalter „Vorabversion“ aktivieren und einschalten. Sonst meldet HACS
   den Stand des Hauptzweigs als Update, und der ist älter als die Beta.
5. Einstellungen, Geräte und Dienste, Integration hinzufügen: Facade Conductor.
6. Das Haus einrichten. Danach erscheint „Facade Conductor“ in der Seitenleiste: Dort zeigt die
   Übersicht jeden Raum mit Position und Grund, unter „Räume“ werden Räume angelegt und eingestellt.

**Neu eingerichtet läuft alles im Probelauf.** Die Integration rechnet und zeigt je Raum
„Grund“ und „Zielposition“, fährt aber nichts. So lässt sie sich neben bestehenden
Automationen testen. Erst mit der Betriebsart „Automatik“ steuert sie die Rollläden. Dann
sollten die alten Automationen für dieselben Rollläden aus sein.

## Hilfe und Mitmachen

Fragen, Fehler und Ideen bitte als [Issue](https://github.com/SekaiMedia/FaCo/issues).

---

## English

One controller for shutters, curtains and windows in Home Assistant.

**Why:** Separate automations send commands room by room, overwrite each other and never
tell you why a shutter is where it is. Facade Conductor replaces them with a fixed priority
per room (safety, manual, window, situations such as TV on, cinema mode, storm, rain side,
sleep and more, heat protection, daily schedule), decides
all rooms in the same cycle, moves matching targets at the same time and exposes the reason
as an entity.

**Status:** beta. Houses and rooms can be set up; daily schedule, windows, sleep, heat protection
and manual moves are handled; each room has entities for reason, target position, window, sleep
and a manual switch. When the last person leaves while a chosen door or window is open, a push
message is sent. Situations such as "TV on" or a cinema mode hold a room or move it to a fixed
position. A room that is warm in the evening stays open to cool down. Alarm, smoke or power failure move
all rooms, an alarm clock opens a room at wake-up time, group covers for the house, each floor
and each room work by voice, curtains get their own rules and the window direction can be set
on a map. Versions follow the calendar like Home Assistant: `2026.11.0` is the November release.

**Installation (beta):**

1. Add this repository to HACS or the Marketplace:
   1. Open HACS, tap the three dots in the top right corner and choose "Custom repositories".
   2. Paste this link into "Repository":

      ```
      https://github.com/SekaiMedia/FaCo
      ```

   3. Choose "Integration" as "Type" and tap "Add".
2. Search for Facade Conductor in HACS, tap "Download", enable "Show beta versions" and pick
   the latest beta.
3. Restart Home Assistant and add the Facade Conductor integration.

Rooms are added and adjusted on the Facade Conductor page in
the sidebar. New setups start in **dry run**: reasons and target positions
are shown, nothing moves until you switch the operating mode to automatic. To receive later
betas as updates, enable the HACS "Pre-release" switch on the Facade Conductor device.

**Help:** please open an [issue](https://github.com/SekaiMedia/FaCo/issues).

---

Eine Integration von HiiragiSensei @ [SekaiMedia](https://sekaimedia.de) ·
Lizenz: [Apache 2.0](LICENSE)
