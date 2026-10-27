#!/usr/bin/env python3
"""
make_video.py — turn a folder of scene images + human_gone_motion.json into an
animated MP4 (slow camera push-in per scene, exact per-scene duration).

No AI video model needed: every scene in the motion file is a camera move
("slow push-in of about N percent ... hold about D seconds"), which ffmpeg's
zoompan does perfectly.

Usage
-----
    python3 make_video.py --motion human_gone_motion.json --images ./images \
                          --out final.mp4 [--fps 30] [--width 1920] [--height 1080] \
                          [--audio narration.mp3] [--crf 20] [--start 1] [--end 204]

Images are matched by scene id, so any of these work:
    scene_001.png  scene_1.png  scene1.png  001.png  1.png  1.jpg
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

EXTS = (".png", ".jpg", ".jpeg", ".webp")


def ffmpeg_exe() -> str:
    """System ffmpeg, else the bundled one from imageio-ffmpeg."""
    for name in ("ffmpeg",):
        p = shutil.which(name)
        if p:
            return p
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        sys.exit("ffmpeg nahi mila. Install:  pip install imageio-ffmpeg   (ya apt install ffmpeg)")


def parse_push_in(text: str, default: float = 0.04) -> float:
    """'slow push-in of about 4 percent' -> 0.04"""
    m = re.search(r"push[-\s]?in of about (\d+(?:\.\d+)?)\s*percent", text, re.I)
    if m:
        return max(0.0, float(m.group(1)) / 100.0)
    if re.search(r"\bhold still\b|\bno (?:camera )?movement\b|\bstatic\b", text, re.I):
        return 0.0
    return default


def find_image(folder: Path, scene_id: int):
    """scene_id 7 -> scene_007.png / scene_7.png / 007.png / 7.jpg ..."""
    for pad in (3, 4, 2, 0):
        num = str(scene_id).zfill(pad) if pad else str(scene_id)
        for stem in (f"scene_{num}", f"scene{num}", f"scene-{num}", num):
            for ext in EXTS:
                for name in (f"{stem}{ext}", f"{stem}{ext.upper()}"):
                    p = folder / name
                    if p.exists():
                        return p
    return None


def render_scene(ff: str, img: Path, dur: float, pct: float, out: Path,
                 fps: int, w: int, h: int, crf: int) -> bool:
    """One clip: slow zoom from 1.0 to 1+pct over `dur` seconds, centred."""
    frames = max(2, int(round(dur * fps)))
    # upscale first so the zoom is smooth (avoids visible stepping)
    up_w, up_h = w * 2, h * 2
    if pct <= 0.0001:
        vf = (f"scale={up_w}:{up_h}:force_original_aspect_ratio=increase,"
              f"crop={up_w}:{up_h},scale={w}:{h},format=yuv420p")
    else:
        vf = (
            f"scale={up_w}:{up_h}:force_original_aspect_ratio=increase,"
            f"crop={up_w}:{up_h},"
            f"zoompan=z='1+{pct:.4f}*on/{frames}'"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d=1:s={w}x{h}:fps={fps},format=yuv420p"
        )
    cmd = [ff, "-y", "-loglevel", "error",
           "-loop", "1", "-framerate", str(fps), "-t", f"{dur:.3f}", "-i", str(img),
           "-vf", vf, "-t", f"{dur:.3f}",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
           "-pix_fmt", "yuv420p", "-r", str(fps), str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"   ffmpeg error: {r.stderr.strip()[:300]}")
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--motion", required=True, help="human_gone_motion.json")
    ap.add_argument("--images", required=True, help="folder with scene images")
    ap.add_argument("--out", default="final.mp4")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--crf", type=int, default=20)
    ap.add_argument("--audio", default=None, help="optional narration audio to mux")
    ap.add_argument("--start", type=int, default=None)
    ap.add_argument("--end", type=int, default=None)
    ap.add_argument("--fade", type=float, default=0.0, help="crossfade seconds (0 = hard cut)")
    a = ap.parse_args()

    ff = ffmpeg_exe()
    data = json.loads(Path(a.motion).read_text(encoding="utf-8"))
    scenes = data.get("scenes") or data.get("prompts") or []
    if not scenes:
        sys.exit("motion file mein 'scenes' nahi mila")

    img_dir = Path(a.images)
    if not img_dir.is_dir():
        sys.exit(f"images folder nahi mila: {img_dir}")

    todo = [s for s in scenes
            if (a.start is None or s.get("scene_id", 0) >= a.start)
            and (a.end is None or s.get("scene_id", 0) <= a.end)]

    tmp = Path(tempfile.mkdtemp(prefix="mkscenes_"))
    clips, missing = [], []
    print(f"ffmpeg: {ff}")
    print(f"scenes: {len(todo)}  |  {a.width}x{a.height} @ {a.fps}fps")

    for i, s in enumerate(todo, 1):
        sid = s.get("scene_id", i)
        dur = float(s.get("duration_sec") or 2.0)
        pct = parse_push_in(s.get("motion_prompt") or "")
        img = find_image(img_dir, sid)
        if not img:
            missing.append(sid)
            print(f"  [{i}/{len(todo)}] scene {sid}: image nahi mili — skip")
            continue
        out = tmp / f"clip_{sid:04d}.mp4"
        ok = render_scene(ff, img, dur, pct, out, a.fps, a.width, a.height, a.crf)
        print(f"  [{i}/{len(todo)}] scene {sid}: {dur:.1f}s  zoom {pct*100:.1f}%  "
              f"{'ok' if ok else 'FAIL'}")
        if ok:
            clips.append(out)

    if not clips:
        sys.exit("koi clip nahi bani (images mili hi nahi?)")

    # concat (identical encode params -> stream copy)
    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{c.as_posix()}'\n" for c in clips), encoding="utf-8")
    out_path = Path(a.out).resolve()
    if a.audio:
        cmd = [ff, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
               "-i", a.audio, "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
               "-shortest", str(out_path)]
    else:
        cmd = [ff, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
               "-c", "copy", str(out_path)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("concat fail: " + r.stderr.strip()[:400])

    total = sum(float(s.get("duration_sec") or 2.0) for s in todo
                if find_image(img_dir, s.get("scene_id", 0)))
    print(f"\n✅ video: {out_path}")
    print(f"   clips: {len(clips)}  |  ~{total/60:.1f} min")
    if missing:
        print(f"   ⚠️ images missing for scenes: {missing[:20]}{' …' if len(missing) > 20 else ''}")


if __name__ == "__main__":
    main()
