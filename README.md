# img-gen-cli

An interactive CLI that turns YouTube video scripts into AI-generated story images. It splits each script into ~1000-word segments, uses Claude to write image prompts, optionally generates a historically-consistent visual style per video, and then renders images via the [kie.ai](https://kie.ai) API (NanoBanana 2 or NanoBanana Pro).

Designed for long-form "sleep video"–style content where every image of a given video shares one consistent visual language.

## Features

- **Single or batch mode** — process one video or every video folder in one run.
- **Per-video style** — either pick a preset style from `style_strings/`, or have Claude Opus generate one from the video title and infer the historical period.
- **Claude Message Batches API support** — in batch mode, submit all prompt-generation requests as one cheap async batch (50% cost reduction, up to 24 h turnaround).
- **Back-navigation** — type `b` or `back` at any prompt to go back one step.
- **Rate-limit friendly** — a configurable delay between image submissions.

## Requirements

- Python 3.9+
- A Claude (Anthropic) API key — <https://console.anthropic.com/>
- A kie.ai API key — <https://kie.ai>

## First-time setup on a new (virgin) Windows machine

If you are starting from a brand-new computer that has never had this project on it, follow these steps in order. After this is done, day-to-day use is just double-clicking `run.bat`.

### 1. Install Python 3

1. Go to <https://www.python.org/downloads/> and download the latest Python 3 installer for Windows.
2. Run the installer. **On the first screen, tick the box "Add python.exe to PATH"** before clicking Install Now. Without this, `run.bat` will not find Python.
3. When the installer finishes, open a new Command Prompt and run `python --version` to confirm it prints a version number.

### 2. Install Git

1. Go to <https://git-scm.com/download/win> and download "64-bit Git for Windows Setup".
2. Run the installer. The default options are fine — just keep clicking Next. The important ones (already default) are:
   - "Git from the command line and also from 3rd-party software" (so `git` works in Command Prompt).
   - The bundled "Git Bash" terminal is installed as well; either Command Prompt or Git Bash works for the commands below.
3. Open a new Command Prompt and run `git --version` to confirm it prints a version.
4. One-time identity setup (replace with your own name and email):

   ```bash
   git config --global user.name "Your Name"
   git config --global user.email "you@example.com"
   ```

### 3. Clone the repository

Pick a folder where you want the project to live (for example `C:\Users\<you>\Projects`) and in Command Prompt:

```bash
cd C:\Users\<you>\Projects
git clone https://github.com/dncseh66/img-gen-cli.git
cd img-gen-cli
```

This creates an `img-gen-cli` folder containing the repo.

### 4. Create `config.json` with your API keys

`config.json` is **gitignored on purpose** — it is never in the clone. You need to create it yourself before the first run. Two options:

- **Easiest:** just run `run.bat` once (step 5). On first run the CLI prompts for your Claude and kie.ai keys and writes `config.json` for you.
- **Manual:** copy `config.example.json` to `config.json` in the repo root and fill in:

  ```json
  {
    "claude_api_key": "sk-ant-...",
    "kie_api_key": "..."
  }
  ```

Get the keys from <https://console.anthropic.com/> and <https://kie.ai>.

### 5. Run it

Double-click **`run.bat`** in the repo folder (or run `run.bat` from Command Prompt). On the very first run it will:

1. Create a `.venv` virtual environment.
2. Install everything in `requirements.txt` into that venv.
3. Launch [cli.py](cli.py).

Every subsequent run skips the install step (thanks to a `.installed` stamp file) and goes straight to the CLI. This is the normal day-to-day entry point — you do not need to activate the venv manually.

## Updating to the latest version

When new changes are pushed to the repo, pull them down with:

```bash
cd C:\Users\<you>\Projects\img-gen-cli
git pull
```

If `requirements.txt` changed in the update, delete the file `.venv\.installed` in the repo folder and run `run.bat` again — that forces a fresh `pip install`. If it didn't change, just run `run.bat` as normal. Your `config.json` and the `.venv` folder are untouched by `git pull`.

If `git pull` complains about local changes you did not intend to make, run `git status` to see what's different and `git stash` to set them aside before pulling.

## Manual install (advanced / macOS / Linux)

If you would rather manage the venv yourself, or you are on macOS / Linux where `run.bat` does not apply:

```bash
git clone https://github.com/dncseh66/img-gen-cli.git
cd img-gen-cli
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt
python cli.py
```

## Configure

On first run the CLI will prompt you for your API keys and save them to `config.json` next to the script. This file is **gitignored** — it never leaves your machine.

You can also create it manually by copying the template:

```bash
cp config.example.json config.json
# then edit config.json and fill in the keys
```

`config.json` format:

```json
{
  "claude_api_key": "sk-ant-...",
  "kie_api_key": "..."
}
```

## Prepare your working folder

The CLI operates on a *working folder* (anywhere on your disk — it does not have to be inside this repo) laid out like this:

```
working_folder/
├── titles.txt
├── MO0001/
│   └── MO0001.txt
├── MO0002/
│   └── MO0002.txt
└── ...
```

- **`<video_id>/<video_id>.txt`** — the script for that video. Paragraphs separated by blank lines.
- **`titles.txt`** — one line per video in the form `<video_id>: <title>`. Only required if you want to auto-generate styles.

Example `titles.txt`:

```
MO0001: The Fall of the Roman Empire
MO0002: Life in Medieval England
```

## Run

```bash
python cli.py
```

You will be prompted for, in order:

1. **Working folder** path.
2. **Single or batch** mode.
3. If single: **pick a video** from the list.
4. **Image model** — NanoBanana 2 (default) or NanoBanana Pro.
5. **Images per 1000-word segment** (integer).
6. **Style** — pick a preset from `style_strings/`, or generate per video from `titles.txt`.
7. **Batches API** (batch mode only) — whether to use Anthropic Message Batches. Answer no if you need results quickly.
8. **Confirm** — review and proceed.

Type `b` or `back` at any prompt to return to the previous step.

## Output

For each processed video:

```
working_folder/<video_id>/
├── style_string.txt         # the style actually used
├── image_prompts.json       # every prompt + task ID + file path
└── images/
    ├── 1_1.png
    ├── 1_2.png
    ├── 2_1.png
    └── ...
```

Filenames are `<segment_number>_<image_number>.png`.

## Style presets

Any `.txt` file in [style_strings/](style_strings/) shows up in the style menu (filename without extension becomes the label). To add one, drop a new file in that folder — its entire contents are appended to each image prompt.

When you let Claude generate a style, it goes into `<video_id>/style_string.txt` (not into `style_strings/` — generated styles are per-video, not shared).

## Legacy CLI

[script_to_images.py](script_to_images.py) is an older flag-based CLI kept for backward compatibility. New work goes into [cli.py](cli.py).

## Troubleshooting

- **"No subfolders with `<id>/<id>.txt` found"** — the script filename must exactly match the folder name.
- **"titles.txt is missing entries for…"** — only needed if you chose to generate styles. Pick a preset style instead, or add the missing rows.
- **kie.ai rate-limit errors** — increase `KIE_SUBMIT_DELAY_SECONDS` in [cli.py](cli.py).
- **Batch API stuck** — it polls every 15 seconds; Anthropic batches can legitimately take hours under load. Ctrl-C to abort.

## License

MIT — see [LICENSE](LICENSE) if present.
