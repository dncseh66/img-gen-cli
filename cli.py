"""
Interactive CLI for generating images from video scripts.

Workflow:
  1. Ask for a working folder containing:
       - <video_id>/<video_id>.txt   (script)
       - titles.txt                   (lines: "<video_id>: <title>")

Type 'b' or 'back' at any prompt to return to the previous step.
  2. Pick single video or batch.
  3. Pick image model (NanoBanana 2 default, or NanoBanana Pro).
  4. Pick images per 1000-word segment.
  5. Pick style (existing style file, or generate from title via Opus).
  6. In batch mode: optionally use Anthropic Message Batches API
     (50% cheaper, but can take up to 24h — don't use if urgent).
  7. Generate image prompts via Claude, append style, create images via kie.ai,
     save to <working_folder>/<video_id>/images/.

Config (API keys) lives in image_gen/config.json next to this file.
"""

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from anthropic import Anthropic

from nano_banana_pro_client import NanoBananaProClient
from kie_model_presets import GOOGLE_NANO_BANANA, NANO_BANANA_PRO


HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "config.json"
STYLE_STRINGS_DIR = HERE / "style_strings"

PROMPT_GEN_MODEL = "claude-sonnet-4-5-20250929"
STYLE_GEN_MODEL = "claude-opus-4-5-20251101"

DEFAULT_RESOLUTION = "2K"
DEFAULT_ASPECT_RATIO = "16:9"
DEFAULT_FORMAT = "png"

TARGET_WORDS_PER_SEGMENT = 1000

# Seconds to sleep between kie.ai create_task calls to avoid rate limits.
KIE_SUBMIT_DELAY_SECONDS = 2.0

STYLE_SYSTEM_PROMPT = """You are a visual historian and AI prompt engineering image generation expert. Your task is to define a consistent, historically authentic visual style to use when creating story-driven images for a long-form YouTube sleep video.

Based on the given video title, infer the historical time period the video covers, then define:
1. The dominant visual art style of that time
2. A description of the artistic medium (e.g. tapestry, propaganda poster, mosaic, ink scroll)
3. The typical color palette used in that era/style
4. The visual tone (e.g. dramatic, surreal, muted, saturated)
5. Any relevant artistic details (e.g. flat perspective, exaggerated features, use of texture, brush strokes, etc.)
6. A formatted, ready-to-use style string to include at the end of any image prompt
7. Include that if an image has people in it, they should always be in the middle ground or background, never in the foreground or the central focus of the image.
8. Confirm that all images must be 1920x1080 wide and contain no modern fonts or captions

After reasoning through 1-8, output ONLY the final style string (the item 6 output, augmented with items 7 and 8). Wrap it between the markers <STYLE_STRING> and </STYLE_STRING> on their own lines. Do not include any other text after </STYLE_STRING>."""

PROMPT_GEN_SYSTEM = """You are an expert at creating detailed, vivid image generation prompts for video scripts.

I am now going to provide you a segment of the video script. Generate descriptive image prompts that will accompany the voiceover of this script. These image prompts should be extremely descriptive and complement what is being said in the script. They set the scene and give the viewer a feel for what that time felt like. They do not need to exactly mimic the script, but must complement it.

For each image prompt:
- Be extremely descriptive about visual elements
- Include mood, atmosphere, composition, setting, environmental details
- Complement the voiceover without directly illustrating every word
- People, if present, must be in the background or middle ground, never in the foreground
- CRITICAL: Each prompt MUST NOT exceed 1000 characters
- Generate EXACTLY the requested number of prompts
- Return ONLY a valid JSON array of strings, nothing else"""


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

def load_or_create_config() -> Dict[str, str]:
    """Load config.json next to this file; prompt for any missing keys and save."""
    config: Dict[str, str] = {}
    if CONFIG_PATH.exists():
        try:
            config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"Warning: {CONFIG_PATH} is invalid JSON. Recreating.")
            config = {}

    changed = False
    if not config.get("claude_api_key"):
        config["claude_api_key"] = input("Enter Claude (Anthropic) API key: ").strip()
        changed = True
    if not config.get("kie_api_key"):
        config["kie_api_key"] = input("Enter KIE API key: ").strip()
        changed = True

    if changed:
        CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")
        print(f"Saved config to: {CONFIG_PATH}")

    return config


