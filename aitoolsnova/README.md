# AI Tools Nova — YouTube Content Engine (MoneyPrinterTurbo ke saath)

Yeh folder aapke channel **AI Tools Nova** ke liye ek complete, step-wise system hai:
AI tutorials + AI news + AI se earning — sab kuch MoneyPrinterTurbo se semi-automated
voiceover videos ke roop me.

```
aitoolsnova/
├── README.md              <- yehi file (step-by-step SOP)
├── strategy.md            <- channel plan, 3 pillars, upload rhythm, monetization
├── prompts.md             <- LLM system prompts (Hinglish script, hooks, titles, SEO)
├── topics/                <- har pillar ke liye ready topic lists (.txt)
│   ├── tutorials.txt
│   ├── news.txt
│   └── earning.txt
├── make_batch.py          <- topics .txt -> MoneyPrinterTurbo batch JSONL
└── batches/               <- generated JSONL manifests (yahin banenge)
```

---

## Step 0 — Ek baar ka setup (15 minute)

```bash
cd /home/user/MoneyPrinterTurbo
cp config.example.toml config.toml
```

`config.toml` me kam se kam yeh 2 cheezein bharni hain:

1. **LLM key** (script likhne ke liye) — `llm_provider` + uska api key.
   Sasta/free start: `moonshot` ya `openai` compatible koi bhi relay.
2. **Material key** (footage ke liye, free) — Pexels:
   ```toml
   pexels_api_keys = ["YOUR_PEXELS_KEY"]
   ```
   Key yahan se: https://www.pexels.com/api/

Voiceover ke liye kuch nahi chahiye — **Edge TTS free hai**, aur Hindi voices built-in hain:

| Voice name (CLI me aise hi likhna) | Kaisi lagti hai |
|---|---|
| `hi-IN-MadhurNeural-Male` | Male, news/authority tone — News + Earning pillar |
| `hi-IN-SwaraNeural-Female` | Female, friendly — Tutorials pillar |
| `en-IN-PrabhatNeural-Male` | Indian-English male (pure English videos) |
| `en-IN-NeerjaNeural-Female` | Indian-English female |

> Hinglish script ke liye `hi-IN-*` voices best hain — woh Roman English words bhi
> theek bolti hain. Poori list: `docs/voice-list.txt`.

WebUI se check karna ho:
```bash
sh webui.sh        # phir browser me khol lo
```

---

## Step 1 — Topic decide karo (5 min/din)

`aitoolsnova/topics/*.txt` khol ke line add/edit karo. **Ek line = ek video.**
Format simple hai:

```
Video subject | optional extra instruction
```

Example:
```
NotebookLM se 1 ghante ki study PDF ko 5 minute me kaise samjhein | beginner ke liye, 3 steps
```

News pillar ke liye har subah 10 min: X/Twitter, TechCrunch AI, ya Google News "AI"
dekh ke 3 fresh lines daal do. **News videos ki shelf-life 48 ghante hai — same din upload.**

---

## Step 2 — Batch manifest banao

```bash
cd /home/user/MoneyPrinterTurbo
python aitoolsnova/make_batch.py tutorials --count 5
python aitoolsnova/make_batch.py news --count 3
python aitoolsnova/make_batch.py earning --count 3
```

Yeh `aitoolsnova/batches/tutorials.jsonl` etc. banata hai, jisme har video ke liye
sahi voice, aspect ratio, subtitle style aur pillar-specific script prompt already set hai.

Useful flags:
- `--long` → 9:16 Shorts ki jagah 16:9 long-form (default Shorts hai)
- `--voice hi-IN-SwaraNeural-Female` → voice override
- `--paragraphs 4` → lamba script (Shorts ke liye 1-2 rakho)
- `--out mypath.jsonl`

Pehle sirf **script** dekhna hai (LLM cost bahut kam, footage download nahi hoga):

