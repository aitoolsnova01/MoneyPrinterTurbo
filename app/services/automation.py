from __future__ import annotations

import copy
import json
import os
import socket
import tempfile
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from loguru import logger

from app.config import config
from app.models.schema import VideoAspect, VideoParams
from app.services import llm, material, task as task_service, upload_post
from app.utils import utils

AUTOMATION_ACTION_GENERATE_NOW = "generate_now"
AUTOMATION_ACTION_UPLOAD_NOW = "upload_now"
AUTOMATION_GENERATION_PENDING = "pending"
AUTOMATION_GENERATION_RUNNING = "running"
AUTOMATION_GENERATION_SUCCEEDED = "succeeded"
AUTOMATION_GENERATION_FAILED = "failed"
AUTOMATION_UPLOAD_NOT_REQUESTED = "not_requested"
AUTOMATION_UPLOAD_PENDING = "pending"
AUTOMATION_UPLOAD_RUNNING = "running"
AUTOMATION_UPLOAD_SUCCEEDED = "succeeded"
AUTOMATION_UPLOAD_FAILED = "failed"
AUTOMATION_UPLOAD_AUTHORIZATION_REQUIRED = "authorization_required"
AUTOMATION_DEFAULT_NICHE = "AI tools and practical AI news"
AUTOMATION_DEFAULT_LANGUAGE = "en-US"
AUTOMATION_DEFAULT_DURATION_SECONDS = 45
AUTOMATION_DEFAULT_UPLOAD_TIME = "09:00"
AUTOMATION_DEFAULT_TITLE_STYLE = "Practical, curiosity-driven, trustworthy, no hype"
AUTOMATION_DEFAULT_VIDEO_SOURCE = "pexels"
AUTOMATION_DEFAULT_HISTORY_LIMIT = 200
AUTOMATION_MAX_HISTORY_LIMIT = 500
AUTOMATION_MIN_POLL_INTERVAL_SECONDS = 5
AUTOMATION_MAX_POLL_INTERVAL_SECONDS = 300
AUTOMATION_MAX_RECENT_TOPIC_MEMORY = 30
RUN_EVENT_LIMIT = 200


@dataclass(frozen=True)
class AutomationSettings:
    enabled: bool
    youtube_authorization_confirmed: bool
    auto_generate: bool
    auto_upload: bool
    niche: str
    language: str
    video_duration_seconds: int
    daily_upload_time: str
    videos_per_day: int
    title_description_style: str
    video_source: str
    voice_name: str
    thumbnail_enabled: bool
    generation_retry_attempts: int
    upload_retry_attempts: int
    retry_backoff_minutes: int
    poll_interval_seconds: int
    history_limit: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class AutomationError(RuntimeError):
    pass


def _automation_dir(sub_dir: str = "") -> Path:
    base = Path(utils.storage_dir("automation", create=True))
    if sub_dir:
        base = base / sub_dir
    base.mkdir(parents=True, exist_ok=True)
    return base


def _runs_dir() -> Path:
    return _automation_dir("runs")


def _actions_dir() -> Path:
    return _automation_dir("actions")


def _worker_status_file() -> Path:
    return _automation_dir() / "worker-status.json"


def _now() -> datetime:
    return datetime.now().astimezone()


def _iso_now() -> str:
    return _now().isoformat()


def _parse_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _parse_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _normalize_time_string(value: Any, default: str) -> str:
    text = str(value or default).strip()
    parts = text.split(":")
    if len(parts) != 2:
        return default
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return default
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        return default
    return f"{hour:02d}:{minute:02d}"