# --------------------------------------------------------------------------
# Input helpers
# --------------------------------------------------------------------------

BACK = "__BACK__"  # Sentinel returned by ask_* helpers when user types 'b' or 'back'.


def _is_back(raw: str) -> bool:
    return raw.lower() in ("b", "back")


def ask(prompt: str, default: Optional[str] = None, allow_back: bool = True):
    suffix = f" [{default}]" if default else ""
    hint = " (b=back)" if allow_back else ""
    while True:
        val = input(f"{prompt}{suffix}{hint}: ").strip()
        if allow_back and _is_back(val):
            return BACK
        if val:
            return val
        if default is not None:
            return default


def ask_int(prompt: str, default: Optional[int] = None, min_val: int = 1, allow_back: bool = True):
    while True:
        raw = ask(prompt, str(default) if default is not None else None, allow_back=allow_back)
        if raw is BACK:
            return BACK
        try:
            val = int(raw)
            if val < min_val:
                print(f"Must be >= {min_val}")
                continue
            return val
        except ValueError:
            print("Enter a number.")


def ask_yes_no(prompt: str, default: bool = False, allow_back: bool = True):
    d = "y" if default else "n"
    while True:
        raw = ask(prompt + " (y/n)", d, allow_back=allow_back)
        if raw is BACK:
            return BACK
        low = raw.lower()
        if low in ("y", "yes"):
            return True
        if low in ("n", "no"):
            return False
        print("Answer y or n.")


def pick_from_list(items: List[str], prompt: str, allow_back: bool = True):
    """Print a numbered list and return the chosen index (0-based), or BACK."""
    for i, item in enumerate(items, start=1):
        print(f"  [{i}] {item}")
    hint = " (b=back)" if allow_back else ""
    while True:
        raw = input(f"{prompt}{hint}: ").strip()
        if allow_back and _is_back(raw):
            return BACK
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(items):
                return idx
        except ValueError:
            pass
        print(f"Enter a number 1-{len(items)}.")


# --------------------------------------------------------------------------
# Working folder + title.txt
# --------------------------------------------------------------------------

def discover_videos(working_folder: Path) -> List[str]:
    """Return sorted list of subfolder names containing <name>/<name>.txt."""
    if not working_folder.is_dir():
        raise FileNotFoundError(f"Working folder not found: {working_folder}")

    videos: List[str] = []
    for sub in sorted(working_folder.iterdir()):
        if not sub.is_dir():
            continue
        if (sub / f"{sub.name}.txt").exists():
            videos.append(sub.name)
    return videos


def load_titles(working_folder: Path) -> Dict[str, str]:
    """Parse titles.txt in the working folder. Lines: '<video_id>: <title>' (colon or whitespace separator)."""
    path = working_folder / "titles.txt"
    titles: Dict[str, str] = {}
    if not path.exists():
        return titles

    for line_num, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^(\S+?)\s*[:\t]\s*(.+)$", line) or re.match(r"^(\S+)\s+(.+)$", line)
        if not m:
            print(f"Warning: titles.txt line {line_num} unparseable: {line!r}")
            continue
        titles[m.group(1).strip()] = m.group(2).strip()
    return titles


# --------------------------------------------------------------------------
# Script segmentation
# --------------------------------------------------------------------------

def read_paragraphs(script_path: Path) -> List[str]:
    raw = script_path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    paragraphs: List[str] = []
    current: List[str] = []
    for line in raw.split("\n"):
        if line.strip() == "":
            if current:
                paragraphs.append("\n".join(current).strip())
                current = []
        else:
            current.append(line)
    if current:
        paragraphs.append("\n".join(current).strip())
    return [p for p in paragraphs if p]


