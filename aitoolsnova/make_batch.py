#!/usr/bin/env python3
"""Turn an AI Tools Nova topic list into a MoneyPrinterTurbo batch manifest.

Usage:
    python aitoolsnova/make_batch.py tutorials --count 5
    python aitoolsnova/make_batch.py news --count 3 --voice hi-IN-MadhurNeural-Male
    python aitoolsnova/make_batch.py earning --long --paragraphs 4

Then:
    python cli.py --batch-file aitoolsnova/batches/tutorials.jsonl --stop-at script
    python cli.py --batch-file aitoolsnova/batches/tutorials.jsonl --stop-at video
"""

from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOPICS_DIR = os.path.join(HERE, "topics")
BATCH_DIR = os.path.join(HERE, "batches")

TUTORIAL_PROMPT = (
    "Write a YouTube voiceover script in natural Hinglish (Hindi sentence structure, "
    "Roman script, common English tech words kept in English). "
    "Open with a one-sentence hook that shows the RESULT, not the tool name. "
    "Then name the tool and the exact problem it solves for an Indian student or freelancer. "
    "Give at most three concrete steps, each one short sentence. "
    "End with one line telling the viewer what they can now do. "
    "No emojis, no headings, no stage directions, no markdown. "
    "Keep sentences under 14 words so text-to-speech sounds natural. "
    "Never invent product features."
)

NEWS_PROMPT = (
    "Write a fast AI-news voiceover script in natural Hinglish (Roman script). "
    "Line one is the headline as a punchy hook in present tense. "
    "Then two or three factual sentences on what actually happened. "
    "Then a section starting with 'Aapke liye iska matlab' explaining the practical impact "
    "on an ordinary Indian user, student or freelancer. This part matters most. "
    "Close with one line inviting daily AI news subscribers. "
    "No emojis, no markdown, no speculation stated as fact. "
    "Phrase uncertain numbers, dates or names as reported, not confirmed. "
    "Keep sentences under 14 words."
)

EARNING_PROMPT = (
    "Write a YouTube voiceover script in natural Hinglish (Roman script) about earning money "
    "with AI, aimed at Indian viewers. "
    "Hook with a specific believable outcome in rupees, framed as an experiment or observation, "
    "never as a guarantee. "
    "Explain the actual skill and the actual deliverable the viewer would sell. "
    "Name a realistic Indian price range and where clients are found. "
    "Include one honest limitation or reason this fails for most people. "
    "End with the first small step someone can do today. "
    "No emojis, no markdown. Never promise income and never say guaranteed, passive, or "
    "anyone can. Keep sentences under 14 words."
)

PILLARS = {
    "tutorials": {
        "prompt": TUTORIAL_PROMPT,
        "voice": "hi-IN-SwaraNeural-Female",
        "paragraphs": 2,
        "clip_duration": 4,
    },
    "news": {
        "prompt": NEWS_PROMPT,
        "voice": "hi-IN-MadhurNeural-Male",
        "paragraphs": 1,
        "clip_duration": 3,
    },
    "earning": {
        "prompt": EARNING_PROMPT,
        "voice": "hi-IN-MadhurNeural-Male",
        "paragraphs": 2,
        "clip_duration": 4,
    },
}


def read_topics(pillar: str) -> list[tuple[str, str]]:
    path = os.path.join(TOPICS_DIR, f"{pillar}.txt")
    if not os.path.isfile(path):
        sys.exit(f"topic file not found: {path}")
    topics: list[tuple[str, str]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            subject, _, extra = line.partition("|")
            topics.append((subject.strip(), extra.strip()))
    if not topics:
        sys.exit(f"no usable topic lines in {path}")
    return topics


def build_task(pillar: str, subject: str, extra: str, args) -> dict:
    preset = PILLARS[pillar]
    prompt = preset["prompt"]
    if extra:
        prompt = f"{prompt} Additional direction for this video: {extra}."
    # video_script_prompt is capped at 2000 characters by VideoParams.
    prompt = prompt[:2000]

    return {
        "video_subject": subject,
        "video_script_prompt": prompt,
        "paragraph_number": args.paragraphs or preset["paragraphs"],
        "video_aspect": "16:9" if args.long else "9:16",
        "voice_name": args.voice or preset["voice"],
        "voice_rate": 0.95,
        "video_source": args.source,
        "video_concat_mode": "random",
        "video_transition_mode": "FadeIn",
        "video_clip_duration": preset["clip_duration"],
        "subtitle_enabled": True,
        "subtitle_position": "center" if not args.long else "bottom",
        "font_size": 72 if not args.long else 60,
        "text_fore_color": "#FFFFFF",
        "stroke_color": "#000000",
        "stroke_width": 2.0,
        "bgm_type": "random",
        "bgm_volume": 0.12,
        "video_count": 1,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pillar", choices=sorted(PILLARS), help="which topic list to use")
    parser.add_argument("--count", type=int, default=0, help="how many topics to take (0 = all)")
    parser.add_argument("--skip", type=int, default=0, help="skip the first N topics")
    parser.add_argument("--long", action="store_true", help="16:9 long-form instead of 9:16 Shorts")
    parser.add_argument("--voice", default="", help="override the voice name")
    parser.add_argument("--paragraphs", type=int, default=0, help="override paragraph count (1-10)")
    parser.add_argument("--source", default="pexels", help="material source (pexels, pixabay, local, ...)")
    parser.add_argument("--out", default="", help="output .jsonl path")
    args = parser.parse_args()

    if args.paragraphs and not 1 <= args.paragraphs <= 10:
        sys.exit("--paragraphs must be between 1 and 10")

    topics = read_topics(args.pillar)[args.skip:]
    if args.count:
        topics = topics[: args.count]
    if not topics:
        sys.exit("no topics left after --skip/--count")

    os.makedirs(BATCH_DIR, exist_ok=True)
    out_path = args.out or os.path.join(BATCH_DIR, f"{args.pillar}.jsonl")
    with open(out_path, "w", encoding="utf-8") as handle:
        for subject, extra in topics:
            task = build_task(args.pillar, subject, extra, args)
            handle.write(json.dumps(task, ensure_ascii=False) + "\n")

    rel = os.path.relpath(out_path, os.getcwd())
    print(f"wrote {len(topics)} task(s) to {rel}")
    print("\nnext steps:")
    print(f"  python cli.py --batch-file {rel} --stop-at script   # review scripts first")
    print(f"  python cli.py --batch-file {rel} --stop-at video    # render the videos")


if __name__ == "__main__":
    main()
