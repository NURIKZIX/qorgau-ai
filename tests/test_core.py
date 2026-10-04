from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from qorgau.config import Settings
from qorgau.engine import Event, EventEngine, Observation, risk_score
from qorgau.storage import Database
from qorgau.reports import export_report


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = EventEngine(Settings())

    def feed(self, observation, start, end, step=0.25):
        opened, closed = [], []
        t = start
        while t <= end:
            a, b = self.engine.update(observation, t)
            opened.extend(a)
            closed.extend(b)
            t += step
        return opened, closed

    def test_phone_debounce_and_single_episode(self):
        opened, _ = self.feed(Observation(people=1, phones=1), 0, 8)
        self.assertEqual(len(opened), 1)
        self.assertEqual(opened[0].start, 0)
        _, closed = self.engine.update(Observation(people=1), 8.25)
        self.assertEqual(closed[0].duration, 8.25)

    def test_short_false_positive_is_ignored(self):
        self.feed(Observation(people=1, phones=1), 0, 1)
        opened, closed = self.engine.update(Observation(people=1), 1.25)
        self.assertEqual(opened + closed, [])

    def test_repeat_after_recovery_is_new_episode(self):
        self.feed(Observation(people=1, phones=1), 0, 2)
        self.engine.update(Observation(people=1), 2.25)
        opened, _ = self.feed(Observation(people=1, phones=1), 3, 5)
        self.assertEqual(len(opened), 1)
        self.assertEqual(opened[0].start, 3)

    def test_camera_error_is_not_absence(self):
        opened, _ = self.feed(Observation(camera_ok=False), 0, 10)
        self.assertEqual([e.kind for e in opened], ["camera"])
        self.assertEqual(risk_score(opened), 0)

    def test_face_prevents_false_absence(self):
        opened, _ = self.feed(Observation(people=0, faces=1), 0, 10)
        self.assertEqual(opened, [])

    def test_multiple_faces_even_when_yolo_finds_one(self):
        opened, _ = self.feed(Observation(people=1, faces=2), 0, 3)
        self.assertEqual([e.kind for e in opened], ["multiple"])

    def test_head_yaw_both_directions(self):
        for angle in (-40, 40):
            self.engine = EventEngine(Settings())
            opened, _ = self.feed(Observation(people=1, yaw=angle), 0, 4)
            self.assertEqual([e.kind for e in opened], ["head"])

    def test_window_requires_explicit_observation(self):
        opened, _ = self.feed(Observation(people=1, window_away=None), 0, 4)
        self.assertEqual(opened, [])
        opened, _ = self.feed(Observation(people=1, window_away=True), 4.25, 7)
        self.assertEqual([e.kind for e in opened], ["window"])

    def test_frame_gap_resets_pending_vision(self):
        self.feed(Observation(people=0), 0, 4)
        opened, _ = self.engine.update(Observation(people=0), 10)
        self.assertEqual(opened, [])
        opened, _ = self.feed(Observation(people=0), 10.25, 15.25)
        self.assertEqual([e.kind for e in opened], ["absence"])

    def test_gap_closes_active_at_last_observation(self):
        self.feed(Observation(people=1, phones=1), 0, 2)
        _, closed = self.engine.update(Observation(people=1, phones=1), 8)
        self.assertEqual(closed[0].end, 2)

    def test_finish_closes_all_active(self):
        self.feed(Observation(people=2, phones=1), 0, 3)
        closed = self.engine.finish(3.5)
        self.assertEqual(len(closed), 2)
        self.assertTrue(all(e.end == 3.5 for e in closed))
        self.assertEqual(self.engine.active, {})

    def test_backwards_time_rejected(self):
        self.engine.update(Observation(people=1), 1)
        with self.assertRaises(ValueError):
            self.engine.update(Observation(people=1), 0)

    def test_score_is_bounded(self):
        self.assertEqual(risk_score([Event("phone", 0)] * 20), 100)


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = Database(self.root/"test.db")
        self.session = self.db.start("<script>Имя & ID</script>", "Алгебра", "demo", Settings())

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_event_review_and_end_roundtrip(self):
        event = Event("phone", 2)
        self.db.add_event(self.session, event)
        event.end = 8
        self.db.close_event(event)
        self.db.review(event.id, "dismissed")
        self.db.finish(self.session, 9)
        row = self.db.events(self.session)[0]
        self.assertEqual((row["start"], row["end"], row["review"]), (2, 8, "dismissed"))
        self.assertEqual(self.db.session(self.session)["status"], "completed")

    def test_crash_recovery_uses_saved_duration(self):
        event = Event("absence", 1)
        self.db.add_event(self.session, event)
        self.db.heartbeat(self.session, 11)
        self.db.recover()
        self.assertEqual(self.db.session(self.session)["status"], "interrupted")
        self.assertEqual(self.db.events(self.session)[0]["end"], 11)

    def test_reports_escape_text_and_mark_demo(self):
        event = Event("head", 1, 5, "<img src=x onerror=alert(1)>")
        self.db.add_event(self.session, event)
        self.db.finish(self.session, 6)
        for suffix in ("html", "json", "csv"):
            export_report(self.db, self.session, self.root/f"report.{suffix}")
        html = (self.root/"report.html").read_text(encoding="utf-8")
        self.assertIn("ДЕМОРЕЖИМ", html)
        self.assertNotIn("<script>Имя", html)
        self.assertIn("&lt;img", html)
        payload = json.loads((self.root/"report.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["review_priority"], 5)
        self.assertEqual(payload["session"]["settings"]["confidence"], 0.45)
        self.assertEqual(payload["session"]["settings"]["phone_confidence"], 0.25)
        self.assertTrue((self.root/"report.csv").read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_sql_values_are_parameters(self):
        text = "'); DROP TABLE sessions; --"
        sid = self.db.start(text, text, "live", Settings())
        self.assertEqual(self.db.session(sid)["candidate"], text)
        self.assertEqual(len(self.db.sessions()), 2)

    def test_settings_malformed_falls_back(self):
        path = self.root/"settings.json"
        path.write_text('{"confidence": 4}', encoding="utf-8")
        self.assertEqual(Settings.load(path), Settings())
        Settings(camera_index=2).save(path)
        self.assertEqual(Settings.load(path).camera_index, 2)


if __name__ == "__main__":
    unittest.main()
