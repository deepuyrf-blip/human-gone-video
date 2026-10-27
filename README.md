# human-gone-video

Turn the scene images + `human_gone_motion.json` into an animated MP4 —
a slow camera **push-in** per scene, with the exact per-scene duration.
No AI video model needed: every scene in the motion file is a camera move,
which ffmpeg's `zoompan` does perfectly.

## What's in here

| File | Purpose |
|---|---|
| `human_gone_prompts.json` | 204 **image** prompts (scene_id, prompt, negative_prompt) — use in the app's "JSON → Images" tab |
| `human_gone_motion.json` | 204 **motion** prompts (scene_id, duration_sec, motion_prompt) — drives the animation |
| `make_video.py` | builds the MP4 from the images + the motion file |
| `images/` | put the scene images here (scene_001.png, scene_002.png, …) |

## Use

```bash
pip install imageio-ffmpeg        # bundles an ffmpeg binary (no apt needed)
python3 make_video.py --motion human_gone_motion.json --images ./images --out human_gone.mp4
```

With narration audio:

```bash
python3 make_video.py --motion human_gone_motion.json --images ./images \
                      --out human_gone.mp4 --audio narration.mp3
```

Test a few scenes first:

```bash
python3 make_video.py --motion human_gone_motion.json --images ./images \
                      --out test.mp4 --start 1 --end 20
```

## Image naming

Matched by `scene_id`, so any of these work:
`scene_001.png` · `scene_1.png` · `scene1.png` · `001.png` · `1.jpg` · `.webp`

## Options

`--fps 30` · `--width 1920 --height 1080` · `--crf 20` (quality) ·
`--start N --end N` (subset) · `--audio file` (mux narration)

## What it can / can't do

* ✅ camera push-in + hold (100% of the scenes) and exact durations
* ✅ optional narration audio
* ❌ character motion (blink, head tilt, walking) — a still image can't do that;
  for those scenes use an AI image-to-video model (Kling / Runway / Veo / Seedance / LTX)
  with the image + `motion_prompt`.