def load_settings() -> AutomationSettings:
    return AutomationSettings(
        enabled=_parse_bool(config.automation.get("enabled", False), False),
        youtube_authorization_confirmed=_parse_bool(
            config.automation.get("youtube_authorization_confirmed", False),
            False,
        ),
        auto_generate=_parse_bool(config.automation.get("auto_generate", True), True),
        auto_upload=_parse_bool(config.automation.get("auto_upload", True), True),
        niche=str(
            config.automation.get("niche", AUTOMATION_DEFAULT_NICHE)
            or AUTOMATION_DEFAULT_NICHE
        ).strip(),
        language=str(
            config.automation.get("language", AUTOMATION_DEFAULT_LANGUAGE)
            or AUTOMATION_DEFAULT_LANGUAGE
        ).strip(),
        video_duration_seconds=_parse_int(
            config.automation.get(
                "video_duration_seconds", AUTOMATION_DEFAULT_DURATION_SECONDS
            ),
            AUTOMATION_DEFAULT_DURATION_SECONDS,
            15,
            180,
        ),
        daily_upload_time=_normalize_time_string(
            config.automation.get("daily_upload_time", AUTOMATION_DEFAULT_UPLOAD_TIME),
            AUTOMATION_DEFAULT_UPLOAD_TIME,
        ),
        videos_per_day=_parse_int(
            config.automation.get("videos_per_day", 1),
            1,
            1,
            10,
        ),
        title_description_style=str(
            config.automation.get(
                "title_description_style", AUTOMATION_DEFAULT_TITLE_STYLE
            )
            or AUTOMATION_DEFAULT_TITLE_STYLE
        ).strip(),
        video_source=str(
            config.automation.get("video_source", AUTOMATION_DEFAULT_VIDEO_SOURCE)
            or AUTOMATION_DEFAULT_VIDEO_SOURCE
        ).strip(),
        voice_name=str(config.automation.get("voice_name", "") or "").strip(),
        thumbnail_enabled=_parse_bool(
            config.automation.get("thumbnail_enabled", True),
            True,
        ),
        generation_retry_attempts=_parse_int(
            config.automation.get("generation_retry_attempts", 2),
            2,
            1,
            10,
        ),
        upload_retry_attempts=_parse_int(
            config.automation.get("upload_retry_attempts", 3),
            3,
            1,
            10,
        ),
        retry_backoff_minutes=_parse_int(
            config.automation.get("retry_backoff_minutes", 30),
            30,
            1,
            1440,
        ),
        poll_interval_seconds=_parse_int(
            config.automation.get("poll_interval_seconds", 30),
            30,
            AUTOMATION_MIN_POLL_INTERVAL_SECONDS,
            AUTOMATION_MAX_POLL_INTERVAL_SECONDS,
        ),
        history_limit=_parse_int(
            config.automation.get("history_limit", AUTOMATION_DEFAULT_HISTORY_LIMIT),
            AUTOMATION_DEFAULT_HISTORY_LIMIT,
            10,
            AUTOMATION_MAX_HISTORY_LIMIT,
        ),
    )


def update_settings(values: dict[str, Any]) -> AutomationSettings:
    allowed_keys = {
        "enabled",
        "youtube_authorization_confirmed",
        "auto_generate",
        "auto_upload",
        "niche",
        "language",
        "video_duration_seconds",
        "daily_upload_time",
        "videos_per_day",
        "title_description_style",
        "video_source",
        "voice_name",
        "thumbnail_enabled",
        "generation_retry_attempts",
        "upload_retry_attempts",
        "retry_backoff_minutes",
        "poll_interval_seconds",
        "history_limit",
    }
    for key, value in values.items():
        if key not in allowed_keys:
            continue
        config.automation[key] = value

    sanitized = load_settings()
    for key, value in sanitized.as_dict().items():
        config.automation[key] = value

    config.save_config()
    config.reload_config()
    return load_settings()


def _read_json(path: Path, default):
    if not path.is_file():
        return default
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(f"failed to read automation JSON file: path={path}, error={exc}")
        return default


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".automation-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def _run_path(run_id: str) -> Path:
    return _runs_dir() / f"{run_id}.json"


def _append_event(run: dict[str, Any], level: str, message: str, **extra: Any) -> None:
    events = list(run.get("events") or [])
    event = {
        "at": _iso_now(),
        "level": level,
        "message": message,
    }
    if extra:
        event["details"] = extra
    events.append(event)
    del events[:-RUN_EVENT_LIMIT]
    run["events"] = events
    run["updated_at"] = event["at"]


def _save_run(run: dict[str, Any]) -> dict[str, Any]:
    run.setdefault("updated_at", _iso_now())
    _write_json_atomic(_run_path(run["run_id"]), run)
    return run


