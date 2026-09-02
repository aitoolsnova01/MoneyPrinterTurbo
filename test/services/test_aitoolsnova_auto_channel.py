import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "aitoolsnova"))

import auto_channel


class TestAutoChannel(unittest.TestCase):
    def test_clean_rss_title_strips_trailing_source_suffix(self):
        self.assertEqual(
            auto_channel._clean_rss_title("OpenAI launches a new AI tool - TechCrunch"),
            "OpenAI launches a new AI tool",
        )
        self.assertEqual(
            auto_channel._clean_rss_title("AI market grows fast"),
            "AI market grows fast",
        )

    def test_select_rotating_topic_advances_job_rotation_and_topic_cursor(self):
        state = {"topic_cursors": {"tutorials": 0, "earning": 0}, "job_rotation_indices": {"long": 1}}
        job_cfg = {"topic_pillars": ["tutorials", "earning"]}

        with patch.object(auto_channel, "read_topics", return_value=[("Topic A", "Extra")]):
            pillar, subject, extra, next_cursor, next_rotation = auto_channel.select_rotating_topic(
                "long", job_cfg, state
            )

        self.assertEqual(pillar, "earning")
        self.assertEqual(subject, "Topic A")
        self.assertEqual(extra, "Extra")
        self.assertEqual(next_cursor, 0)
        self.assertEqual(next_rotation, 0)

    def test_apply_successful_state_updates_marks_only_successful_jobs(self):
        state = {
            "topic_cursors": {},
            "job_rotation_indices": {},
            "used_rss_guids": {},
            "used_rss_links": {},
            "last_success": {},
        }
        plans = [
            auto_channel.PlannedVideo(
                job_name="short",
                task={"video_subject": "Latest AI news"},
                source_label="RSS",
                selected_pillar="news",
                rss_guid="guid-1",
                rss_link="https://example.com/1",
            ),
            auto_channel.PlannedVideo(
                job_name="long",
                task={"video_subject": "Tutorial topic"},
                source_label="tutorials",
                selected_pillar="tutorials",
                topic_cursor_updates={"tutorials": 2},
                rotation_index_update=1,
            ),
        ]
        summary = {
            "tasks": [
                {"status": "succeeded"},
                {"status": "failed"},
            ]
        }

        changed = auto_channel.apply_successful_state_updates(state, plans, summary)

        self.assertTrue(changed)
        self.assertEqual(state["used_rss_guids"]["short"], ["guid-1"])
        self.assertEqual(state["used_rss_links"]["short"], ["https://example.com/1"])
        self.assertNotIn("tutorials", state["topic_cursors"])
        self.assertNotIn("long", state["job_rotation_indices"])
        self.assertEqual(state["last_success"]["short"]["video_subject"], "Latest AI news")

    def test_command_plan_writes_manifest(self):
        config_text = """
[channel]
name = "Demo"

[automation]
manifest_directory = "aitoolsnova/batches"
state_file = "aitoolsnova/state/test-state.json"

[short]
enabled = true
mode = "topic_rotation"
topic_pillars = ["tutorials"]
prompt_style = "tutorials"
voice_name = "hi-IN-SwaraNeural-Female"
paragraph_number = 1
video_aspect = "9:16"

[long]
enabled = false
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "channel.toml"
            config_path.write_text(config_text, encoding="utf-8")
            manifest_dir = Path(tmpdir) / "batches"
            state_path = Path(tmpdir) / "state.json"
            argv = [
                "plan",
                "--config",
                str(config_path),
                "--job",
                "short",
            ]
            with (
                patch.object(auto_channel, "manifest_path_for_job", return_value=manifest_dir / "daily-short.jsonl"),
                patch.object(auto_channel, "state_path_from_config", return_value=state_path),
                patch.object(auto_channel, "read_topics", return_value=[("Demo subject", "Demo extra")]),
            ):
                code = auto_channel.main(argv)

            self.assertEqual(code, 0)
            manifest = (manifest_dir / "daily-short.jsonl").read_text(encoding="utf-8")
            payload = json.loads(manifest.strip())
            self.assertEqual(payload["video_subject"], "Demo subject")
            self.assertEqual(payload["voice_name"], "hi-IN-SwaraNeural-Female")


if __name__ == "__main__":
    unittest.main()