```bash
python cli.py --batch-file aitoolsnova/batches/tutorials.jsonl --stop-at script
```

Output JSON me har task ka script aata hai. Pasand na aaye to `prompts.md` ka prompt
tweak karo ya topic line me instruction badlo — phir dubara chalao.

---

## Step 3 — Poori video generate karo

```bash
python cli.py --batch-file aitoolsnova/batches/tutorials.jsonl --stop-at video
```

Videos yahan aayengi: `storage/tasks/<task-id>/final-1.mp4`
Summary JSON stdout par print hoti hai (total / succeeded / failed).

Ek hi video test karne ke liye batch ki zaroorat nahi:

```bash
python cli.py \
  --video-subject "Top 5 free AI tools for students in 2026" \
  --voice-name hi-IN-SwaraNeural-Female \
  --video-aspect 9:16 --paragraph-number 1 \
  --stop-at video
```

---

## Step 4 — Human touch (yehi channel ko bachata hai)

Raw AI video upload mat karo. Har video par 5-10 minute:

1. **Hook** — pehle 3 second apni awaaz/face ya bold text overlay se replace karo agar ho sake.
2. **Screen recording** — tutorial pillar me tool ka 10-15 sec actual screen clip daalo
   (stock footage ki jagah). Yeh CTR aur retention dono badhata hai.
3. **Thumbnail** — 3 words max + apna face/tool logo. Canva template ek baar bana lo.
4. **End card** — "Next video: <topic>" — session watch time badhta hai.

---

## Step 5 — Upload + SEO

Har video ke liye `prompts.md` ka **Title/Description/Tags prompt** LLM me daal ke output lo,
ya MoneyPrinterTurbo ka built-in social metadata use karo.

Rules:
- Title: 50-60 chars, ek number ya "kaise" ya "free" ho.
- Description: pehli 2 lines me keyword + video ka value; niche tool links (affiliate agar hai),
  timestamps, aur 3 related videos ke links.
- Tags: 8-12, mix of Hindi + English (`ai tools hindi`, `free ai tools 2026`, ...)
- Shorts: `#Shorts` title me nahi, description me.

---

## Step 6 — Weekly rhythm (realistic, burnout-free)

| Din | Kaam | Output |
|---|---|---|
| Mon | Tutorials batch (5 Shorts) generate + edit | 5 Shorts queue |
| Tue | 1 long-form tutorial (8-10 min) record + AI b-roll | 1 long video |
| Wed | News batch (3 Shorts) — same din upload | 3 Shorts |
| Thu | Earning pillar 1 long-form (case study style) | 1 long video |
| Fri | News batch + analytics review | 3 Shorts |
| Sat | Thumbnails + next week ke topics list | planning |
| Sun | Off / community post | — |

Target: **~10-12 Shorts + 2 long-form per week.** 90 din me 100+ videos = algorithm ko
enough data mil jayega.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `no material found` | Pexels key daalo, ya `--video-source pixabay`, ya English keywords use karo (stock sites Hindi terms nahi samajhte — isliye prompts English video terms nikaalte hain) |
| Hindi subtitles boxes dikh rahe | `--font-name` me Devanagari font do; `resource/fonts/` me apna `NotoSansDevanagari-Bold.ttf` daal do |
| Voice robotic | `--voice-rate 0.95`, aur script me chhote vaakya rakho (prompts already aisa karte hain) |
| Script bahut generic | `topics/*.txt` line me specific instruction add karo (number, audience, year) |
| LLM cost zyada | Pehle `--stop-at script` se batch chalao, accept hone par hi `--stop-at video` |

---

## Aage kya (mai kar sakta hoon)

- Devanagari font auto-download + default set
- Auto-upload to YouTube (repo me `upload_post.py` service already hai — usko wire kar dun?)
- News pillar ke liye RSS scraper jo roz `topics/news.txt` khud bhar de

Bolo, kaunsa pehle chahiye.
