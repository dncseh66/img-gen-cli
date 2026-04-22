# How to Use the Image Generator

A simple step-by-step guide for turning your YouTube video scripts into a folder of AI-generated images.

---

## What it does

You give it a folder of video scripts. It reads each script, comes up with image descriptions, picks a consistent visual style for each video, and generates the images — all automatically. One image style per video, so everything looks like it belongs together.

---

## Before you start

### 1. Set up your videos folder

Pick a folder anywhere on your computer (for example `D:\my_videos`). Inside it, make **one subfolder per video**, and put the script inside as a `.txt` file with the **same name as the folder**.

Also add a file called `titles.txt` at the top level listing every video's title.

It should look like this:

```
D:\my_videos\
├── titles.txt
├── byzantine_fall_01\
│   └── byzantine_fall_01.txt
├── roman_legion_02\
│   └── roman_legion_02.txt
└── viking_raid_03\
    └── viking_raid_03.txt
```

**Important:** the folder name and the script filename must match. `byzantine_fall_01/byzantine_fall_01.txt`, not `script.txt`.

### 2. Write your script

Plain text. Separate paragraphs with a blank line between them. That's it.

### 3. Fill in `titles.txt`

One line per video, in the format `folder_name: video title`.

```
byzantine_fall_01: The Last Days of Constantinople, 1453
roman_legion_02: Life of a Roman Legionary on the Rhine Frontier
viking_raid_03: A Night Raid on Lindisfarne, 793 AD
```

You only need this file if you want the tool to invent a style for each video from its title. If you pick a ready-made style instead, `titles.txt` is optional.

---

## Running it

Double-click **`run.bat`** in the program folder.

A black window opens and asks you a series of questions. At **any** prompt you can type `b` then Enter to go back one step. Ctrl-C cancels.

**First time only:** it will ask for your Claude API key and your KIE API key. Paste them in. It remembers them after that.

---

## The questions it asks

### 1. Working folder path

Paste the full path to your videos folder.

```
Working folder path: D:\my_videos
```

It will list the video folders it found.

### 2. Mode

```
  [1] Single video
  [2] Batch (all videos in folder)
```

- **Single** — process just one video. You'll pick which one next.
- **Batch** — process every video in the folder.

### 3. Pick video *(single mode only)*

A numbered list. Type the number.

### 4. Image model

```
  [1] NanoBanana 2   (cheaper, good quality)
  [2] NanoBanana Pro (more expensive, higher quality)
```

Pick `1` unless you specifically want Pro quality.

### 5. Images per segment

```
Images per 1000-word segment [2]:
```

Every ~1000 words of script becomes one "segment." This is how many images you want per segment. Press Enter for 2, or type a number like `3` or `4`.

### 6. Style

In **single** mode you get one menu:

```
  [1] medieval_tapestry
  [2] ukiyo_e_scroll
  [3] roman_fresco
  [4] [Generate from titles.txt per video]
```

- Numbers `1–3` are ready-made styles. Pick one and every image in the video uses it.
- The last option tells the tool: "look at the video's title and invent a historically accurate style for me." Great for period pieces.

In **batch** mode it first asks whether to use the **same style for every video** or **generate one per video** from the titles.

### 7. Batches API *(batch mode only)*

```
Use Claude Message Batches API? (50% cheaper, may take up to 24h)
```

- `n` (default) — normal speed, full price. Takes minutes.
- `y` — half price, but can take anywhere from a few minutes to a full day. Only say yes if you're not in a hurry.

### 8. Confirm

It shows you everything you picked. Type `y` to start, `n` to restart, or `b` to go back one step.

---

## While it runs

You'll see status lines like:

```
Generating style string via Opus...
  [byzantine_fall_01] saved style_string.txt (412 chars)
  [byzantine_fall_01] 5 segment(s)

Generating image prompts for 5 segment(s)...
  [byzantine_fall_01] queued 1_1.png task=abc123
  ...
Waiting for 15 image task(s) to complete...
  ✓ byzantine_fall_01/1_1.png
  ✓ byzantine_fall_01/1_2.png
  ...
✓ Done.
```

Just let it finish. Image generation is the slow part — expect a few seconds to a minute per image.

---

## Where your images go

Inside each video's folder:

```
byzantine_fall_01\
├── byzantine_fall_01.txt
├── style_string.txt        ← the style that was used
├── image_prompts.json      ← full record of every prompt + image
└── images\
    ├── 1_1.png             ← segment 1, image 1
    ├── 1_2.png             ← segment 1, image 2
    ├── 2_1.png             ← segment 2, image 1
    └── ...
```

File names are `<segment>_<image>.png`, so they sort naturally in the order they appear in your script.

---

## Adding your own style preset

Want a reusable style that shows up in the menu?

1. Open the `style_strings` folder inside the program folder.
2. Make a new text file, for example `anime_sunset.txt`.
3. Write a short description of the look you want (aim for a few sentences). Always include: *people in middle ground or background, never the foreground*. And mention: *1920x1080, no modern fonts or captions*.
4. Save. Next run it appears in the menu as `anime_sunset`.

Example contents of `medieval_tapestry.txt`:

```
Medieval European tapestry style, flat perspective, woven thread texture,
muted wool-dyed palette of deep reds, ochres, forest greens, and cream.
Decorative borders, stylized foliage, heraldic motifs. People, if present,
always in middle ground or background, never the central focus.
1920x1080, no modern fonts or captions.
```

---

## If something goes wrong

| Message you see | What to do |
| --- | --- |
| `No subfolders with <id>/<id>.txt found` | Your script file isn't named the same as its folder. Rename it. |
| `titles.txt is missing entries for: ...` | Add that video's line to `titles.txt`, or pick a ready-made style instead of "generate from titles." |
| Lots of `rate limit` errors from kie.ai | You're submitting too fast. Wait a few minutes and re-run, or ask the developer to raise the submit delay. |
| A batch run is "still processing" for hours | Normal with the Batches API option. Wait, or cancel with Ctrl-C and re-run without that option. |
| It asks for API keys again | The `config.json` file got deleted or corrupted. Paste the keys again. |

---

## Quick checklist

1. Folder with one subfolder per video, script named the same as the folder.
2. `titles.txt` at the top (needed only if generating styles from titles).
3. Double-click `run.bat`.
4. Answer the questions. `b` = back, Ctrl-C = cancel.
5. Wait for ✓ Done.
6. Find your images in each video's `images\` folder.
