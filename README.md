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
4. Situationen, etwa „Fernseher an“
5. Schlafen
6. Hitzeschutz
7. Tagesablauf

Die oberste Stufe, die gerade zutrifft, gewinnt. Alle Räume werden im selben Takt entschieden,
gleiche Ziele fahren gleichzeitig, und jeder Raum zeigt als Entität, warum er so steht.

## Stand

Beta. Eingerichtet werden Haus und Räume, gerechnet wird mit Tagesablauf, Fenster, Schlafen,
Hitzeschutz und Handbetrieb, angezeigt werden je Raum Grund und Zielposition. Noch nicht
enthalten: Situationen, Sicherheit, Abendkühlung, Wecker, Regenschutz und Benachrichtigungen.

Versionen folgen dem Kalender wie bei Home Assistant: `2026.11.0` ist die Version vom November,
`2026.11.0-beta.1` eine Beta dafür. Die Nummer sagt, wann eine Version erschien, nicht für welche
Home-Assistant-Version sie gilt. Eine Beta wird stabil, wenn sie mindestens eine Woche ohne
Eingriff im Betrieb lief, auch mit der neuen Home-Assistant-Version des Monats.

## Installation (Beta)

1. In HACS beziehungsweise im Marketplace dieses Repository als benutzerdefiniertes Repository
   hinzufügen, Kategorie Integration.
2. Facade Conductor öffnen, „Beta-Versionen anzeigen“ einschalten und die neueste Beta laden.
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
per room (safety, manual, window, situation, sleep, heat protection, daily schedule), decides
all rooms in the same cycle, moves matching targets at the same time and exposes the reason
as an entity.

**Status:** beta. Houses and rooms can be set up; daily schedule, windows, sleep, heat protection
and manual moves are handled, and each room shows its reason and target position. Versions
follow the calendar like Home Assistant: `2026.11.0` is the November release.

**Installation (beta):** add this repository to HACS or the Marketplace as a custom repository
(category integration), enable "Show beta versions", download, restart Home Assistant and add
the Facade Conductor integration. Rooms are added and adjusted on the Facade Conductor page in
the sidebar. New setups start in **dry run**: reasons and target positions
are shown, nothing moves until you switch the operating mode to automatic. To receive later
betas as updates, enable the HACS "Pre-release" switch on the Facade Conductor device.

**Help:** please open an [issue](https://github.com/SekaiMedia/FaCo/issues).

---

Eine Integration von HiiragiSensei @ [SekaiMedia](https://sekaimedia.de) ·
Lizenz: [Apache 2.0](LICENSE)
