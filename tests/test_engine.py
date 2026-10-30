"""Fälle aus der Konzeptvorschau, gerechnet an einem Beispielhaus.

Positionen stammen aus einer bestehenden Rollladen-Automation, die
Sonnenwinkel gelten für Norddeutschland Mitte Juli.
"""

import importlib.util
import sys
import unittest
from pathlib import Path

# engine.py direkt laden: das Paket selbst braucht Home Assistant, die Logik nicht
_path = Path(__file__).parents[1] / "custom_components" / "facade_conductor" / "engine.py"
_spec = importlib.util.spec_from_file_location("facade_engine", _path)
_engine = importlib.util.module_from_spec(_spec)
sys.modules["facade_engine"] = _engine
_spec.loader.exec_module(_engine)

from facade_engine import (  # noqa: E402
    CommandLog,
    Decision,
    direction_range,
    phase_for,
    House,
    Hysteresis,
    Phase,
    Positions,
    Reason as R,
    RoomConfig,
    RoomState,
    Window,
    batch,
    decide,
    in_range,
    may_move,
    situation_active,
)

BUERO = RoomConfig(positions=Positions(shade=75), sun_azimuth=(120, 210))
KUECHE = RoomConfig(positions=Positions(dusk=40, night=25, tilted=45))
SCHLAF = RoomConfig(sun_azimuth=(60, 130))
WOHN = RoomConfig(sun_azimuth=(60, 130), sleep_pause=(11, 18))

MORGEN = House(Phase.DAY, 7.5, hot=True, sun_azimuth=77)
MITTAG = House(Phase.DAY, 13, hot=True, sun_azimuth=167)
DAEMMERUNG = House(Phase.DUSK, 21.25)
NACHT = House(Phase.NIGHT, 23.5)


def d(cfg, house, current, **state):
    return decide(cfg, RoomState(**state), house, current)


class Rangfolge(unittest.TestCase):
    def assertD(self, got: Decision, pos: int, reason: R):
        self.assertEqual((got.position, got.reason), (pos, reason))

    def test_a_morgen_heiss(self):
        self.assertD(d(BUERO, MORGEN, 0), 100, R.SCHEDULE)
        self.assertD(d(KUECHE, MORGEN, 25), 100, R.SCHEDULE)
        self.assertD(d(SCHLAF, MORGEN, 0), 70, R.HEAT)
        self.assertD(d(WOHN, MORGEN, 0), 70, R.HEAT)

    def test_b_mittag_heiss(self):
        self.assertD(d(BUERO, MITTAG, 100), 75, R.HEAT)
        self.assertD(d(KUECHE, MITTAG, 100), 100, R.SCHEDULE)
        self.assertD(d(SCHLAF, MITTAG, 70), 100, R.SCHEDULE)
        self.assertD(d(WOHN, MITTAG, 70), 100, R.SCHEDULE)

    def test_c_daemmerung(self):
        for cfg, pos in ((BUERO, 25), (KUECHE, 40), (SCHLAF, 25), (WOHN, 25)):
            self.assertD(d(cfg, DAEMMERUNG, 100), pos, R.SCHEDULE)

    def test_c2_hitzeschutz_nur_tagsueber(self):
        west = RoomConfig(sun_azimuth=(240, 300))
        heisser_abend = House(Phase.DUSK, 21, hot=True, sun_azimuth=290)
        self.assertD(d(west, heisser_abend, 100), 25, R.SCHEDULE)
        self.assertD(d(west, House(Phase.DAY, 19, hot=True, sun_azimuth=270), 100), 70, R.HEAT)

    def test_d_nacht(self):
        for cfg, pos in ((BUERO, 0), (KUECHE, 25), (SCHLAF, 0), (WOHN, 0)):
            self.assertD(d(cfg, NACHT, 25), pos, R.SCHEDULE)

    def test_e_nacht_gekippt(self):
        self.assertD(d(BUERO, NACHT, 25, window=Window.TILTED), 25, R.WINDOW_TILTED)
        self.assertD(d(KUECHE, NACHT, 40, window=Window.TILTED), 45, R.WINDOW_TILTED)
        self.assertD(d(SCHLAF, NACHT, 25, window=Window.TILTED), 25, R.WINDOW_TILTED)

    def test_f_g_morgen_schlafend_bleibt_zu(self):
        self.assertD(d(SCHLAF, MORGEN, 0, asleep=True), 0, R.SLEEP)
        self.assertD(d(WOHN, MORGEN, 0, asleep=True), 0, R.SLEEP)
        self.assertD(d(SCHLAF, MORGEN, 0, asleep=True, window=Window.TILTED), 25, R.WINDOW_TILTED)

    def test_h_n_mittagsschlaf_und_verbund_pause(self):
        self.assertD(d(SCHLAF, MITTAG, 100, asleep=True), 25, R.SLEEP)
        self.assertD(d(SCHLAF, MITTAG, 0, asleep=True), 0, R.SLEEP)
        self.assertD(d(WOHN, MITTAG, 0, asleep=True), 100, R.SCHEDULE)

    def test_i_situation_haelt_und_sicherheit_geht_vor(self):
        self.assertD(d(WOHN, MITTAG, 70, hold=70), 70, R.SITUATION)
        self.assertD(d(WOHN, MITTAG, 70, hold=70, safety=100), 100, R.SAFETY)
        self.assertD(d(WOHN, MITTAG, 100, hold=70), 70, R.SITUATION)
        self.assertFalse(situation_active(23.5, 7, 23))
        self.assertD(d(WOHN, NACHT, 70), 0, R.SCHEDULE)

    def test_j_hand_schlaegt_lueften(self):
        self.assertD(d(BUERO, NACHT, 25, window=Window.TILTED, manual=50), 50, R.MANUAL)

    def test_k_sicherheit(self):
        for cfg in (BUERO, KUECHE, SCHLAF, WOHN):
            self.assertD(d(cfg, NACHT, 0, safety=100, manual=50), 100, R.SAFETY)

    def test_m_abendkuehlung(self):
        self.assertD(d(SCHLAF, DAEMMERUNG, 100, warm=True), 100, R.EVENING_COOLING)
        self.assertD(d(SCHLAF, NACHT, 100, warm=True), 0, R.SCHEDULE)
        self.assertD(d(SCHLAF, DAEMMERUNG, 100, warm=True, asleep=True), 25, R.SLEEP)
        self.assertD(d(SCHLAF, MITTAG, 100, warm=True), 100, R.SCHEDULE)

    def test_o_q_drei_fensterzustaende(self):
        self.assertD(d(SCHLAF, NACHT, 0, window=Window.TILTED), 25, R.WINDOW_TILTED)
        self.assertD(d(SCHLAF, NACHT, 25, window=Window.OPEN), 25, R.WINDOW_OPEN)
        self.assertD(d(SCHLAF, NACHT, 25), 0, R.SCHEDULE)
        self.assertD(d(SCHLAF, DAEMMERUNG, 25, window=Window.OPEN), 100, R.WINDOW_OPEN)
        # Dämmerung steht schon auf 25 %, Schlafen und Spalt ändern nichts, also bleibt der Grund
        self.assertD(d(SCHLAF, DAEMMERUNG, 100, window=Window.OPEN, asleep=True), 25, R.SCHEDULE)
        tagsueber_offen = RoomConfig(open_at_night_is_gap=False)
        self.assertD(d(tagsueber_offen, NACHT, 0, window=Window.OPEN), 100, R.WINDOW_OPEN)