def get_run(run_id: str) -> dict[str, Any] | None:
    payload = _read_json(_run_path(run_id), None)
    return payload if isinstance(payload, dict) else None


def list_recent_runs(limit: int | None = None) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for path in sorted(_runs_dir().glob("*.json")):
        payload = _read_json(path, None)
        if isinstance(payload, dict):
            runs.append(payload)
    runs.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
    if limit:
        runs = runs[:limit]
    return runs


def _trim_history_if_needed(settings: AutomationSettings) -> None:
    runs = list_recent_runs()
    for obsolete in runs[settings.history_limit :]:
        run_id = obsolete.get("run_id")
        if run_id:
            try:
                _run_path(run_id).unlink(missing_ok=True)
            except OSError:
                logger.warning(f"failed to prune automation history: run_id={run_id}")


def _recent_topics(limit: int = AUTOMATION_MAX_RECENT_TOPIC_MEMORY) -> list[str]:
    subjects: list[str] = []
    for run in list_recent_runs(limit=limit * 2):
        subject = str(run.get("video_subject", "") or "").strip()
        if subject:
            subjects.append(subject)
        if len(subjects) >= limit:
            break
    return subjects


def _make_schedule_key(now: datetime, sequence_number: int) -> str:
    return f"{now.date().isoformat()}#{sequence_number}"


def _find_run_by_schedule_key(schedule_key: str) -> dict[str, Any] | None:
    for run in list_recent_runs(limit=AUTOMATION_MAX_HISTORY_LIMIT):
        if run.get("schedule_key") == schedule_key:
            return run
    return None


def _generation_lead_minutes(settings: AutomationSettings) -> int:
    # Start somewhat before the requested publish time so video rendering has a buffer.
    # The lead scales with target duration but remains bounded for predictability.
    return max(15, min(120, settings.video_duration_seconds))


def _scheduled_datetimes(settings: AutomationSettings, reference: datetime | None = None) -> tuple[datetime, datetime]:
    reference = reference or _now()
    hour_text, minute_text = settings.daily_upload_time.split(":", 1)
    upload_at = reference.replace(
        hour=int(hour_text),
        minute=int(minute_text),
        second=0,
        microsecond=0,
    )
    generate_at = upload_at - timedelta(minutes=_generation_lead_minutes(settings))
    return generate_at, upload_at


def next_upload_time(settings: AutomationSettings, reference: datetime | None = None) -> str:
    reference = reference or _now()
    _, upload_at = _scheduled_datetimes(settings, reference)
    if reference >= upload_at:
        _, upload_at = _scheduled_datetimes(settings, reference + timedelta(days=1))
    return upload_at.isoformat()


def _create_run(
    settings: AutomationSettings,
    *,
    source: str,
    sequence_number: int | None = None,
    schedule_key: str | None = None,
    upload_requested: bool = False,
) -> dict[str, Any]:
    run = {
        "run_id": f"run-{uuid4().hex[:12]}",
        "source": source,
        "sequence_number": sequence_number,
        "schedule_key": schedule_key,
        "created_at": _iso_now(),
        "updated_at": _iso_now(),
        "generation_status": AUTOMATION_GENERATION_PENDING,
        "upload_status": AUTOMATION_UPLOAD_PENDING if upload_requested else AUTOMATION_UPLOAD_NOT_REQUESTED,
        "upload_requested": bool(upload_requested),
        "generation_attempts": 0,
        "upload_attempts": 0,
        "last_error": "",
        "video_subject": "",
        "video_language": settings.language,
        "settings_snapshot": settings.as_dict(),
        "events": [],
    }
    _append_event(run, "info", f"Created {source} automation run")
    return _save_run(run)


def enqueue_action(action_type: str, run_id: str = "") -> dict[str, Any]:
    if action_type not in {AUTOMATION_ACTION_GENERATE_NOW, AUTOMATION_ACTION_UPLOAD_NOW}:
        raise AutomationError(f"unsupported automation action: {action_type}")
    action = {
        "action_id": f"action-{uuid4().hex[:12]}",
        "type": action_type,
        "run_id": run_id,
        "requested_at": _iso_now(),
    }
    action_path = _actions_dir() / f"{action['requested_at'].replace(':', '-')}--{action['action_id']}.json"
    _write_json_atomic(action_path, action)
    return action