def split_sentences(text: str) -> List[str]:
    endings = re.compile(r"([.!?])(?:\s+|$)")
    sentences, last = [], 0
    for m in endings.finditer(text):
        s = text[last:m.end()].strip()
        if s:
            sentences.append(s)
        last = m.end()
    tail = text[last:].strip()
    if tail:
        sentences.append(tail)
    return sentences


def divide_into_segments(script_path: Path, target_words: int = TARGET_WORDS_PER_SEGMENT) -> List[str]:
    """First paragraph stays intact; rest is combined and re-split at sentence boundaries into ~target_words chunks."""
    paragraphs = read_paragraphs(script_path)
    if not paragraphs:
        return []

    segments = [paragraphs[0]]
    if len(paragraphs) == 1:
        return segments

    sentences = split_sentences(" ".join(paragraphs[1:]))
    cur: List[str] = []
    cur_words = 0
    for s in sentences:
        sw = len(s.split())
        would_exceed = cur_words + sw > target_words
        if cur_words >= target_words * 0.9 and would_exceed and cur:
            segments.append(" ".join(cur))
            cur, cur_words = [], 0
        cur.append(s)
        cur_words += sw
    if cur:
        segments.append(" ".join(cur))
    return segments


# --------------------------------------------------------------------------
# Style strings
# --------------------------------------------------------------------------

def list_style_files() -> List[Path]:
    if not STYLE_STRINGS_DIR.exists():
        STYLE_STRINGS_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(STYLE_STRINGS_DIR.glob("*.txt"))


def generate_style_string(claude: Anthropic, title: str) -> str:
    """Call Opus to generate a style string for a video title. Returns the bare style string."""
    user = f"Video title: \"{title}\""
    msg = claude.messages.create(
        model=STYLE_GEN_MODEL,
        max_tokens=2048,
        system=STYLE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user}],
    )
    text = msg.content[0].text
    # Extract between markers
    m = re.search(r"<STYLE_STRING>\s*(.+?)\s*</STYLE_STRING>", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # Fallback: take last non-empty paragraph
    paragraphs = [p.strip() for p in text.strip().split("\n\n") if p.strip()]
    return paragraphs[-1] if paragraphs else text.strip()


# --------------------------------------------------------------------------
# Image prompt generation
# --------------------------------------------------------------------------

def build_prompt_gen_user(segment: str, seg_num: int, num_images: int, full_script_ctx: Optional[str]) -> str:
    ctx = ""
    if full_script_ctx:
        ctx = (
            "You are given the full script context to help keep settings, locations, and details consistent.\n"
            "Do NOT repeat it in your output, use it only as background.\n\n"
            f"FULL SCRIPT CONTEXT:\n{full_script_ctx}\n\n---\n\n"
        )
    return (
        f"{ctx}SEGMENT {seg_num}:\n{segment}\n\n"
        f"Generate exactly {num_images} descriptive image prompt(s) for this script segment. "
        f"The images should be chronologically spaced through the segment. "
        f"Each prompt must be under 1000 characters. "
        f"Return a JSON array with exactly {num_images} prompt string(s)."
    )


def parse_prompt_array(text: str) -> List[str]:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [str(p) for p in data if p]
        if isinstance(data, str):
            return [data]
    except json.JSONDecodeError:
        pass
    # Fallback: pull quoted strings from first [...] block
    m = re.search(r"\[(.*?)\]", text, re.DOTALL)
    if m:
        strings = re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1))
        if strings:
            return strings
    return [text]


def enforce_prompt_limits(prompts: List[str], want: int) -> List[str]:
    out = []
    for p in prompts[:want]:
        if len(p) > 1000:
            p = p[:1000].rsplit(" ", 1)[0]
        out.append(p)
    return out


