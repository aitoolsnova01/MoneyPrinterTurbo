# Prompts — AI Tools Nova

Yeh prompts `make_batch.py` automatically har task ke `video_script_prompt` me daal deta hai.
Manually tweak karna ho to yahin edit karo aur script me copy karo.

---

## 1. Tutorial pillar — script prompt

```
Write a YouTube Shorts voiceover script in natural Hinglish (Hindi sentence structure,
Roman script, common English tech words kept in English).

Rules:
- Open with a 1-sentence hook that shows the RESULT, not the tool name.
- Then name the tool and the exact problem it solves for an Indian student or freelancer.
- Give at most 3 concrete steps. Each step one short sentence.
- End with one line telling the viewer what they can now do.
- Total 110-140 words. No emojis, no headings, no stage directions, no markdown.
- Sentences under 14 words so text-to-speech sounds natural.
- Never invent features. If unsure about a feature, describe the general capability.
```

Video terms (stock footage keywords) hamesha **English** me generate hone chahiye,
warna Pexels/Pixabay kuch nahi dhoondh paate. MoneyPrinterTurbo default se English terms
nikalta hai — us par kuch nahi karna.

---

## 2. News pillar — script prompt

```
Write a 45-second YouTube Shorts news script in natural Hinglish (Roman script).

Rules:
- Line 1: the headline as a punchy hook, present tense.
- Then 2-3 sentences of what actually happened, factual and specific.
- Then a clearly separated section starting with "Aapke liye iska matlab" that explains
  the practical impact on an ordinary Indian user, student or freelancer. This is the
  most important part.
- Close with one line inviting daily AI news subscribers.
- 100-130 words. No emojis, no markdown, no speculation stated as fact.
- If a number, date or company name is uncertain, phrase it as reported, not confirmed.
```

---

## 3. Earning pillar — script prompt

```
Write a YouTube script in natural Hinglish (Roman script) about earning money with AI,
aimed at Indian viewers.

Rules:
- Hook: a specific, believable outcome with a real number in rupees, framed as an
  experiment or observation, never as a guarantee.
- Explain the actual skill and the actual deliverable the viewer would sell.
- Name the realistic Indian price range and where clients are found.
- Include one honest limitation or reason this fails for most people.
- End with the first small step someone can do today.
- 130-160 words. No emojis, no markdown.
- Never promise income. Never say "guaranteed", "passive", or "anyone can".
```

---

## 4. Title / Description / Tags prompt (upload ke waqt)

```
You are a YouTube SEO assistant for a Hinglish AI-tools channel aimed at Indian viewers.

Given this script, return JSON with keys: title, description, tags.

- title: 50-60 characters, Hinglish, include one number or the word "free" or "kaise"
  when honest. No ALL CAPS, no clickbait that the script doesn't deliver.
- description: first two lines contain the main keyword and the concrete value.
  Then a blank line, then 3-5 bullet points of what's covered, then a line
  "Tools mentioned:" listing them, then a line inviting subscribes.
- tags: 10 tags, mixing Hindi-transliterated and English search terms.

Script:
<<<SCRIPT>>>
```

---

## 5. Hook rewriter (jab retention girti hai)

```
Rewrite only the first sentence of this Hinglish script into 5 alternative hooks.
Each under 12 words. Vary the angle: result-first, question, contrarian, number,
and "most people don't know". Return a plain numbered list.

Script first line: <<<LINE>>>
```

---

## 6. Custom system prompt (optional, `--custom-system-prompt` ke liye)

Agar poora control chahiye to `cli.py` ka `--custom-system-prompt` use karo:

```
You are a scriptwriter for "AI Tools Nova", a Hinglish YouTube channel for Indian
students and freelancers. Your voice is direct, warm and practical — like a friend
explaining something useful, not a news anchor. You never hype, never use emojis,
never write markdown, and never produce sentences longer than 14 words because the
output is fed straight into text-to-speech. You always end with one actionable line.
```