def _consume_next_action() -> dict[str, Any] | None:
    for path in sorted(_actions_dir().glob("*.json")):
        payload = _read_json(path, None)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning(f"failed to remove automation action file: {path}")
        if isinstance(payload, dict):
            return payload
    return None


def _worker_status_snapshot() -> dict[str, Any]:
    payload = _read_json(_worker_status_file(), {})
    return payload if isinstance(payload, dict) else {}


def get_worker_status() -> dict[str, Any]:
    payload = _worker_status_snapshot()
    settings = load_settings()
    payload.setdefault("settings_enabled", settings.enabled)
    payload.setdefault("next_upload_time", next_upload_time(settings))
    payload.setdefault("upload_post_configured", upload_post.upload_post_service.is_configured())
    payload.setdefault("thumbnail_ready", material.is_openai_image_enabled())
    payload.setdefault("pending_actions", len(list(_actions_dir().glob("*.json"))))
    return payload


def _write_worker_status(**payload: Any) -> None:
    status = {
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
        "heartbeat_at": _iso_now(),
        **payload,
    }
    _write_json_atomic(_worker_status_file(), status)


def _language_prompt(settings: AutomationSettings) -> str:
    language = settings.language.strip().lower()
    if "hinglish" in language or language.startswith("hi"):
        return "Write in natural Hinglish using Roman script, with short spoken sentences."
    if language.startswith("en"):
        return "Write in clear conversational English with short spoken sentences."
    return f"Write in this language: {settings.language}. Keep the narration easy to speak aloud."


def _build_script_prompt(settings: AutomationSettings) -> str:
    target_words = max(60, min(180, int(settings.video_duration_seconds * 2.4)))
    return (
        f"Write a YouTube Shorts voiceover script for the niche '{settings.niche}'. "
        f"Target about {settings.video_duration_seconds} seconds and roughly {target_words} words. "
        "Start with a strong hook in the first sentence. Keep every sentence short and voiceover-friendly. "
        "Include one practical takeaway. No markdown, no bullet lists, no emojis, and no stage directions. "
        "Do not make unrealistic financial promises or invent product capabilities. "
        + _language_prompt(settings)
    )


def _resolved_voice_name(settings: AutomationSettings) -> str:
    if settings.voice_name:
        return settings.voice_name
    language = settings.language.strip().lower()
    if "hinglish" in language or language.startswith("hi"):
        return "hi-IN-MadhurNeural-Male"
    if language.startswith("en-in"):
        return "en-IN-NeerjaNeural-Female"
    if language.startswith("en"):
        return "en-US-JennyNeural-Female"
    return "en-US-JennyNeural-Female"


def _build_video_params(settings: AutomationSettings, video_subject: str) -> VideoParams:
    clip_duration = 3 if settings.video_duration_seconds <= 45 else 4
    return VideoParams(
        video_subject=video_subject,
        video_language=settings.language,
        paragraph_number=1,
        video_script_prompt=_build_script_prompt(settings),
        video_aspect=VideoAspect.portrait.value,
        video_source=settings.video_source,
        voice_name=_resolved_voice_name(settings),
        voice_rate=0.95,
        subtitle_enabled=True,
        subtitle_position="center",
        video_clip_duration=clip_duration,
        match_materials_to_script=True,
        font_size=72,
        text_fore_color="#FFFFFF",
        stroke_color="#000000",
        stroke_width=2.0,
        bgm_type="random",
        bgm_volume=0.12,
        video_count=1,
    )


def _generate_topic(settings: AutomationSettings) -> str:
    recent_topics = _recent_topics()
    ideas = llm.generate_topic_ideas(
        niche=settings.niche,
        language=settings.language,
        count=1,
        style_instruction=(
            "Prefer topics with strong curiosity, practical value, and topical relevance for YouTube Shorts."
        ),
        excluded_topics=recent_topics,
    )
    return (ideas[0] if ideas else settings.niche).strip()


