from dataclasses import asdict
import unittest
from qorgau.config import Settings
from qorgau.engine import Event
from qorgau.product import event_matches, overview_stats, preset_settings, review_stats


class ProductTests(unittest.TestCase):
    def test_demo_results_do_not_inflate_exam_dashboard(self):
        sessions = [
            {"mode": "demo", "status": "completed", "event_count": 999, "duration": 9999},
            {"mode": "live", "status": "completed", "event_count": 4, "duration": 60},
            {"mode": "live", "status": "interrupted", "event_count": 2, "duration": 20}]
        self.assertEqual(overview_stats(sessions), {"live": 2, "demo": 1, "completed": 1, "events": 6, "duration": 80})
        self.assertEqual(overview_stats([])["live"], 0)

    def test_preset_preserves_camera_model_and_privacy_preferences(self):
        source = Settings(camera_index=3, confidence=.6, phone_confidence=.35, save_evidence=True)
        before = asdict(source)
        result = preset_settings(source, "responsive")
        self.assertEqual((result.camera_index, result.confidence, result.phone_confidence, result.save_evidence), (3, .6, .35, True))
        self.assertEqual(result.phone_seconds, .5)
        self.assertEqual(asdict(source), before)
        for key in ("balanced", "tolerant", "responsive"):
            preset_settings(source, key).validate()

    def test_search_combines_category_with_case_insensitive_event_details(self):
        event = Event("copy", 2, 2, "Нажато Ctrl+Shift+C")
        self.assertTrue(event_matches(event, "keyboard", "CTRL+SHIFT"))
        self.assertFalse(event_matches(event, "vision", "ctrl"))
        self.assertTrue(event_matches({"kind": "phone", "detail": "Телефонов: 1"}, "vision", "телефон"))
        self.assertFalse(event_matches(event, "all", "no such event"))

    def test_review_completion_counts_actual_decisions(self):
        self.assertEqual(review_stats([{"review": "pending"}, {"review": "confirmed"}, {"review": "dismissed"}, {"review": "pending"}]), {"pending": 2, "confirmed": 1, "dismissed": 1})
        self.assertEqual(review_stats([]), {"pending": 0, "confirmed": 0, "dismissed": 0})
