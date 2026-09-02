import json
import os
import sys
from pathlib import Path

import streamlit as st

root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
if root_dir in sys.path:
    sys.path.remove(root_dir)
sys.path.insert(0, root_dir)

from app.services import automation

st.set_page_config(page_title="MoneyPrinterTurbo Automation", page_icon="⏱️", layout="wide")

style_file = Path(root_dir) / "webui" / "styles.css"
if style_file.is_file():
    st.markdown(f"<style>{style_file.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

st.title("MoneyPrinterTurbo Automation Dashboard")
st.caption(
    "Configure daily YouTube Shorts generation, queue manual test actions, and inspect run history."
)

snapshot = automation.dashboard_snapshot()
settings = snapshot["settings"]
worker = snapshot["worker"]
prerequisites = snapshot["prerequisites"]
recent_runs = snapshot["recent_runs"]
latest_upload_candidate_run_id = snapshot.get("latest_upload_candidate_run_id", "")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Worker heartbeat", worker.get("heartbeat_at", "not started"))
col2.metric("Automation enabled", "Yes" if settings.get("enabled") else "No")
col3.metric("Next upload target", worker.get("next_upload_time", "n/a"))
col4.metric("Pending actions", str(worker.get("pending_actions", 0)))

with st.expander("Prerequisites and publishing requirements", expanded=True):
    st.write(
        "Current MoneyPrinterTurbo YouTube publishing uses Upload-Post. "
        "Connect and authorize your own YouTube channel in Upload-Post first, then confirm it below."
    )
    st.write(
        {
            "llm_provider": prerequisites.get("llm_provider") or "not set",
            "video_source": prerequisites.get("video_source"),
            "resolved_voice_name": prerequisites.get("voice_name"),
            "upload_post_configured": prerequisites.get("upload_post_configured"),
            "thumbnail_ready": prerequisites.get("thumbnail_ready"),
        }
    )

with st.form("automation_settings_form"):
    left, right = st.columns(2)
    with left:
        enabled = st.checkbox("Enable scheduled automation", value=bool(settings.get("enabled")))
        auto_generate = st.checkbox("Enable auto-generation", value=bool(settings.get("auto_generate")))
        auto_upload = st.checkbox("Enable auto-upload", value=bool(settings.get("auto_upload")))
        youtube_authorization_confirmed = st.checkbox(
            "I confirm I connected and authorized my own YouTube channel in Upload-Post",
            value=bool(settings.get("youtube_authorization_confirmed")),
        )
        niche = st.text_area("Niche", value=str(settings.get("niche", "")), height=120)
        language = st.text_input("Language", value=str(settings.get("language", "")))
        video_source = st.selectbox(
            "Video source",
            options=["pexels", "pixabay", "coverr", "openai_image"],
            index=["pexels", "pixabay", "coverr", "openai_image"].index(
                str(settings.get("video_source", "pexels"))
                if str(settings.get("video_source", "pexels")) in {"pexels", "pixabay", "coverr", "openai_image"}
                else "pexels"
            ),
        )
        voice_name = st.text_input(
            "Voice name override (optional)",
            value=str(settings.get("voice_name", "")),
            help="Leave empty to let automation choose a default voice from the selected language.",
        )
    with right:
        video_duration_seconds = st.number_input(
            "Video duration (seconds)",
            min_value=15,
            max_value=180,
            value=int(settings.get("video_duration_seconds", 45)),
            step=5,
        )
        daily_upload_time = st.text_input(
            "Daily upload time (HH:MM, server local time)",
            value=str(settings.get("daily_upload_time", "09:00")),
        )
        videos_per_day = st.number_input(
            "Number of videos per day",
            min_value=1,
            max_value=10,
            value=int(settings.get("videos_per_day", 1)),
            step=1,
        )
        title_description_style = st.text_area(
            "Title / description style",
            value=str(settings.get("title_description_style", "")),
            height=120,
        )
        thumbnail_enabled = st.checkbox(
            "Generate thumbnail artifact when image generation is configured",
            value=bool(settings.get("thumbnail_enabled", True)),
        )
        generation_retry_attempts = st.number_input(
            "Generation retry attempts",
            min_value=1,
            max_value=10,
            value=int(settings.get("generation_retry_attempts", 2)),
            step=1,
        )
        upload_retry_attempts = st.number_input(
            "Upload retry attempts",
            min_value=1,
            max_value=10,
            value=int(settings.get("upload_retry_attempts", 3)),
            step=1,
        )
        retry_backoff_minutes = st.number_input(
            "Retry backoff (minutes)",
            min_value=1,
            max_value=1440,
            value=int(settings.get("retry_backoff_minutes", 30)),
            step=1,
        )
    save_clicked = st.form_submit_button("Save automation settings", type="primary")

if save_clicked:
    saved = automation.update_settings(
        {
            "enabled": enabled,
            "auto_generate": auto_generate,
            "auto_upload": auto_upload,
            "youtube_authorization_confirmed": youtube_authorization_confirmed,
            "niche": niche,
            "language": language,
            "video_source": video_source,
            "voice_name": voice_name,
            "video_duration_seconds": int(video_duration_seconds),
            "daily_upload_time": daily_upload_time,
            "videos_per_day": int(videos_per_day),
            "title_description_style": title_description_style,
            "thumbnail_enabled": thumbnail_enabled,
            "generation_retry_attempts": int(generation_retry_attempts),
            "upload_retry_attempts": int(upload_retry_attempts),
            "retry_backoff_minutes": int(retry_backoff_minutes),
        }
    )
    st.success(f"Automation settings saved. Next upload target: {automation.next_upload_time(saved)}")
    st.rerun()

st.subheader("Manual actions")
action_col1, action_col2, action_col3 = st.columns([1, 1, 2])
if action_col1.button("Generate Now", type="primary"):
    action = automation.enqueue_action(automation.AUTOMATION_ACTION_GENERATE_NOW)
    st.success(f"Queued manual generation action: {action['action_id']}")

upload_target_run_id = action_col3.text_input(
    "Run ID for Upload Now (optional)",
    value=latest_upload_candidate_run_id,
    help="Leave the suggested run ID to upload the latest generated video that has not been uploaded yet.",
)
if action_col2.button("Upload Now"):
    action = automation.enqueue_action(
        automation.AUTOMATION_ACTION_UPLOAD_NOW,
        run_id=upload_target_run_id.strip(),
    )
    st.success(f"Queued manual upload action: {action['action_id']}")

st.subheader("Recent runs")
if not recent_runs:
    st.info("No automation runs yet. Start the worker and queue Generate Now or wait for the schedule.")
else:
    table_rows = []
    for run in recent_runs:
        table_rows.append(
            {
                "run_id": run.get("run_id"),
                "source": run.get("source"),
                "topic": run.get("video_subject"),
                "generation": run.get("generation_status"),
                "upload": run.get("upload_status"),
                "created_at": run.get("created_at"),
                "updated_at": run.get("updated_at"),
                "task_id": run.get("task_id", ""),
                "last_error": run.get("last_error", ""),
            }
        )
    st.dataframe(table_rows, use_container_width=True)

    run_options = {run.get("run_id"): run for run in recent_runs if run.get("run_id")}
    selected_run_id = st.selectbox(
        "Inspect run details",
        options=list(run_options.keys()),
    )
    if selected_run_id:
        st.code(json.dumps(run_options[selected_run_id], ensure_ascii=False, indent=2), language="json")