def _maybe_generate_thumbnail(
    run: dict[str, Any],
    settings: AutomationSettings,
) -> str:
    if not settings.thumbnail_enabled:
        _append_event(run, "info", "Thumbnail generation is disabled")
        _save_run(run)
        return ""
    if not material.is_openai_image_enabled():
        _append_event(
            run,
            "warning",
            "Skipping thumbnail generation because OpenAI-compatible image settings are incomplete",
        )
        _save_run(run)
        return ""

    prompt = (
        f"YouTube Shorts thumbnail concept for {run.get('video_subject', '')}, "
        "portrait composition, bold focal subject, cinematic lighting, no text"
    )
    generated = material.generate_images_openai(
        search_term=prompt,
        minimum_duration=1,
        video_aspect=VideoAspect.portrait,
        save_dir=str(_automation_dir("thumbnails")),
    )
    if not generated:
        _append_event(run, "warning", "Thumbnail generation returned no images")
        _save_run(run)
        return ""

    thumbnail_path = str(generated[0].url)
    _append_event(run, "info", "Generated thumbnail image", thumbnail_path=thumbnail_path)
    run["thumbnail_path"] = thumbnail_path
    _save_run(run)
    return thumbnail_path


def _publish_via_upload_post(
    video_paths: list[str],
    video_subject: str,
    video_script: str,
    language: str,
    style_instruction: str,
    metadata: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    metadata = metadata or llm.generate_social_metadata(
        video_subject=video_subject,
        video_script=video_script,
        language=language,
        platform="youtube_shorts",
        style_instruction=style_instruction,
    )
    post_title = (
        metadata.get("caption")
        or metadata.get("title")
        or video_subject
        or "Check out this video! #shorts"
    )
    youtube_extra = {
        "youtube_title": metadata.get("title", video_subject),
        "youtube_description": metadata.get("caption", ""),
        "tags": metadata.get("hashtags", []),
        "privacyStatus": upload_post.upload_post_service.youtube_privacy_status,
        "containsSyntheticMedia": True,
    }
    results: list[dict[str, Any]] = []
    for video_path in video_paths:
        result = upload_post.cross_post_video(
            video_path=video_path,
            title=post_title,
            platforms=["youtube"],
            youtube_extra=youtube_extra,
        )
        if not isinstance(result, dict):
            result = {
                "success": False,
                "error": "Upload-Post returned an invalid response",
            }
        results.append(result)
    return results, metadata


def _mark_generation_failure(
    run: dict[str, Any],
    settings: AutomationSettings,
    error: str,
) -> dict[str, Any]:
    run["generation_status"] = AUTOMATION_GENERATION_FAILED
    run["last_error"] = error
    if run.get("generation_attempts", 0) < settings.generation_retry_attempts:
        next_retry_at = _now() + timedelta(minutes=settings.retry_backoff_minutes)
        run["next_generation_retry_at"] = next_retry_at.isoformat()
        _append_event(run, "error", "Video generation failed; retry scheduled", error=error)
    else:
        run["next_generation_retry_at"] = ""
        _append_event(run, "error", "Video generation failed; retries exhausted", error=error)
    return _save_run(run)


def _mark_upload_failure(
    run: dict[str, Any],
    settings: AutomationSettings,
    error: str,
) -> dict[str, Any]:
    run["upload_status"] = AUTOMATION_UPLOAD_FAILED
    run["last_error"] = error
    if run.get("upload_attempts", 0) < settings.upload_retry_attempts:
        next_retry_at = _now() + timedelta(minutes=settings.retry_backoff_minutes)
        run["next_upload_retry_at"] = next_retry_at.isoformat()
        _append_event(run, "error", "Upload failed; retry scheduled", error=error)
    else:
        run["next_upload_retry_at"] = ""
        _append_event(run, "error", "Upload failed; retries exhausted", error=error)
    return _save_run(run)


def run_generation(run_id: str, settings: AutomationSettings | None = None) -> dict[str, Any]:
    settings = settings or load_settings()
    run = get_run(run_id)
    if not run:
        raise AutomationError(f"run not found: {run_id}")

    run["generation_attempts"] = int(run.get("generation_attempts", 0)) + 1
    run["generation_status"] = AUTOMATION_GENERATION_RUNNING
    run["last_error"] = ""
    run.pop("next_generation_retry_at", None)
    _append_event(run, "info", "Starting automated video generation")
    _save_run(run)

    topic = _generate_topic(settings)
    run["video_subject"] = topic
    _append_event(run, "info", "Selected topic idea", video_subject=topic)
    _save_run(run)

    params = _build_video_params(settings, topic)
    task_id = utils.get_uuid()

    try:
        result = task_service.start(
            task_id=task_id,
            params=params,
            stop_at="video",
            cross_post_enabled_override=False,
        )
    except Exception as exc:
        logger.exception(f"automation generation crashed, run_id={run_id}, error={exc}")
        return _mark_generation_failure(run, settings, f"{type(exc).__name__}: {exc}")

    if not isinstance(result, dict) or not result or result.get("state") == task_service.const.TASK_STATE_FAILED:
        error = "generation returned an invalid result"
        if isinstance(result, dict):
            error = str(result.get("error") or error)
        return _mark_generation_failure(run, settings, error)

    metadata = llm.generate_social_metadata(
        video_subject=topic,
        video_script=result.get("script", ""),
        language=settings.language,
        platform="youtube_shorts",
        style_instruction=settings.title_description_style,
    )

    run.update(
        {
            "task_id": task_id,
            "generation_status": AUTOMATION_GENERATION_SUCCEEDED,
            "video_subject": topic,
            "video_script": result.get("script", ""),
            "video_terms": result.get("terms", []),
            "video_paths": result.get("videos", []),
            "subtitle_path": result.get("subtitle_path", ""),
            "audio_file": result.get("audio_file", ""),
            "material_paths": result.get("materials", []),
            "publish_metadata": metadata,
            "warnings": result.get("warnings", []),
            "last_error": "",
            "next_generation_retry_at": "",
        }
    )
    if run.get("upload_requested"):
        run["upload_status"] = AUTOMATION_UPLOAD_PENDING
    else:
        run["upload_status"] = AUTOMATION_UPLOAD_NOT_REQUESTED
    _append_event(run, "info", "Video generation completed successfully", task_id=task_id)
    _save_run(run)

    _maybe_generate_thumbnail(run, settings)
    return get_run(run_id) or run


def run_upload(run_id: str, settings: AutomationSettings | None = None) -> dict[str, Any]:
    settings = settings or load_settings()
    run = get_run(run_id)
    if not run:
        raise AutomationError(f"run not found: {run_id}")
    if run.get("generation_status") != AUTOMATION_GENERATION_SUCCEEDED:
        raise AutomationError("cannot upload before generation succeeds")
    if not run.get("video_paths"):
        raise AutomationError("no generated video paths are available for upload")
    if not upload_post.upload_post_service.is_configured():
        raise AutomationError(
            "Upload-Post is not configured. Set upload_post credentials via env vars or config.toml."
        )
    if not settings.youtube_authorization_confirmed:
        run["upload_status"] = AUTOMATION_UPLOAD_AUTHORIZATION_REQUIRED
        _append_event(
            run,
            "warning",
            "Publishing blocked until you confirm that your own YouTube channel is connected in Upload-Post",
        )
        return _save_run(run)

    run["upload_requested"] = True
    run["upload_attempts"] = int(run.get("upload_attempts", 0)) + 1
    run["upload_status"] = AUTOMATION_UPLOAD_RUNNING
    run["last_error"] = ""
    run.pop("next_upload_retry_at", None)
    _append_event(run, "info", "Starting YouTube upload via Upload-Post")
    _save_run(run)

    try:
        results, metadata = _publish_via_upload_post(
            video_paths=list(run.get("video_paths") or []),
            video_subject=str(run.get("video_subject", "") or ""),
            video_script=str(run.get("video_script", "") or ""),
            language=str(run.get("video_language", settings.language) or settings.language),
            style_instruction=settings.title_description_style,
            metadata=(
                copy.deepcopy(run.get("publish_metadata"))
                if isinstance(run.get("publish_metadata"), dict)
                else None
            ),
        )
    except Exception as exc:
        logger.exception(f"automation upload crashed, run_id={run_id}, error={exc}")
        return _mark_upload_failure(run, settings, f"{type(exc).__name__}: {exc}")

    failures = [item for item in results if not item.get("success")]
    run["publish_metadata"] = metadata
    run["upload_results"] = results
    if failures:
        error = "; ".join(
            str(item.get("error") or item.get("message") or "unknown upload error")
            for item in failures
        )
        return _mark_upload_failure(run, settings, error)

    run["upload_status"] = AUTOMATION_UPLOAD_SUCCEEDED
    run["last_error"] = ""
    run["published_at"] = _iso_now()
    run["next_upload_retry_at"] = ""
    _append_event(run, "info", "YouTube upload completed successfully")
    return _save_run(run)


def _latest_upload_candidate() -> dict[str, Any] | None:
    for run in list_recent_runs(limit=AUTOMATION_MAX_HISTORY_LIMIT):
        if run.get("generation_status") != AUTOMATION_GENERATION_SUCCEEDED:
            continue
        if run.get("upload_status") == AUTOMATION_UPLOAD_SUCCEEDED:
            continue
        if run.get("video_paths"):
            return run
    return None


def _parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _is_retry_due(status_value: str, next_retry_at: str, now: datetime) -> bool:
    if status_value not in {AUTOMATION_GENERATION_FAILED, AUTOMATION_UPLOAD_FAILED}:
        return False
    retry_at = _parse_iso_datetime(next_retry_at)
    return retry_at is not None and retry_at <= now


def _process_action(action: dict[str, Any], settings: AutomationSettings) -> bool:
    action_type = action.get("type")
    if action_type == AUTOMATION_ACTION_GENERATE_NOW:
        run = _create_run(settings, source="manual", upload_requested=False)
        run_generation(run["run_id"], settings)
        return True

    if action_type == AUTOMATION_ACTION_UPLOAD_NOW:
        run_id = str(action.get("run_id", "") or "").strip()
        run = get_run(run_id) if run_id else _latest_upload_candidate()
        if not run:
            logger.warning("manual Upload Now was requested but no generated run is available")
            return False
        run["upload_requested"] = True
        if run.get("upload_status") == AUTOMATION_UPLOAD_NOT_REQUESTED:
            run["upload_status"] = AUTOMATION_UPLOAD_PENDING
        _append_event(run, "info", "Manual upload was requested")
        _save_run(run)
        run_upload(run["run_id"], settings)
        return True

    raise AutomationError(f"unsupported action type: {action_type}")


def _run_due_follow_up_work(settings: AutomationSettings, now: datetime) -> bool:
    for run in list_recent_runs(limit=settings.history_limit):
        generation_status = str(run.get("generation_status", "") or "")
        upload_status = str(run.get("upload_status", "") or "")

        if generation_status == AUTOMATION_GENERATION_FAILED and _is_retry_due(
            generation_status,
            str(run.get("next_generation_retry_at", "") or ""),
            now,
        ):
            run_generation(run["run_id"], settings)
            return True

        if generation_status != AUTOMATION_GENERATION_SUCCEEDED or not run.get("upload_requested"):
            continue

        target_upload_at = _parse_iso_datetime(
            str(run.get("target_upload_at", "") or "")
        )
        upload_window_open = target_upload_at is None or target_upload_at <= now

        if upload_status == AUTOMATION_UPLOAD_FAILED and _is_retry_due(
            upload_status,
            str(run.get("next_upload_retry_at", "") or ""),
            now,
        ):
            run_upload(run["run_id"], settings)
            return True

        if (
            upload_status in {
                AUTOMATION_UPLOAD_PENDING,
                AUTOMATION_UPLOAD_AUTHORIZATION_REQUIRED,
            }
            and upload_window_open
            and settings.youtube_authorization_confirmed
        ):
            run_upload(run["run_id"], settings)
            return True

    return False


def _run_due_scheduled_job(settings: AutomationSettings, now: datetime) -> bool:
    if not settings.enabled or not settings.auto_generate:
        return False

    generate_at, upload_at = _scheduled_datetimes(settings, now)
    today = now.date().isoformat()

    for sequence in range(1, settings.videos_per_day + 1):
        schedule_key = f"{today}#{sequence}"
        run = _find_run_by_schedule_key(schedule_key)
        if run is None:
            if now < generate_at:
                return False
            scheduled_run = _create_run(
                settings,
                source="scheduled",
                sequence_number=sequence,
                schedule_key=schedule_key,
                upload_requested=settings.auto_upload,
            )
            scheduled_run["target_upload_at"] = upload_at.isoformat()
            _append_event(
                scheduled_run,
                "info",
                "Created scheduled daily run",
                target_upload_at=upload_at.isoformat(),
            )
            _save_run(scheduled_run)
            run_generation(scheduled_run["run_id"], settings)
            return True

        if run.get("generation_status") == AUTOMATION_GENERATION_FAILED and _is_retry_due(
            run.get("generation_status", ""), run.get("next_generation_retry_at", ""), now
        ):
            run_generation(run["run_id"], settings)
            return True

        if (
            settings.auto_upload
            and run.get("generation_status") == AUTOMATION_GENERATION_SUCCEEDED
            and run.get("upload_status") == AUTOMATION_UPLOAD_FAILED
            and _is_retry_due(run.get("upload_status", ""), run.get("next_upload_retry_at", ""), now)
        ):
            run_upload(run["run_id"], settings)
            return True

        if (
            settings.auto_upload
            and run.get("generation_status") == AUTOMATION_GENERATION_SUCCEEDED
            and run.get("upload_status") in {
                AUTOMATION_UPLOAD_PENDING,
                AUTOMATION_UPLOAD_AUTHORIZATION_REQUIRED,
            }
            and now >= upload_at
            and settings.youtube_authorization_confirmed
        ):
            run_upload(run["run_id"], settings)
            return True

    return False


def run_once() -> bool:
    config.reload_config()
    settings = load_settings()
    _trim_history_if_needed(settings)
    now = _now()

    action = _consume_next_action()
    if action is not None:
        _write_worker_status(state="processing_action", current_action=action)
        processed = _process_action(action, settings)
        _write_worker_status(state="idle", last_action=action, processed=processed)
        return processed

    processed = _run_due_follow_up_work(settings, now)
    if not processed:
        processed = _run_due_scheduled_job(settings, now)
    _write_worker_status(
        state="idle",
        processed=processed,
        settings_enabled=settings.enabled,
        next_upload_time=next_upload_time(settings, now),
    )
    return processed


def worker_loop(stop_event: threading.Event | None = None) -> None:
    logger.info("starting MoneyPrinterTurbo automation worker")
    while True:
        if stop_event is not None and stop_event.is_set():
            _write_worker_status(state="stopped")
            return
        try:
            run_once()
            settings = load_settings()
            wait_seconds = settings.poll_interval_seconds
        except Exception as exc:
            logger.exception(f"automation worker iteration failed: {exc}")
            _write_worker_status(state="error", last_error=f"{type(exc).__name__}: {exc}")
            wait_seconds = 30
        if stop_event is None:
            time.sleep(wait_seconds)
        else:
            stop_event.wait(wait_seconds)


def dashboard_snapshot() -> dict[str, Any]:
    settings = load_settings()
    latest_upload_candidate = _latest_upload_candidate()
    return {
        "settings": settings.as_dict(),
        "worker": get_worker_status(),
        "recent_runs": list_recent_runs(limit=25),
        "latest_upload_candidate_run_id": (
            latest_upload_candidate.get("run_id") if latest_upload_candidate else ""
        ),
        "prerequisites": {
            "upload_post_configured": upload_post.upload_post_service.is_configured(),
            "thumbnail_ready": material.is_openai_image_enabled(),
            "llm_provider": str(config.app.get("llm_provider", "") or ""),
            "video_source": settings.video_source,
            "voice_name": _resolved_voice_name(settings),
        },
    }
