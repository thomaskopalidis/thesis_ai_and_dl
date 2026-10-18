"""
Create candidate idle videos for the teacher avatar (D-015).

Workflow:
  # Stage 1 — pick preprocess mode (3 candidates, 4 s each)
  python evaluation/make_idle_video.py --drive <dir> --name s1_full \
      --preprocess full --no-still --audio pink --enhancer none --duration 4
  python evaluation/make_idle_video.py --drive <dir> --name s1_extcrop \
      --preprocess extcrop --no-still --audio pink --enhancer none --duration 4
  python evaluation/make_idle_video.py --drive <dir> --name s1_full_still \
      --preprocess full --still --audio pink --enhancer none --duration 4

  # Stage 2 — in the chosen preprocess, pick audio
  python evaluation/make_idle_video.py --drive <dir> --name s2_pink \
      --preprocess full --no-still --audio pink --enhancer none --duration 4
  python evaluation/make_idle_video.py --drive <dir> --name s2_silence \
      --preprocess full --no-still --audio silence --enhancer none --duration 4

  # Final — same combo at 10 s, two enhancer variants
  python evaluation/make_idle_video.py --drive <dir> --name final_none \
      --preprocess full --no-still --audio pink --enhancer none --duration 10
  python evaluation/make_idle_video.py --drive <dir> --name final_gfpgan \
      --preprocess full --no-still --audio pink --enhancer gfpgan --duration 10

  # Promote chosen candidate to the frozen asset (archives any previous).
  python evaluation/make_idle_video.py --drive <dir> --promote final_gfpgan

Each candidate is written to <drive>/candidates/<name>.mp4 + <name>.json.
Promoted asset lives at <drive>/teacher_idle_25fps.mp4 + teacher_idle_manifest.json.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
import config  # noqa: E402
from core.engines.sadtalker import SadTalkerEngine  # noqa: E402

FROZEN_NAME = "teacher_idle_25fps.mp4"
FROZEN_MANIFEST = "teacher_idle_manifest.json"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sadtalker_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT / "SadTalker",
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() if out.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _make_audio(kind: str, duration_s: float, out: Path) -> None:
    """kind in {'pink', 'silence'} -> 16 kHz mono WAV of given duration."""
    if kind == "pink":
        src = f"anoisesrc=d={duration_s}:c=pink:r=16000:a=0.003"
    elif kind == "silence":
        src = f"anullsrc=r=16000:cl=mono"
    else:
        raise ValueError(f"Unknown audio kind: {kind}")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", src,
           "-t", str(duration_s), "-ar", "16000", "-ac", "1", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg audio synth failed: {r.stderr[-500:]}")


def _ping_pong(src: Path, dst: Path) -> None:
    """Forward + reverse concat. Reversal point is the same frame → seamless."""
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
           "-filter_complex", "[0]reverse[r];[0][r]concat=n=2:v=1[v]",
           "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-r", "25", "-movflags", "+faststart", str(dst)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg ping-pong failed: {r.stderr[-500:]}")


# ─── Build one candidate ───────────────────────────────────────────────────
def build_candidate(
    name: str,
    out_dir: Path,
    preprocess: str,
    still: bool,
    audio_kind: str,
    enhancer: str | None,
    duration_s: float,
    source_image: Path,
    expression_scale: float = 0.5,
    pose_style: int = 0,
    size: int = 256,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    mp4_out = out_dir / f"{name}.mp4"
    json_out = out_dir / f"{name}.json"

    # 1. silent/pink driving audio
    audio_tmp = out_dir / f"_driver_{name}.wav"
    _make_audio(audio_kind, duration_s, audio_tmp)

    # 2. SadTalker run with per-candidate params
    engine = SadTalkerEngine(
        still=still,
        preprocess=preprocess,
        enhancer=(enhancer if enhancer and enhancer != "none" else None),
        size=size,
        pose_style=pose_style,
        expression_scale=expression_scale,
    )
    if not engine.is_available():
        audio_tmp.unlink(missing_ok=True)
        raise RuntimeError(
            "SadTalker is not installed (missing inference.py or checkpoints). "
            "Run the SadTalker setup cell first."
        )

    print(f"[{name}] SadTalker: preprocess={preprocess} still={still} "
          f"enhancer={enhancer} audio={audio_kind} dur={duration_s}s "
          f"expr={expression_scale} pose={pose_style} size={size}")
    t_total = time.perf_counter()
    raw = engine.generate(str(audio_tmp), base_path=str(source_image))
    forward_path = Path(raw.video_path)

    # 3. ping-pong
    _ping_pong(forward_path, mp4_out)
    total_s = time.perf_counter() - t_total

    audio_tmp.unlink(missing_ok=True)
    try:
        forward_path.unlink()
    except OSError:
        pass

    # 4. manifest for this candidate
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=width,height,duration,r_frame_rate", "-of", "json", str(mp4_out)],
        capture_output=True, text=True,
    )
    streams = json.loads(probe.stdout).get("streams", [{}])[0] if probe.returncode == 0 else {}

    meta = {
        "name": name,
        "created_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "video_sha256": _sha256(mp4_out),
        "video_size_bytes": mp4_out.stat().st_size,
        "video_width": streams.get("width"),
        "video_height": streams.get("height"),
        "video_duration_s": float(streams.get("duration", 0.0) or 0.0),
        "video_r_frame_rate": streams.get("r_frame_rate"),
        "source_image": str(source_image.name),
        "source_image_sha256": _sha256(source_image),
        "sadtalker_commit": _sadtalker_commit(),
        "sadtalker_config": {
            "preprocess": preprocess,
            "still": still,
            "enhancer": enhancer,
            "size": size,
            "pose_style": pose_style,
            "expression_scale": expression_scale,
            "audio_kind": audio_kind,
            "driver_duration_s": duration_s,
        },
        "measurements": {
            "sadtalker_time_s": round(raw.time_s, 2),
            "sadtalker_peak_vram_mb": round(raw.peak_vram_mb, 1),
            "pingpong_included": True,
            "pipeline_total_s": round(total_s, 2),
        },
    }
    json_out.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[{name}] OK → {mp4_out}  ({meta['video_duration_s']:.2f}s, "
          f"{meta['video_width']}x{meta['video_height']})")
    return meta


# ─── Promote a candidate to the frozen asset ──────────────────────────────
def promote(drive: Path, name: str) -> None:
    cand_mp4 = drive / "candidates" / f"{name}.mp4"
    cand_json = drive / "candidates" / f"{name}.json"
    if not cand_mp4.is_file() or not cand_json.is_file():
        raise FileNotFoundError(f"Candidate '{name}' not found under {drive/'candidates'}.")

    frozen_mp4 = drive / FROZEN_NAME
    frozen_json = drive / FROZEN_MANIFEST

    # Archive previous frozen asset if present.
    if frozen_mp4.is_file() or frozen_json.is_file():
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        archive = drive / f"archived_{stamp}"
        archive.mkdir(exist_ok=True)
        for p in (frozen_mp4, frozen_json):
            if p.is_file():
                shutil.move(str(p), str(archive / p.name))
        print(f"[ARCHIVED] previous frozen asset → {archive}")

    # Copy candidate -> frozen; manifest records provenance.
    shutil.copy2(cand_mp4, frozen_mp4)
    cand_meta = json.loads(cand_json.read_text(encoding="utf-8"))
    cand_meta["promoted_from"] = name
    cand_meta["promoted_utc"] = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    cand_meta["frozen_sha256"] = _sha256(frozen_mp4)
    frozen_json.write_text(json.dumps(cand_meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[PROMOTED] {name} → {frozen_mp4}  (SHA-256 {cand_meta['frozen_sha256'][:16]}…)")


# ─── Entry point ───────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--drive", type=Path, required=True,
                    help="Target dir (e.g. /content/drive/MyDrive/thesis_ai_and_dl/avatar).")
    ap.add_argument("--name", type=str,
                    help="Candidate name (required unless --promote).")
    ap.add_argument("--source", type=Path, default=Path(config.AVATAR_IMAGE_PATH),
                    help="Source image (default: config.AVATAR_IMAGE_PATH).")
    ap.add_argument("--preprocess", choices=["crop", "extcrop", "resize", "full", "extfull"],
                    default="full")
    still_group = ap.add_mutually_exclusive_group()
    still_group.add_argument("--still", dest="still", action="store_true")
    still_group.add_argument("--no-still", dest="still", action="store_false")
    ap.set_defaults(still=False)
    ap.add_argument("--audio", choices=["pink", "silence"], default="pink")
    ap.add_argument("--enhancer", choices=["none", "gfpgan", "RestoreFormer"], default="none")
    ap.add_argument("--duration", type=float, default=10.0)
    ap.add_argument("--expression-scale", type=float, default=0.5,
                    help="SadTalker expression_scale (default 0.5, D-015)")
    ap.add_argument("--pose-style", type=int, default=0,
                    help="SadTalker pose_style, 0..45 (default 0, D-015)")
    ap.add_argument("--size", type=int, default=256,
                    help="SadTalker face render size (default 256)")
    ap.add_argument("--promote", type=str,
                    help="Candidate name to promote as the frozen asset.")
    args = ap.parse_args()

    drive: Path = args.drive
    drive.mkdir(parents=True, exist_ok=True)

    if args.promote:
        promote(drive, args.promote)
        return 0

    if not args.name:
        print("[ERROR] --name is required unless --promote is used.", file=sys.stderr)
        return 2
    if not args.source.is_file():
        print(f"[ERROR] source image not found: {args.source}", file=sys.stderr)
        return 2

    build_candidate(
        name=args.name,
        out_dir=drive / "candidates",
        preprocess=args.preprocess,
        still=args.still,
        audio_kind=args.audio,
        enhancer=args.enhancer,
        duration_s=args.duration,
        source_image=args.source,
        expression_scale=args.expression_scale,
        pose_style=args.pose_style,
        size=args.size,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