def generate_prompts_sequential(
    claude: Anthropic,
    jobs: List[Dict],
) -> Dict[str, List[str]]:
    """jobs: [{custom_id, segment, seg_num, num_images, full_script_ctx}] -> {custom_id: [prompts]}."""
    results: Dict[str, List[str]] = {}
    for job in jobs:
        user = build_prompt_gen_user(
            job["segment"], job["seg_num"], job["num_images"], job.get("full_script_ctx")
        )
        try:
            msg = claude.messages.create(
                model=PROMPT_GEN_MODEL,
                max_tokens=4096,
                system=PROMPT_GEN_SYSTEM,
                messages=[{"role": "user", "content": user}],
            )
            prompts = enforce_prompt_limits(
                parse_prompt_array(msg.content[0].text), job["num_images"]
            )
            results[job["custom_id"]] = prompts
        except Exception as e:
            print(f"  ✗ Prompt gen failed for {job['custom_id']}: {e}")
            results[job["custom_id"]] = []
    return results


def generate_prompts_via_batches(
    claude: Anthropic,
    jobs: List[Dict],
) -> Dict[str, List[str]]:
    """Submit all prompt-gen jobs as a single Message Batch, wait, and parse results."""
    from anthropic.types.messages.batch_create_params import Request
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming

    requests = []
    for job in jobs:
        user = build_prompt_gen_user(
            job["segment"], job["seg_num"], job["num_images"], job.get("full_script_ctx")
        )
        requests.append(
            Request(
                custom_id=job["custom_id"],
                params=MessageCreateParamsNonStreaming(
                    model=PROMPT_GEN_MODEL,
                    max_tokens=4096,
                    system=PROMPT_GEN_SYSTEM,
                    messages=[{"role": "user", "content": user}],
                ),
            )
        )

    print(f"Submitting Message Batch with {len(requests)} request(s)...")
    batch = claude.messages.batches.create(requests=requests)
    batch_id = batch.id
    print(f"Batch ID: {batch_id}")
    print("Polling for completion (batches may take up to 24h; typically minutes)...")

    while True:
        status = claude.messages.batches.retrieve(batch_id)
        if status.processing_status == "ended":
            break
        counts = status.request_counts
        print(
            f"  status={status.processing_status} "
            f"processing={counts.processing} succeeded={counts.succeeded} "
            f"errored={counts.errored} canceled={counts.canceled} expired={counts.expired}"
        )
        time.sleep(15)

    results: Dict[str, List[str]] = {job["custom_id"]: [] for job in jobs}
    want_by_id = {job["custom_id"]: job["num_images"] for job in jobs}
    for entry in claude.messages.batches.results(batch_id):
        cid = entry.custom_id
        if entry.result.type != "succeeded":
            print(f"  ✗ Batch entry {cid} failed: {entry.result.type}")
            continue
        text = entry.result.message.content[0].text
        results[cid] = enforce_prompt_limits(parse_prompt_array(text), want_by_id[cid])
    return results


# --------------------------------------------------------------------------
# Image generation pipeline
# --------------------------------------------------------------------------

