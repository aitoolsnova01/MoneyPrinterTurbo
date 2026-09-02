# AI Tools Nova — YouTube Content Engine (MoneyPrinterTurbo ke saath)

Yeh folder aapke channel **AI Tools Nova** ke liye ek complete, step-wise system hai:
AI tutorials + AI news + AI se earning — sab kuch MoneyPrinterTurbo se semi-automated
voiceover videos ke roop me.

```
aitoolsnova/
├── README.md                 <- yehi file (step-by-step SOP)
├── strategy.md               <- channel plan, 3 pillars, upload rhythm, monetization
├── prompts.md                <- LLM system prompts (Hinglish script, hooks, titles, SEO)
├── topics/                   <- har pillar ke liye ready topic lists (.txt)
│   ├── tutorials.txt
│   ├── news.txt
│   └── earning.txt
├── make_batch.py             <- topics .txt -> MoneyPrinterTurbo batch JSONL
├── auto_channel.py           <- daily short + long automation helper
├── channel.example.toml      <- automation config template
├── batches/                  <- generated JSONL manifests (git-ignore)
├── logs/                     <- cron / automation logs (git-ignore)
└── state/                    <- cursor + used-news tracking (git-ignore)
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

## Step 7 — Complete daily automation (1 Short + 1 Long)

Agar aapko **roz automatic 1 short aur 1 long video** chahiye, to is repo me ab
`aitoolsnova/auto_channel.py` helper diya gaya hai.

Yeh kya karta hai:
- **Short job** ke liye Google News RSS se latest AI headline pick karta hai
- **Long job** ke liye `topics/tutorials.txt` aur `topics/earning.txt` ko rotate karta hai
- Har job ka MoneyPrinterTurbo batch JSONL banata hai
- `cli.py` chala kar video generate karta hai
- Agar `config.toml` me Upload-Post configured hai to generated videos ko **YouTube par auto-upload** bhi kar deta hai

### 7.1 Channel automation config banao

```bash
cd /home/user/MoneyPrinterTurbo
cp aitoolsnova/channel.example.toml aitoolsnova/channel.toml
```

Phir `aitoolsnova/channel.toml` me yeh cheezein edit karo:
- `channel.url` → apna YouTube channel link
- `channel.name` → channel name
- `short.schedule_time` → short kis time chale
- `long.schedule_time` → long video kis time chale
- `rss_queries` → kis type ki AI news chahiye

### 7.2 Pehle planning check karo

```bash
python aitoolsnova/auto_channel.py plan --config aitoolsnova/channel.toml
```

Isse manifest banega aur console me dikhega ki aaj ka short aur long kis topic par hai.

### 7.3 Manual run test karo

```bash
python aitoolsnova/auto_channel.py run --config aitoolsnova/channel.toml --job short
python aitoolsnova/auto_channel.py run --config aitoolsnova/channel.toml --job long
```

### 7.4 YouTube auto-upload enable karo

Main `config.toml` ke `[app]` section me Upload-Post credentials bharne honge:

```toml
[app]
upload_post_enabled = true
upload_post_api_key = "YOUR_UPLOAD_POST_API_KEY"
upload_post_username = "YOUR_UPLOAD_POST_USERNAME"
upload_post_platforms = ["youtube"]
upload_post_auto_upload = true
upload_post_youtube_privacy_status = "public"
```

> Note: `auto_channel.py` channel ideas aur scheduling manage karta hai; actual video render aur
> YouTube upload ab bhi MoneyPrinterTurbo + Upload-Post se hoga.

### 7.5 Daily cron lines nikaalo

```bash
python aitoolsnova/auto_channel.py print-cron --config aitoolsnova/channel.toml
```

Example output kuch aisa hoga:

```cron
0 9 * * * cd /home/user/MoneyPrinterTurbo && /usr/bin/python3 aitoolsnova/auto_channel.py run --config aitoolsnova/channel.toml --job short >> /home/user/MoneyPrinterTurbo/aitoolsnova/logs/short.log 2>&1
0 18 * * * cd /home/user/MoneyPrinterTurbo && /usr/bin/python3 aitoolsnova/auto_channel.py run --config aitoolsnova/channel.toml --job long >> /home/user/MoneyPrinterTurbo/aitoolsnova/logs/long.log 2>&1
```

Un lines ko `crontab -e` me paste kar do. Bas phir roz automatic run hoga.

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

## Aage kya aur improve kar sakte hain

- Devanagari font auto-download + default set
- RSS source ko aur curated banana (TechCrunch AI, The Verge AI, India-specific feeds)
- Thumbnail/title generator add karna
- Shorts ke saath community-post automation bhi add karna

Agar chaho to next step me main **aapke actual channel link aur credentials ke hisaab se `channel.toml` bhar kar ready** bhi kar dunga.
