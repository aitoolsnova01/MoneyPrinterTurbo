#!/usr/bin/env python3
"""Daily automation helper for AI Tools Nova / MoneyPrinterTurbo.

Examples:
    python aitoolsnova/auto_channel.py plan --config aitoolsnova/channel.toml
    python aitoolsnova/auto_channel.py run --config aitoolsnova/channel.toml --job short
    python aitoolsnova/auto_channel.py print-cron --config aitoolsnova/channel.toml

The script intentionally uses only the Python standard library so it can run in the
same environment as MoneyPrinterTurbo without extra dependencies.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.11+ ships tomllib.
    tomllib = None  # type: ignore[assignment]

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
DEFAULT_CONFIG_PATH = HERE / "channel.toml"
DEFAULT_STATE_PATH = HERE / "state" / "channel-state.json"
DEFAULT_MANIFEST_DIR = HERE / "batches"
DEFAULT_GOOGLE_NEWS_QUERY = (
    'AI tools OR generative AI OR OpenAI OR Google Gemini OR Anthropic OR Midjourney'
)
SUPPORTED_PROMPT_STYLES = {"auto", "tutorials", "news", "earning"}
SUPPORTED_JOBS = {"short", "long"}
GOOGLE_NEWS_SEARCH_RSS = (
    "https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
)

# make_batch already contains the tuned prompt presets for this channel.
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from make_batch import PILLARS, build_task_from_profile, read_topics  # noqa: E402


@dataclass
class RssItem:
    title: str
    link: str
    guid: str
    source: str = ""
    published: str = ""


@dataclass
class PlannedVideo:
    job_name: str
    task: dict[str, Any]
    source_label: str
    selected_pillar: str
    rss_guid: str | None = None
    rss_link: str | None = None
    topic_cursor_updates: dict[str, int] = field(default_factory=dict)
    rotation_index_update: int | None = None


class AutoChannelError(RuntimeError):
    pass


def load_toml(path: Path) -> dict[str, Any]:
    if tomllib is None:
        raise AutoChannelError("Python 3.11+ is required for tomllib support")
    if not path.is_file():
        raise AutoChannelError(
            f"config file not found: {path}. Copy aitoolsnova/channel.example.toml first."
        )
    with path.open("rb") as handle:
        return tomllib.load(handle)


def load_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "topic_cursors": {},
            "job_rotation_indices": {},
            "used_rss_guids": {},
            "used_rss_links": {},
            "last_success": {},
        }
    with path.open("r", encoding="utf-8") as handle:
        try:
            payload = json.load(handle)
        except json.JSONDecodeError as exc:
            raise AutoChannelError(f"invalid state file JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise AutoChannelError(f"invalid state file structure: {path}")
    payload.setdefault("topic_cursors", {})
    payload.setdefault("job_rotation_indices", {})
    payload.setdefault("used_rss_guids", {})
    payload.setdefault("used_rss_links", {})
    payload.setdefault("last_success", {})
    return payload


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def _string_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    raise AutoChannelError(f"expected string or list of strings, got {type(value).__name__}")


def _int_from_config(value: Any, field_name: str) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError) as exc:
        raise AutoChannelError(f"invalid integer for {field_name}: {value!r}") from exc


def _channel_context(config_data: dict[str, Any]) -> str:
    channel = config_data.get("channel", {}) or {}
    name = str(channel.get("name", "AI Tools Nova") or "AI Tools Nova").strip()
    url = str(channel.get("url", "") or "").strip()
    audience = str(
        channel.get(
            "audience",
            "Indian students, freelancers, creators, and small business owners",
        )
        or ""
    ).strip()
    focus = str(
        channel.get(
            "focus",
            "AI tools, AI earning ideas, new AI launches, and practical AI news",
        )
        or ""
    ).strip()
    parts = [
        f'Channel name: {name}.',
        f'Audience: {audience}.',
        f'Content focus: {focus}.',
    ]
    if url:
        parts.append(f'Channel URL: {url}.')
    parts.append(
        "Speak in practical Hinglish for Indian viewers. Prioritize useful examples over hype."
    )
    return " ".join(parts)


def _effective_extra_instruction(
    config_data: dict[str, Any],
    job_name: str,
    job_cfg: dict[str, Any],
) -> str:
    automation_cfg = config_data.get("automation", {}) or {}
    channel_context = _channel_context(config_data)
    global_extra = str(automation_cfg.get("global_instruction", "") or "").strip()
    job_extra = str(job_cfg.get("extra_instruction", "") or "").strip()
    extras = [channel_context]
    if global_extra:
        extras.append(global_extra)
    if job_extra:
        extras.append(job_extra)
    extras.append(f"This is the daily {job_name} upload. Keep the script platform-ready.")
    return " ".join(extras)


def _clean_rss_title(title: str) -> str:
    cleaned = " ".join((title or "").split()).strip()
    if " - " in cleaned:
        head, _, tail = cleaned.rpartition(" - ")
        # News feeds commonly append the publisher at the end. Keep the source out of
        # the subject line so the generated script focuses on the news angle itself.
        if head and tail and len(tail) <= 40:
            cleaned = head.strip()
    return cleaned


def build_google_news_urls(queries: list[str]) -> list[str]:
    if not queries:
        queries = [DEFAULT_GOOGLE_NEWS_QUERY]
    urls: list[str] = []
    for query in queries:
        encoded = urllib.parse.quote_plus(query)
        urls.append(GOOGLE_NEWS_SEARCH_RSS.format(query=encoded))
    return urls


def fetch_rss_items(url: str, timeout: int = 20) -> list[RssItem]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        payload = response.read()
    root = ET.fromstring(payload)
    items: list[RssItem] = []
    for node in root.findall(".//item"):
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        guid = (node.findtext("guid") or link or title).strip()
        source = ""
        source_node = node.find("source")
        if source_node is not None and source_node.text:
            source = source_node.text.strip()
        published = (node.findtext("pubDate") or "").strip()
        if title:
            items.append(
                RssItem(
                    title=_clean_rss_title(title),
                    link=link,
                    guid=guid,
                    source=source,
                    published=published,
                )
            )
    return items


def select_rss_item(
    job_name: str,
    job_cfg: dict[str, Any],
    state: dict[str, Any],
) -> RssItem:
    queries = _string_list(job_cfg.get("rss_queries"))
    if not queries:
        single_query = str(job_cfg.get("rss_query", "") or "").strip()
        if single_query:
            queries = [single_query]
    urls = build_google_news_urls(queries)
    if not urls:
        raise AutoChannelError(f"{job_name}: no RSS query configured")

    used_guids = set(_string_list((state.get("used_rss_guids") or {}).get(job_name)))
    used_links = set(_string_list((state.get("used_rss_links") or {}).get(job_name)))
    fallback_item: RssItem | None = None

    for url in urls:
        items = fetch_rss_items(url)
        for item in items:
            if fallback_item is None:
                fallback_item = item
            if item.guid not in used_guids and item.link not in used_links:
                return item

    if fallback_item is not None:
        return fallback_item

    raise AutoChannelError(f"{job_name}: no RSS items found for configured queries")


def _normalize_topic_pillars(job_cfg: dict[str, Any]) -> list[str]:
    pillars = _string_list(job_cfg.get("topic_pillars"))
    if not pillars:
        single = str(job_cfg.get("topic_pillar", "") or "").strip()
        if single:
            pillars = [single]
    if not pillars:
        pillars = ["tutorials"]
    invalid = [pillar for pillar in pillars if pillar not in PILLARS]
    if invalid:
        raise AutoChannelError(f"unsupported topic pillars: {', '.join(invalid)}")
    return pillars


def select_topic(
    pillar: str,
    state: dict[str, Any],
) -> tuple[str, str, int]:
    topics = read_topics(pillar)
    cursor_map = state.get("topic_cursors") or {}
    raw_cursor = cursor_map.get(pillar, 0)
    try:
        cursor = int(raw_cursor)
    except (TypeError, ValueError):
        cursor = 0
    if cursor < 0:
        cursor = 0
    if cursor >= len(topics):
        cursor = 0
    subject, extra = topics[cursor]
    next_cursor = (cursor + 1) % len(topics)
    return subject, extra, next_cursor


def select_rotating_topic(
    job_name: str,
    job_cfg: dict[str, Any],
    state: dict[str, Any],
) -> tuple[str, str, str, int, int]:
    pillars = _normalize_topic_pillars(job_cfg)
    raw_index = (state.get("job_rotation_indices") or {}).get(job_name, 0)
    try:
        start_index = int(raw_index)
    except (TypeError, ValueError):
        start_index = 0
    if start_index < 0:
        start_index = 0

    pillar = pillars[start_index % len(pillars)]
    subject, extra, next_cursor = select_topic(pillar, state)
    next_rotation_index = (start_index + 1) % len(pillars)
    return pillar, subject, extra, next_cursor, next_rotation_index


def resolve_prompt_style(mode: str, source_pillar: str, job_cfg: dict[str, Any]) -> str:
    requested = str(job_cfg.get("prompt_style", "auto") or "auto").strip().lower()
    if requested not in SUPPORTED_PROMPT_STYLES:
        raise AutoChannelError(
            f"unsupported prompt_style '{requested}', choose from {sorted(SUPPORTED_PROMPT_STYLES)}"
        )
    if requested != "auto":
        return requested
    if mode == "rss":
        return "news"
    return source_pillar


def plan_job(
    config_data: dict[str, Any],
    job_name: str,
    state: dict[str, Any],
) -> PlannedVideo | None:
    if job_name not in SUPPORTED_JOBS:
        raise AutoChannelError(f"unsupported job name: {job_name}")

    job_cfg = dict(config_data.get(job_name, {}) or {})
    if not bool(job_cfg.get("enabled", False)):
        return None

    mode = str(job_cfg.get("mode", "topic_rotation") or "topic_rotation").strip().lower()
    if mode == "rss":
        item = select_rss_item(job_name, job_cfg, state)
        source_pillar = "news"
        subject = item.title
        extra = _effective_extra_instruction(config_data, job_name, job_cfg)
        prompt_pillar = resolve_prompt_style(mode, source_pillar, job_cfg)
        task = build_task_from_profile(
            pillar=prompt_pillar,
            subject=subject,
            extra=extra,
            long_form=str(job_cfg.get("video_aspect", "9:16")) == "16:9",
            voice=str(job_cfg.get("voice_name", "") or "").strip(),
            paragraphs=_int_from_config(
                job_cfg.get("paragraph_number", 0),
                f"{job_name}.paragraph_number",
            ),
            source=str(
                (config_data.get("automation", {}) or {}).get("video_source", "pexels")
            ),
        )
        task["video_aspect"] = str(job_cfg.get("video_aspect", task.get("video_aspect", "9:16")))
        task["video_subject"] = subject
        return PlannedVideo(
            job_name=job_name,
            task=task,
            source_label=item.source or "RSS",
            selected_pillar=prompt_pillar,
            rss_guid=item.guid,
            rss_link=item.link,
        )

    if mode == "topic_rotation":
        source_pillar, subject, extra, next_cursor, next_rotation_index = select_rotating_topic(
            job_name, job_cfg, state
        )
        prompt_pillar = resolve_prompt_style(mode, source_pillar, job_cfg)
        task = build_task_from_profile(
            pillar=prompt_pillar,
            subject=subject,
            extra=(
                f"{extra}. {_effective_extra_instruction(config_data, job_name, job_cfg)}"
                if extra
                else _effective_extra_instruction(config_data, job_name, job_cfg)
            ),
            long_form=str(job_cfg.get("video_aspect", "16:9")) == "16:9",
            voice=str(job_cfg.get("voice_name", "") or "").strip(),
            paragraphs=_int_from_config(
                job_cfg.get("paragraph_number", 0),
                f"{job_name}.paragraph_number",
            ),
            source=str(
                (config_data.get("automation", {}) or {}).get("video_source", "pexels")
            ),
        )
        task["video_aspect"] = str(job_cfg.get("video_aspect", task.get("video_aspect", "16:9")))
        task["video_subject"] = subject
        return PlannedVideo(
            job_name=job_name,
            task=task,
            source_label=source_pillar,
            selected_pillar=prompt_pillar,
            topic_cursor_updates={source_pillar: next_cursor},
            rotation_index_update=next_rotation_index,
        )

    raise AutoChannelError(
        f"{job_name}: unsupported mode '{mode}', use 'rss' or 'topic_rotation'"
    )


def write_manifest(path: Path, plans: list[PlannedVideo]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for plan in plans:
            handle.write(json.dumps(plan.task, ensure_ascii=False) + "\n")


def manifest_path_for_job(config_data: dict[str, Any], job_key: str) -> Path:
    automation_cfg = config_data.get("automation", {}) or {}
    raw_dir = str(automation_cfg.get("manifest_directory", DEFAULT_MANIFEST_DIR) or DEFAULT_MANIFEST_DIR)
    directory = Path(raw_dir)
    if not directory.is_absolute():
        directory = REPO_ROOT / directory
    return directory / f"daily-{job_key}.jsonl"


def state_path_from_config(config_data: dict[str, Any]) -> Path:
    automation_cfg = config_data.get("automation", {}) or {}
    raw_path = str(automation_cfg.get("state_file", DEFAULT_STATE_PATH) or DEFAULT_STATE_PATH)
    state_path = Path(raw_path)
    if not state_path.is_absolute():
        state_path = REPO_ROOT / state_path
    return state_path


def cli_stop_at_from_config(config_data: dict[str, Any]) -> str:
    stop_at = str((config_data.get("automation", {}) or {}).get("stop_at", "video") or "video").strip()
    return stop_at or "video"


def run_manifest(manifest_path: Path, stop_at: str) -> tuple[int, dict[str, Any] | None]:
    try:
        manifest_arg = str(manifest_path.relative_to(REPO_ROOT))
    except ValueError:
        manifest_arg = str(manifest_path)

    cmd = [sys.executable, "cli.py", "--batch-file", manifest_arg, "--stop-at", stop_at]
    process = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    if process.stderr:
        print(process.stderr, end="", file=sys.stderr)
    if process.stdout:
        print(process.stdout, end="")

    summary = None
    lines = [line for line in process.stdout.splitlines() if line.strip()]
    if lines:
        try:
            summary = json.loads(lines[-1])
        except json.JSONDecodeError:
            summary = None
    return process.returncode, summary


def apply_successful_state_updates(
    state: dict[str, Any],
    plans: list[PlannedVideo],
    summary: dict[str, Any] | None,
) -> bool:
    tasks = []
    if isinstance(summary, dict):
        payload = summary.get("tasks")
        if isinstance(payload, list):
            tasks = payload

    any_applied = False
    for index, plan in enumerate(plans):
        task_summary = tasks[index] if index < len(tasks) else None
        task_succeeded = isinstance(task_summary, dict) and task_summary.get("status") == "succeeded"
        if not task_succeeded:
            continue

        topic_cursors = state.setdefault("topic_cursors", {})
        for pillar, next_cursor in plan.topic_cursor_updates.items():
            topic_cursors[pillar] = next_cursor
            any_applied = True

        if plan.rotation_index_update is not None:
            state.setdefault("job_rotation_indices", {})[plan.job_name] = plan.rotation_index_update
            any_applied = True

        if plan.rss_guid:
            job_guid_list = state.setdefault("used_rss_guids", {}).setdefault(plan.job_name, [])
            if plan.rss_guid not in job_guid_list:
                job_guid_list.append(plan.rss_guid)
                del job_guid_list[:-200]
            any_applied = True
        if plan.rss_link:
            job_link_list = state.setdefault("used_rss_links", {}).setdefault(plan.job_name, [])
            if plan.rss_link not in job_link_list:
                job_link_list.append(plan.rss_link)
                del job_link_list[:-200]
            any_applied = True

        state.setdefault("last_success", {})[plan.job_name] = {
            "video_subject": plan.task.get("video_subject", ""),
            "source": plan.source_label,
            "prompt_style": plan.selected_pillar,
        }
        any_applied = True

    return any_applied


def plan_requested_jobs(
    config_data: dict[str, Any],
    job_selector: str,
    state: dict[str, Any],
) -> list[PlannedVideo]:
    if job_selector == "all":
        job_names = ["short", "long"]
    else:
        job_names = [job_selector]

    plans = [plan for job_name in job_names if (plan := plan_job(config_data, job_name, state))]
    if not plans:
        raise AutoChannelError("no enabled jobs were selected")
    return plans


def print_plan_summary(plans: list[PlannedVideo], manifest_path: Path) -> None:
    print(f"manifest: {manifest_path}")
    for plan in plans:
        print(
            f"- {plan.job_name}: {plan.task.get('video_subject', '')} "
            f"[{plan.source_label} | prompt={plan.selected_pillar} | aspect={plan.task.get('video_aspect')}]"
        )


def _cron_line(script_path: Path, config_path: Path, time_value: str, job_name: str) -> str:
    hour_text, minute_text = parse_schedule_time(time_value)
    try:
        config_arg = str(config_path.relative_to(REPO_ROOT))
    except ValueError:
        config_arg = str(config_path)
    try:
        script_arg = str(script_path.relative_to(REPO_ROOT))
    except ValueError:
        script_arg = str(script_path)
    log_dir = REPO_ROOT / "aitoolsnova" / "logs"
    return (
        f"{minute_text} {hour_text} * * * cd {REPO_ROOT} && "
        f"{sys.executable} {script_arg} run --config {config_arg} --job {job_name} "
        f">> {log_dir / (job_name + '.log')} 2>&1"
    )


def parse_schedule_time(value: str) -> tuple[str, str]:
    text = (value or "").strip()
    if not text:
        raise AutoChannelError("schedule_time cannot be empty")
    parts = text.split(":")
    if len(parts) != 2:
        raise AutoChannelError(f"invalid schedule_time: {value!r}")
    hour_text, minute_text = parts
    try:
        hour = int(hour_text)
        minute = int(minute_text)
    except ValueError as exc:
        raise AutoChannelError(f"invalid schedule_time: {value!r}") from exc
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise AutoChannelError(f"invalid schedule_time: {value!r}")
    return str(hour), str(minute)


def command_plan(args: argparse.Namespace) -> int:
    config_path = Path(args.config).resolve()
    config_data = load_toml(config_path)
    state = load_state(state_path_from_config(config_data))
    plans = plan_requested_jobs(config_data, args.job, state)
    manifest_path = manifest_path_for_job(config_data, args.job)
    write_manifest(manifest_path, plans)
    print_plan_summary(plans, manifest_path)
    return 0


def command_run(args: argparse.Namespace) -> int:
    config_path = Path(args.config).resolve()
    config_data = load_toml(config_path)
    state_path = state_path_from_config(config_data)
    state = load_state(state_path)
    plans = plan_requested_jobs(config_data, args.job, state)
    manifest_path = manifest_path_for_job(config_data, args.job)
    write_manifest(manifest_path, plans)
    print_plan_summary(plans, manifest_path)
    exit_code, summary = run_manifest(manifest_path, cli_stop_at_from_config(config_data))
    if apply_successful_state_updates(state, plans, summary):
        save_state(state_path, state)
    return exit_code


def command_print_cron(args: argparse.Namespace) -> int:
    config_path = Path(args.config).resolve()
    config_data = load_toml(config_path)
    for job_name in ("short", "long"):
        job_cfg = dict(config_data.get(job_name, {}) or {})
        if not bool(job_cfg.get("enabled", False)):
            continue
        schedule_time = str(job_cfg.get("schedule_time", "") or "").strip()
        if not schedule_time:
            raise AutoChannelError(f"{job_name}: schedule_time is required for print-cron")
        print(_cron_line(Path(__file__).resolve(), config_path, schedule_time, job_name))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("plan", "run"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument(
            "--config",
            default=str(DEFAULT_CONFIG_PATH),
            help="path to channel TOML config (copy channel.example.toml first)",
        )
        subparser.add_argument(
            "--job",
            choices=["short", "long", "all"],
            default="all",
            help="which daily job to plan or run",
        )
        subparser.set_defaults(handler=command_plan if command == "plan" else command_run)

    cron_parser = subparsers.add_parser("print-cron")
    cron_parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="path to channel TOML config (copy channel.example.toml first)",
    )
    cron_parser.set_defaults(handler=command_print_cron)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except AutoChannelError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
