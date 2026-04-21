# CLAUDE.md — Project Source of Truth

This file is the authoritative brief for anyone (human or AI) working on this repository. If something here contradicts an earlier conversation, trust this file.

## What this project is

A CLI tool that turns long-form YouTube video scripts into a sequence of AI-generated story images. It splits each script into ~1000-word segments, uses Claude to generate image prompts, optionally generates a historically-consistent visual style per video, then calls the kie.ai API (NanoBanana 2 or NanoBanana Pro) to produce the images.

Primary user intent: produce story-driven images for long-form YouTube "sleep videos" where one consistent visual style is applied across every image of a given video.

## Entry points

- **[cli.py](cli.py)** — the interactive CLI. This is the primary, supported entry point. All new user-facing features should land here.
- **[script_to_images.py](script_to_images.py)** — older flag-driven CLI. Kept working for backward compatibility; do not extend it unless explicitly asked.
- **[nano_banana_pro_client.py](nano_banana_pro_client.py)** — thin client for the kie.ai image API. Imported by both entry points.
- **[kie_model_presets.py](kie_model_presets.py)** — parameter shapes for each kie.ai model (the two models differ: `google/nano-banana` uses `image_size`, `nano-banana-pro` uses `aspect_ratio` + `resolution`).

## Canonical folder layout

**Inside the user's working folder** (NOT inside the repo):

```
<working_folder>/
├── titles.txt                    # "<video_id>: <title>" per line
├── <video_id_1>/
│   ├── <video_id_1>.txt          # script; paragraphs separated by blank lines
│   ├── style_string.txt          # written by the tool
│   ├── image_prompts.json        # written by the tool
│   └── images/<seg>_<img>.png    # written by the tool
└── <video_id_2>/
    └── ...
```

**Inside the repo:**

- `config.json` — API keys, gitignored, created on first run
- `style_strings/*.txt` — reusable style presets (picked from a menu)

## Non-negotiable rules

1. **Never commit `config.json`.** It holds real Claude and kie.ai API keys. It is in `.gitignore` — keep it that way.
2. **Script file naming**: inside a `<video_id>` folder, the script must be named `<video_id>.txt`. Do not rename or infer from other files.
3. **Titles file** is `titles.txt` (plural) at the working folder root, not per-video.
4. **Style string saved per video** is the bare string only (no numbered reasoning). Downstream code appends it verbatim to each image prompt, with a 1000-character cap.
5. **Image prompt cap**: 1000 characters including the appended style. Truncate at word boundaries.
6. **People in images**: always middle ground or background, never foreground focus. This is encoded in both the prompt-generation system prompt and the style-generation system prompt — keep it in both places.
7. **No video prompts** in the new CLI (`cli.py`). The old script has that feature; do not add it to `cli.py` unless explicitly asked.

## Default settings

- Image resolution: `2K`, aspect ratio: `16:9`, format: `png` — hard-coded, not prompted.
- Segment target: 1000 words; first paragraph is kept intact, the rest is re-split at sentence boundaries.
- Claude models: **Opus** (`claude-opus-4-5-20251101`) for style generation, **Sonnet** (`claude-sonnet-4-5-20250929`) for image prompts.
- kie.ai submit delay: `KIE_SUBMIT_DELAY_SECONDS = 2.0` seconds between `create_task` calls. Raise if rate-limited.

## Behavioral contracts

- **Back-navigation**: every interactive prompt in `cli.py` accepts `b` / `back` to return to the previous step. The `ask*` / `pick_from_list` helpers return the `BACK` sentinel; steps must propagate it. Don't add prompts that bypass this.
- **Batch mode**: processes every video subfolder in the working folder. Can optionally use Anthropic's Message Batches API (50% cheaper, up to 24h turnaround). Batches are opt-in per run — the prompt makes the latency trade-off explicit.
- **Style scope**: one style per video is the default. In batch mode you may share one style across all videos, or generate per-video from titles.

## When extending this project

- Add new interactive steps to the `steps` list in `cli.py:main()`. Each step takes `state: Dict`, mutates it, and returns `"next"`, `"retry"`, `"retry_from_start"`, or `BACK`.
- New style presets go into `style_strings/` as `.txt` files; the filename (without extension) becomes the menu label.
- New kie.ai models: add a preset in `kie_model_presets.py` and wire into the model-pick step in `cli.py`.
- Do not introduce provider-neutral abstractions. This project uses Claude and kie.ai directly.

## When something goes wrong

- "No subfolders with `<id>/<id>.txt` found" → script filename must match folder name.
- "titles.txt is missing entries for…" → required only when generating styles from titles, not when picking a preset.
- kie.ai rate limits → raise `KIE_SUBMIT_DELAY_SECONDS` in `cli.py`.
- Batch API stuck in `processing` → that's expected; it polls every 15s and can legitimately take hours. To abort, Ctrl-C.
