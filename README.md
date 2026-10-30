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

In Entwicklung, noch keine Beta. Fertig ist die Entscheidungslogik mit Tests, die Anbindung an
Home Assistant folgt. Der Name kann sich bis zur ersten Beta noch ändern.

Betas erscheinen als Vorabversion und lassen sich in HACS beziehungsweise im Marketplace über
„Beta-Versionen anzeigen“ auswählen. Releases folgen, wenn eine Beta sich bewährt hat.

## Installation (Beta)

1. In HACS beziehungsweise im Marketplace dieses Repository als benutzerdefiniertes Repository
   hinzufügen, Kategorie Integration.
2. Facade Conductor öffnen, „Beta-Versionen anzeigen“ einschalten und die neueste Beta laden.
3. Home Assistant neu starten.
4. Einstellungen, Geräte und Dienste, Integration hinzufügen: Facade Conductor.
5. Das Haus einrichten, danach bei der Integration „Raum hinzufügen“.

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

**Status:** in development, no beta yet. The decision logic and its tests are done, the Home
Assistant integration follows. The name may still change before the first beta.

**Installation (beta):** add this repository to HACS or the Marketplace as a custom repository
(category integration), enable "Show beta versions", download, restart Home Assistant and add
the Facade Conductor integration. New setups start in **dry run**: reasons and target positions
are shown, nothing moves until you switch the operating mode to automatic.

**Help:** please open an [issue](https://github.com/SekaiMedia/FaCo/issues).

---

Eine Integration von HiiragiSensei @ [SekaiMedia](https://sekaimedia.de) ·
Lizenz: [Apache 2.0](LICENSE)