class Werkzeuge(unittest.TestCase):
    def test_gleichlauf_buendelt_nur_aenderungen(self):
        targets = {"buero": 25, "kueche": 40, "schlaf": 25, "wohn_r": 25, "wohn_l": 25, "flur": 100}
        current = {"buero": 100, "kueche": 100, "schlaf": 70, "wohn_r": 70, "wohn_l": 70, "flur": 99}
        self.assertEqual(
            batch(targets, current),
            {25: ["buero", "schlaf", "wohn_r", "wohn_l"], 40: ["kueche"]},
        )

    def test_ruhe_nach_fahrt(self):
        hitze = Decision(70, R.HEAT)
        self.assertFalse(may_move(hitze, last_auto_move=0, now=600))
        self.assertTrue(may_move(hitze, last_auto_move=0, now=1200))
        self.assertTrue(may_move(Decision(100, R.SAFETY), last_auto_move=0, now=1))
        self.assertTrue(may_move(Decision(25, R.WINDOW_TILTED), last_auto_move=0, now=1))

    def test_hysterese_gegen_wolken(self):
        h = Hysteresis(2500, 4000)
        self.assertEqual([h.update(v) for v in (6000, 3000, 2400, 3500, 3900, 4100)],
                         [False, False, True, True, True, False])

    def test_himmelsrichtung(self):
        self.assertEqual(direction_range("e"), (45, 135))
        self.assertEqual(direction_range("n"), (315, 45))
        self.assertTrue(in_range(10, *direction_range("n")))

    def test_tagesphase(self):
        self.assertEqual(phase_for(23.5, 23, 7, dark=True), Phase.NIGHT)
        self.assertEqual(phase_for(6.9, 23, 7, dark=False), Phase.NIGHT)
        self.assertEqual(phase_for(7.5, 23, 7, dark=True), Phase.NIGHT)  # Wintermorgen bleibt zu
        self.assertEqual(phase_for(7.5, 23, 7, dark=False), Phase.DAY)
        self.assertEqual(phase_for(17, 23, 7, dark=True), Phase.DUSK)
        self.assertEqual(phase_for(17, 23, 7, dark=False), Phase.DAY)

    def test_handbetrieb_erkennen(self):
        log = CommandLog(grace=120)
        self.assertTrue(log.is_manual("c", 100, 50, now=10))
        log.sent("c", now=10)
        self.assertFalse(log.is_manual("c", 100, 25, now=60))  # eigene Fahrt
        self.assertTrue(log.is_manual("c", 25, 60, now=200))  # später von Hand
        self.assertFalse(log.is_manual("c", 25, 26, now=300))  # Messrauschen
        self.assertFalse(log.is_manual("c", None, 26, now=300))  # Neustart

    def test_waehrend_der_fahrt_nicht_nachsenden(self):
        log = CommandLog(grace=120)
        log.sent("c", now=0, target=25)
        self.assertTrue(log.in_flight("c", 25, now=30))
        self.assertFalse(log.in_flight("c", 70, now=30))  # neues Ziel geht sofort raus
        self.assertFalse(log.in_flight("c", 25, now=130))  # nicht angekommen: nachsenden

    def test_winkel_mit_ueberlauf(self):
        self.assertTrue(in_range(350, 300, 30))
        self.assertTrue(in_range(10, 300, 30))
        self.assertFalse(in_range(180, 300, 30))
        self.assertTrue(situation_active(23.5, 22, 6))
        self.assertFalse(situation_active(12, 22, 6))


if __name__ == "__main__":
    unittest.main()