def run_kie_generation(
    kie: NanoBananaProClient,
    prompts_by_video: Dict[str, List[List[str]]],
    video_output_dirs: Dict[str, Path],
    output_format: str,
    aspect_ratio: str,
    resolution: str,
) -> Dict[str, List[Dict]]:
    """
    prompts_by_video: {video_id: [[seg1 prompts], [seg2 prompts], ...]}
    Queues all tasks, then polls and downloads. Returns per-video image metadata.
    """
    pending: List[Dict] = []
    per_video: Dict[str, List[Dict]] = {vid: [] for vid in prompts_by_video}
    submitted_count = 0

    for video_id, segments in prompts_by_video.items():
        out_dir = video_output_dirs[video_id]
        out_dir.mkdir(parents=True, exist_ok=True)
        for seg_idx, prompts in enumerate(segments, start=1):
            for img_idx, prompt in enumerate(prompts, start=1):
                filename = f"{seg_idx}_{img_idx}.{output_format}"
                out_path = out_dir / filename
                if submitted_count > 0 and KIE_SUBMIT_DELAY_SECONDS > 0:
                    time.sleep(KIE_SUBMIT_DELAY_SECONDS)
                try:
                    task_id = kie.create_task(
                        prompt=prompt,
                        aspect_ratio=aspect_ratio,
                        resolution=resolution,
                        output_format=output_format,
                    )
                    submitted_count += 1
                    print(f"  [{video_id}] queued {filename} task={task_id}")
                    entry = {
                        "segment": seg_idx,
                        "image": img_idx,
                        "prompt": prompt,
                        "filename": filename,
                        "path": str(out_path),
                        "task_id": task_id,
                    }
                    per_video[video_id].append(entry)
                    pending.append({"video_id": video_id, "out_path": out_path, "entry": entry})
                except Exception as e:
                    print(f"  [{video_id}] ✗ queue failed {filename}: {e}")
                    per_video[video_id].append(
                        {
                            "segment": seg_idx,
                            "image": img_idx,
                            "prompt": prompt,
                            "filename": filename,
                            "path": str(out_path),
                            "error": str(e),
                        }
                    )

    print(f"\nWaiting for {len(pending)} image task(s) to complete...")
    for task in pending:
        tid = task["entry"]["task_id"]
        try:
            data = kie.wait_for_completion(tid)
            urls = kie.get_result_urls(data)
            if not urls:
                raise RuntimeError("No result URLs")
            img_bytes = kie._download_image(urls[0])
            task["out_path"].write_bytes(img_bytes)
            print(f"  ✓ {task['video_id']}/{task['out_path'].name}")
        except Exception as e:
            print(f"  ✗ {task['video_id']}/{task['out_path'].name}: {e}")
            task["entry"]["error"] = str(e)

    return per_video


# --------------------------------------------------------------------------
# Main interactive flow
# --------------------------------------------------------------------------

def _step_working_folder(state: Dict):
    wf_raw = ask("Working folder path", default=state.get("working_folder_raw"))
    if wf_raw is BACK:
        return BACK
    wf = Path(wf_raw.strip('"').strip("'")).expanduser()
    try:
        videos = discover_videos(wf)
    except FileNotFoundError as e:
        print(e)
        return "retry"
    if not videos:
        print("No subfolders with <id>/<id>.txt found.")
        return "retry"
    print(f"Found {len(videos)} video folder(s): {', '.join(videos)}")
    state["working_folder_raw"] = wf_raw
    state["working_folder"] = wf
    state["videos"] = videos
    return "next"


def _step_mode(state: Dict):
    idx = pick_from_list(["Single video", "Batch (all videos in folder)"], "Mode")
    if idx is BACK:
        return BACK
    state["is_batch"] = (idx == 1)
    if state["is_batch"]:
        state["selected_videos"] = list(state["videos"])
    else:
        state["selected_videos"] = None  # to be chosen in next step
    return "next"


def _step_pick_video(state: Dict):
    if state["is_batch"]:
        return "next"  # skip in batch mode
    idx = pick_from_list(state["videos"], "Pick video")
    if idx is BACK:
        return BACK
    state["selected_videos"] = [state["videos"][idx]]
    return "next"


def _step_image_model(state: Dict):
    idx = pick_from_list(
        ["NanoBanana 2 (google/nano-banana) [default]", "NanoBanana Pro (nano-banana-pro)"],
        "Image model",
    )
    if idx is BACK:
        return BACK
    state["kie_model"] = GOOGLE_NANO_BANANA if idx == 0 else NANO_BANANA_PRO
    return "next"


def _step_images_per_segment(state: Dict):
    n = ask_int("Images per 1000-word segment", default=state.get("images_per_segment", 2), min_val=1)
    if n is BACK:
        return BACK
    state["images_per_segment"] = n
    return "next"


