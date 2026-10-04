import json
from pathlib import Path
import tempfile
import unittest

from qorgau.config import Settings
from qorgau.engine import Event, EventEngine, Observation
from qorgau.reports import export_report
from qorgau.security import SecurityMonitor, ShortcutTracker
from qorgau.storage import Database


class ShortcutTests(unittest.TestCase):
    def test_ctrl_copy_paste_each_press_and_repeat(self):
        tracker = ShortcutTracker()
        tracker.feed(0xA2, True)
        self.assertEqual(tracker.feed(0x43, True), ("copy", "Ctrl+C"))
        self.assertIsNone(tracker.feed(0x43, True))
        self.assertIsNone(tracker.feed(0x43, False))
        self.assertEqual(tracker.feed(0x43, True), ("copy", "Ctrl+C"))
        tracker.feed(0x43, False)
        self.assertEqual(tracker.feed(0x56, True), ("paste", "Ctrl+V"))
        tracker.feed(0x56, False)
        tracker.feed(0xA2, False)
        self.assertIsNone(tracker.feed(0x43, True))

    def test_alt_tab_forward_and_backward(self):
        tracker = ShortcutTracker()
        tracker.feed(0xA4, True)
        self.assertEqual(tracker.feed(9, True, 0x20), ("alt_tab", "Alt+Tab"))
        tracker.feed(9, False)
        tracker.feed(0xA0, True)
        self.assertEqual(tracker.feed(9, True, 0x20), ("alt_tab", "Alt+Shift+Tab"))
        tracker.feed(9, False)
        tracker.feed(0xA4, False)
        self.assertIsNone(tracker.feed(9, True))

    def test_alt_system_flag_with_modifier_held_before_start(self):
        tracker = ShortcutTracker()
        self.assertEqual(tracker.feed(9, True, 0x20), ("alt_tab", "Alt+Tab"))

    def test_altgr_is_not_ctrl_copy_or_paste(self):
        tracker = ShortcutTracker()
        tracker.feed(0xA2, True)
        tracker.feed(0xA5, True)
        for key in (0x43, 0x56):
            self.assertIsNone(tracker.feed(key, True, 0x20))
            tracker.feed(key, False, 0x20)

    def test_print_screen_regular_and_keyup_only(self):
        tracker = ShortcutTracker()
        self.assertEqual(tracker.feed(0x2C, True), ("screenshot", "Print Screen"))
        self.assertIsNone(tracker.feed(0x2C, True))
        self.assertIsNone(tracker.feed(0x2C, False))
        self.assertEqual(tracker.feed(0x2C, False), ("screenshot", "Print Screen"))

    def test_modified_print_screen_and_shift_paste(self):
        tracker = ShortcutTracker()
        tracker.feed(0x5B, True)
        self.assertEqual(tracker.feed(0x2C, True), ("screenshot", "Win+Print Screen"))
        tracker.feed(0x2C, False)
        tracker.feed(0x5B, False)
        tracker.feed(0xA3, True)
        tracker.feed(0xA1, True)
        self.assertEqual(tracker.feed(0x56, True), ("paste", "Ctrl+Shift+V"))

    def test_unmonitored_keys_not_retained(self):
        tracker = ShortcutTracker()
        for key in (0x41, 0x42, 0x44, 0x31, 0x20, 0x0D):
            self.assertIsNone(tracker.feed(key, True))
        self.assertEqual(tracker.held, set())

    def test_initial_left_control_can_be_released(self):
        tracker = ShortcutTracker([0xA2])
        tracker.feed(0xA2, False)
        self.assertIsNone(tracker.feed(0x43, True))

    def test_default_window_and_explicit_exam_binding(self):
        monitor = SecurityMonitor()
        monitor.bind_application(100)
        self.assertEqual(monitor.target, 100)
        monitor.external, monitor.target, monitor.title = True, 200, "Exam"
        monitor.bind_application(300)
        self.assertEqual((monitor.target, monitor.title), (200, "Exam"))

    def test_window_no_default_delay_but_user_delay_respected(self):
        engine = EventEngine(Settings())
        opened, _ = engine.update(Observation(people=1, window_away=True), 0.25)
        self.assertEqual([e.kind for e in opened], ["window"])
        engine = EventEngine(Settings(window_seconds=2))
        opened, _ = engine.update(Observation(people=1, window_away=True), 0.25)
        self.assertEqual(opened, [])

    def test_point_events_in_database_and_all_report_formats(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            db = Database(root / "test.sqlite3")
            try:
                session = db.start("Test", "Keyboard", "live", Settings())
                for at, kind in enumerate(("copy", "paste", "alt_tab", "screenshot")):
                    db.add_event(session, Event(kind, at, at, "Shortcut only"))
                db.finish(session, 5)
                for suffix in ("html", "csv", "json"):
                    export_report(db, session, root / f"report.{suffix}")
                payload = json.loads((root / "report.json").read_text(encoding="utf-8"))
                self.assertEqual(payload["review_priority"], 25)
                self.assertTrue(all(e["end"] == e["start"] for e in payload["events"]))
                for suffix in ("html", "csv"):
                    report = (root / f"report.{suffix}").read_text(encoding="utf-8-sig")
                    for chord in ("Ctrl+C", "Ctrl+V", "Alt+Tab", "Print Screen"):
                        self.assertIn(chord, report)
            finally:
                db.close()
