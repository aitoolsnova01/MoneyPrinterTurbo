# MoneyPrinterTurbo Automation Worker

This repository now includes a **persistent automation worker** for daily YouTube Shorts generation.
It is built on top of the existing MoneyPrinterTurbo pipeline instead of replacing it.

## Important current publishing limitation

The current MoneyPrinterTurbo YouTube publishing path in this codebase goes through **Upload-Post**.
That integration supports video upload plus YouTube title, description, tags, privacy, and the
`containsSyntheticMedia` flag. It does **not** currently expose a custom thumbnail upload field in
MoneyPrinterTurbo's code, so the automation worker generates a thumbnail artifact file when possible
but does not claim to upload it as a custom YouTube thumbnail.

## What it uses from MoneyPrinterTurbo

- topic/script generation: existing LLM provider integration in `app/services/llm.py`
- voiceover: existing TTS providers in `app/services/voice.py`
- subtitles/audio/video assembly: existing pipeline in `app/services/task.py`
- stock/AI visual assets: existing material providers in `app/services/material.py`
- YouTube publishing: existing Upload-Post integration in `app/services/upload_post.py`

## Components

- `automation_worker.py` — long-running scheduler/worker process
- `app/services/automation.py` — scheduler, run history, manual action queue, retries
- `webui/pages/Automation.py` — simple web dashboard page inside the Streamlit UI
- `.env.example` — example environment variable names for deployment secrets

## Scheduling model

The worker checks the configured `daily_upload_time` in the server's local timezone.
To avoid publishing too late, it starts generation **before** the target upload time using an internal lead buffer.
When generation succeeds, upload is triggered at or after the target upload time.

## Required publishing authorization

MoneyPrinterTurbo's current YouTube publishing integration uses **Upload-Post**.
You must:

1. Create your own Upload-Post account.
2. Connect and authorize your own YouTube channel inside Upload-Post.
3. Set the Upload-Post API key and username via environment variables or local config.
4. Explicitly confirm that authorization in the automation dashboard before automatic publishing is allowed.

This repository does **not** introduce a separate direct YouTube OAuth flow because the current MoneyPrinterTurbo codebase already publishes through Upload-Post.

## Running locally

```bash
cp .env.example .env
cp config.example.toml config.toml
# fill the non-secret automation settings in config.toml or the dashboard
# fill secret values in .env
python automation_worker.py
```

Open the Streamlit WebUI and use the **Automation** page to change niche, schedule, and manual actions.

## Deployment

Run the normal MoneyPrinterTurbo API/WebUI plus a third process:

```bash
python automation_worker.py
```

Keep `storage/` and `config.toml` on persistent storage. The worker stores run history in:

- `storage/automation/runs/*.json`
- `storage/automation/actions/*.json`
- `storage/automation/worker-status.json`

## Manual testing

- **Generate Now** queues a manual generation run.
- **Upload Now** queues an upload for the latest generated run that is not uploaded yet.

## Retry behavior

- generation retries use `generation_retry_attempts`
- upload retries use `upload_retry_attempts`
- retry delay uses `retry_backoff_minutes`

Every attempt and error is recorded in the run JSON event history.