def _step_style(state: Dict):
    working_folder: Path = state["working_folder"]
    selected_videos: List[str] = state["selected_videos"]
    is_batch: bool = state["is_batch"]

    titles = load_titles(working_folder)
    style_files = list_style_files()
    style_options = [f.stem for f in style_files] + ["[Generate from titles.txt per video]"]
    generate_idx = len(style_files)

    if is_batch:
        scope_idx = pick_from_list(
            ["Same style for all videos", "Generate style per video from titles.txt"],
            "Style scope",
        )
        if scope_idx is BACK:
            return BACK
        if scope_idx == 0:
            if not style_files:
                print("No existing style files; switching to per-video generation.")
                style_per_video_generate = True
                shared_style: Optional[str] = None
            else:
                pick = pick_from_list(style_options[:-1], "Pick style")
                if pick is BACK:
                    return BACK
                shared_style = style_files[pick].read_text(encoding="utf-8").strip()
                style_per_video_generate = False
        else:
            shared_style = None
            style_per_video_generate = True
    else:
        pick = pick_from_list(style_options, "Style")
        if pick is BACK:
            return BACK
        if pick == generate_idx:
            shared_style = None
            style_per_video_generate = True
        else:
            shared_style = style_files[pick].read_text(encoding="utf-8").strip()
            style_per_video_generate = False

    if style_per_video_generate:
        missing = [v for v in selected_videos if v not in titles]
        if missing:
            print(f"Error: titles.txt is missing entries for: {', '.join(missing)}")
            return "retry"

    state["titles"] = titles
    state["style_per_video_generate"] = style_per_video_generate
    state["shared_style"] = shared_style
    return "next"


def _step_batches_api(state: Dict):
    if not state["is_batch"]:
        state["use_batches_api"] = False
        return "next"
    ans = ask_yes_no(
        "Use Claude Message Batches API for prompt generation? "
        "(50% cheaper, may take up to 24h. If urgent, say no.)",
        default=False,
    )
    if ans is BACK:
        return BACK
    state["use_batches_api"] = ans
    return "next"


def _step_confirm(state: Dict):
    print("\n--- Review ---")
    print(f"  Working folder: {state['working_folder']}")
    print(f"  Mode: {'batch' if state['is_batch'] else 'single'}")
    print(f"  Videos: {', '.join(state['selected_videos'])}")
    print(f"  Image model: {state['kie_model']}")
    print(f"  Images per segment: {state['images_per_segment']}")
    if state["style_per_video_generate"]:
        print("  Style: generated per video from titles.txt (Opus)")
    else:
        print("  Style: shared, picked from style_strings/")
    if state["is_batch"]:
        print(f"  Batches API: {'yes' if state['use_batches_api'] else 'no'}")
    ans = ask_yes_no("Proceed?", default=True)
    if ans is BACK or ans is False:
        return BACK if ans is BACK else "retry_from_start"
    return "next"


