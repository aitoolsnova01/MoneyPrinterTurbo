import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import config
from app.services import automation


class TestAutomationService(unittest.TestCase):
    def setUp(self):
        self.original_automation = dict(config.automation)

    def tearDown(self):
        config.automation.clear()
        config.automation.update(self.original_automation)

    def test_load_settings_clamps_ranges_and_normalizes_time(self):
        with patch.dict(
            config.automation,
            {
                "enabled": True,
                "videos_per_day": 99,
                "video_duration_seconds": 5,
                "daily_upload_time": "25:99",
                "poll_interval_seconds": 1,
                "history_limit": 9999,
            },
            clear=True,
        ):
            settings = automation.load_settings()

        self.assertTrue(settings.enabled)
        self.assertEqual(settings.videos_per_day, 10)
        self.assertEqual(settings.video_duration_seconds, 15)
        self.assertEqual(settings.daily_upload_time, "09:00")
        self.assertEqual(settings.poll_interval_seconds, automation.AUTOMATION_MIN_POLL_INTERVAL_SECONDS)
        self.assertEqual(settings.history_limit, automation.AUTOMATION_MAX_HISTORY_LIMIT)

    def test_run_generation_records_successful_result(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            automation.utils,
            "storage_dir",
            return_value=temp_dir,
        ), patch.dict(
            config.automation,
            {
                "language": "en-US",
                "title_description_style": "clear and practical",
                "video_source": "pexels",
                "thumbnail_enabled": False,
            },
            clear=True,
        ), patch.object(
            automation,
            "_generate_topic",
            return_value="3 AI tools students should try",
        ), patch.object(
            automation.task_service,
            "start",
            return_value={
                "script": "Hook. Step one. Step two.",
                "terms": ["student laptop", "ai app"],
                "videos": ["/tmp/final-1.mp4"],
                "subtitle_path": "/tmp/sub.srt",
                "audio_file": "/tmp/audio.mp3",
                "materials": ["/tmp/m1.mp4"],
                "warnings": [],
            },
        ), patch.object(
            automation.llm,
            "generate_social_metadata",
            return_value={
                "title": "3 AI tools students should try",
                "caption": "Useful apps for faster study.",
                "hashtags": ["#aitools", "#students", "#shorts"],
            },
        ), patch.object(
            automation.material,
            "is_openai_image_enabled",
            return_value=False,
        ):
            settings = automation.load_settings()
            run = automation._create_run(settings, source="manual", upload_requested=False)
            result = automation.run_generation(run["run_id"], settings)

        self.assertEqual(result["generation_status"], automation.AUTOMATION_GENERATION_SUCCEEDED)
        self.assertEqual(result["upload_status"], automation.AUTOMATION_UPLOAD_NOT_REQUESTED)
        self.assertEqual(result["video_subject"], "3 AI tools students should try")
        self.assertEqual(result["publish_metadata"]["title"], "3 AI tools students should try")
        self.assertEqual(result["video_paths"], ["/tmp/final-1.mp4"])

    def test_run_upload_requires_explicit_authorization_confirmation(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            automation.utils,
            "storage_dir",
            return_value=temp_dir,
        ), patch.dict(
            config.automation,
            {
                "youtube_authorization_confirmed": False,
            },
            clear=True,
        ), patch.object(
            automation.upload_post.upload_post_service,
            "is_configured",
            return_value=True,
        ):
            settings = automation.load_settings()
            run = automation._create_run(settings, source="manual", upload_requested=True)
            run["generation_status"] = automation.AUTOMATION_GENERATION_SUCCEEDED
            run["video_paths"] = ["/tmp/final-1.mp4"]
            automation._save_run(run)

            result = automation.run_upload(run["run_id"], settings)

        self.assertEqual(
            result["upload_status"],
            automation.AUTOMATION_UPLOAD_AUTHORIZATION_REQUIRED,
        )
        self.assertTrue(any("Publishing blocked" in event["message"] for event in result["events"]))


if __name__ == "__main__":
    unittest.main()
