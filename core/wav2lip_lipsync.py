import os
import sys
import subprocess
import tempfile
import glob
from typing import Optional

import config

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
WAV2LIP_PATH = os.path.join(PROJECT_ROOT, "Wav2Lip")
CHECKPOINT_PATH = os.path.join(WAV2LIP_PATH, "checkpoints", "wav2lip_gan.pth")

_prepared_avatar_path: Optional[str] = None
_prepared_avatar_source: Optional[str] = None


def _prepare_avatar(source_path: str) -> str:
    global _prepared_avatar_path, _prepared_avatar_source
    if _prepared_avatar_path and os.path.isfile(_prepared_avatar_path) and _prepared_avatar_source == source_path:
        return _prepared_avatar_path

    try:
        from PIL import Image
    except ImportError:
        return source_path

    img = Image.open(source_path)
    if img.mode != "RGB":
        img = img.convert("RGB")

    w, h = img.size
    min_side = min(w, h)
    left = (w - min_side) // 2
    top = (h - min_side) // 2
    img = img.crop((left, top, left + min_side, top + min_side))
    img = img.resize((480, 480), Image.LANCZOS)

    out = tempfile.NamedTemporaryFile(suffix="_wav2lip_avatar.jpg", delete=False)
    img.save(out.name, "JPEG", quality=95)
    out.close()

    _prepared_avatar_path = out.name
    _prepared_avatar_source = source_path
    print(f"[Wav2Lip] Prepared avatar saved to: {out.name}")
    return out.name


def generate_wav2lip_video(audio_path: str) -> str:
    inference_script = os.path.join(WAV2LIP_PATH, "inference.py")

    if not os.path.isfile(inference_script):
        raise FileNotFoundError(f"Wav2Lip inference.py not found at: {inference_script}")
    if not os.path.isfile(CHECKPOINT_PATH):
        raise FileNotFoundError(f"Wav2Lip checkpoint not found at: {CHECKPOINT_PATH}")
    if not os.path.isfile(config.AVATAR_IMAGE_PATH):
        raise FileNotFoundError(f"Avatar image not found at: {config.AVATAR_IMAGE_PATH}")

    avatar_path = _prepare_avatar(config.AVATAR_IMAGE_PATH)

    out_fd, out_path = tempfile.mkstemp(suffix=".mp4", prefix="wav2lip_")
    os.close(out_fd)

    cmd = [
        sys.executable, inference_script,
        "--checkpoint_path", CHECKPOINT_PATH,
        "--face", avatar_path,
        "--audio", audio_path,
        "--outfile", out_path,
        "--static", "True",
        "--fps", "25",
        "--pads", "0", "10", "0", "0",
        "--wav2lip_batch_size", "256",
        "--resize_factor", "2",
        "--nosmooth",
    ]

    # inference.py writes temp/result.avi relative to cwd
    os.makedirs(os.path.join(WAV2LIP_PATH, "temp"), exist_ok=True)

    # Pass PYTHONPATH so the subprocess sees the project's venv site-packages
    # and the Wav2Lip repo. On Linux pods we also honour the pip --user site.
    env = os.environ.copy()
    sep = os.pathsep  # ';' on Windows, ':' on Linux
    paths = [WAV2LIP_PATH]
    if sys.platform.startswith("linux"):
        linux_user_site = "/tmp/.local/lib/python3.10/site-packages"
        if os.path.isdir(linux_user_site):
            paths.insert(0, linux_user_site)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = sep.join(paths + ([existing] if existing else []))

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=WAV2LIP_PATH,
        env=env,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Wav2Lip failed (exit {result.returncode}).\n"
            f"--- stdout ---\n{result.stdout[-2000:]}\n"
            f"--- stderr ---\n{result.stderr[-2000:]}"
        )

    if not os.path.isfile(out_path) or os.path.getsize(out_path) == 0:
        raise RuntimeError("Wav2Lip reported success but output MP4 is missing or empty.")

    # Re-encode to H.264 for browser compatibility (Wav2Lip uses XVID by default)
    h264_fd, h264_path = tempfile.mkstemp(suffix="_h264.mp4", prefix="wav2lip_")
    os.close(h264_fd)
    ffmpeg_result = subprocess.run(
        [
            "ffmpeg", "-y", "-i", out_path,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            h264_path,
        ],
        capture_output=True, text=True,
    )
    if ffmpeg_result.returncode == 0 and os.path.getsize(h264_path) > 0:
        os.unlink(out_path)
        return h264_path
    else:
        # ffmpeg not available or failed — return original and hope for the best
        if os.path.exists(h264_path):
            os.unlink(h264_path)
        return out_path