def _run_pipeline(state: Dict, config: Dict, claude: Anthropic) -> int:
    working_folder: Path = state["working_folder"]
    selected_videos: List[str] = state["selected_videos"]
    titles: Dict[str, str] = state["titles"]
    images_per_segment: int = state["images_per_segment"]
    kie_model: str = state["kie_model"]
    style_per_video_generate: bool = state["style_per_video_generate"]
    shared_style: Optional[str] = state["shared_style"]
    use_batches_api: bool = state["use_batches_api"]

    # Resolve per-video styles
    per_video_style: Dict[str, str] = {}
    if style_per_video_generate:
        print("\nGenerating style string(s) via Opus...")
        for vid in selected_videos:
            title = titles[vid]
            print(f"  [{vid}] title: {title}")
            style = generate_style_string(claude, title)
            per_video_style[vid] = style
            # Save per video
            (working_folder / vid / "style_string.txt").write_text(style + "\n", encoding="utf-8")
            print(f"  [{vid}] saved style_string.txt ({len(style)} chars)")
    else:
        for vid in selected_videos:
            per_video_style[vid] = shared_style or ""
            (working_folder / vid / "style_string.txt").write_text(
                per_video_style[vid] + "\n", encoding="utf-8"
            )

    # Segment scripts + build prompt-gen jobs
    jobs: List[Dict] = []
    segments_by_video: Dict[str, List[str]] = {}
    for vid in selected_videos:
        script_path = working_folder / vid / f"{vid}.txt"
        segs = divide_into_segments(script_path)
        segments_by_video[vid] = segs
        ctx = "\n\n".join(segs)[:8000] if segs else None
        for seg_num, seg_text in enumerate(segs, start=1):
            jobs.append(
                {
                    "custom_id": f"{vid}__{seg_num}",
                    "segment": seg_text,
                    "seg_num": seg_num,
                    "num_images": images_per_segment,
                    "full_script_ctx": ctx,
                    "video_id": vid,
                }
            )
        print(f"  [{vid}] {len(segs)} segment(s)")

    if not jobs:
        print("No segments to process.")
        return 1

    # Generate prompts
    print(f"\nGenerating image prompts for {len(jobs)} segment(s)...")
    if use_batches_api:
        prompts_by_id = generate_prompts_via_batches(claude, jobs)
    else:
        prompts_by_id = generate_prompts_sequential(claude, jobs)

    # Assemble per-video prompt lists, applying style suffix
    prompts_by_video: Dict[str, List[List[str]]] = {vid: [] for vid in selected_videos}
    for job in jobs:
        cid = job["custom_id"]
        vid = job["video_id"]
        style = per_video_style.get(vid, "").strip()
        raw_prompts = prompts_by_id.get(cid, [])
        styled = []
        for p in raw_prompts:
            if style:
                combined = f"{p.rstrip()} {style}"
                if len(combined) > 1000:
                    combined = combined[:1000].rsplit(" ", 1)[0]
                styled.append(combined)
            else:
                styled.append(p)
        prompts_by_video[vid].append(styled)

    # Generate images
    kie = NanoBananaProClient(api_key=config["kie_api_key"], model=kie_model)
    video_output_dirs = {vid: (working_folder / vid / "images") for vid in selected_videos}
    results = run_kie_generation(
        kie=kie,
        prompts_by_video=prompts_by_video,
        video_output_dirs=video_output_dirs,
        output_format=DEFAULT_FORMAT,
        aspect_ratio=DEFAULT_ASPECT_RATIO,
        resolution=DEFAULT_RESOLUTION,
    )

    # Write per-video image_prompts.json
    for vid in selected_videos:
        out = {
            "video_id": vid,
            "title": titles.get(vid),
            "style_string": per_video_style.get(vid, ""),
            "model": kie_model,
            "segments": [
                {"segment": i + 1, "prompts": prompts_by_video[vid][i]}
                for i in range(len(prompts_by_video[vid]))
            ],
            "images": results.get(vid, []),
        }
        (working_folder / vid / "image_prompts.json").write_text(
            json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    print("\n✓ Done.")
    return 0


def main() -> int:
    print("=== Image Generation CLI ===")
    print("Type 'b' or 'back' at any prompt to return to the previous step.\n")

    config = load_or_create_config()
    claude = Anthropic(api_key=config["claude_api_key"])

    steps = [
        ("working_folder", _step_working_folder),
        ("mode", _step_mode),
        ("pick_video", _step_pick_video),
        ("image_model", _step_image_model),
        ("images_per_segment", _step_images_per_segment),
        ("style", _step_style),
        ("batches_api", _step_batches_api),
        ("confirm", _step_confirm),
    ]

    state: Dict = {}
    i = 0
    while i < len(steps):
        name, fn = steps[i]
        result = fn(state)
        if result == "next":
            i += 1
        elif result == "retry":
            continue  # re-run same step
        elif result == "retry_from_start":
            state = {}
            i = 0
        elif result is BACK:
            if i == 0:
                print("(Already at first step.)")
                continue
            # Skip over any steps that were auto-skipped (e.g. pick_video in batch mode).
            # Simpler: just decrement; if the previous step's logic would auto-skip itself, it will.
            i -= 1
            # If the previous step is pick_video and batch mode, skip back one more so we don't land on a no-op.
            if steps[i][0] == "pick_video" and state.get("is_batch"):
                i -= 1
        else:
            print(f"Unexpected step result from {name}: {result!r}")
            return 1

    return _run_pipeline(state, config, claude)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
