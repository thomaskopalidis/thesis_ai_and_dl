import os
import sys
import subprocess
import tempfile
import glob
from typing import Optional

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
SADTALKER_PATH = os.path.join(PROJECT_ROOT, "SadTalker")

import config

# Cache the preprocessed avatar — reset this if you change the avatar image
_prepared_avatar_path: Optional[str] = None
_prepared_avatar_source: Optional[str] = None


def _prepare_avatar(source_path: str) -> str:
    """
    Converts the avatar image to a clean RGB JPEG at 512x512 that SadTalker
    can reliably use, regardless of the original format/mode/size.
    Result is cached per source path — changing the image invalidates the cache.
    """
    global _prepared_avatar_path, _prepared_avatar_source
    if _prepared_avatar_path and os.path.isfile(_prepared_avatar_path) and _prepared_avatar_source == source_path:
        return _prepared_avatar_path

    try:
        from PIL import Image
    except ImportError:
        return source_path  # fall back to original if Pillow not available

    img = Image.open(source_path)

    # Convert palette / RGBA / greyscale → RGB
    if img.mode != "RGB":
        img = img.convert("RGB")

    # Crop to square from centre, then resize to 512×512
    w, h = img.size
    min_side = min(w, h)
    left = (w - min_side) // 2
    top = (h - min_side) // 2
    img = img.crop((left, top, left + min_side, top + min_side))
    img = img.resize((512, 512), Image.LANCZOS)

    out = tempfile.NamedTemporaryFile(suffix="_avatar.jpg", delete=False)
    img.save(out.name, "JPEG", quality=95)
    out.close()

    _prepared_avatar_path = out.name
    _prepared_avatar_source = source_path
    print(f"[SadTalker] Prepared avatar saved to: {out.name}")
    return out.name


def generate_sadtalker_video(audio_path: str) -> str:
    inference_script = os.path.join(SADTALKER_PATH, "inference.py")
    checkpoint_dir = os.path.join(SADTALKER_PATH, "checkpoints")

    if not os.path.isfile(inference_script):
        raise FileNotFoundError(f"SadTalker inference.py not found at: {inference_script}")
    if not os.path.isdir(checkpoint_dir):
        raise FileNotFoundError(f"SadTalker checkpoints not found at: {checkpoint_dir}")
    if not os.path.isfile(config.AVATAR_IMAGE_PATH):
        raise FileNotFoundError(f"Avatar image not found at: {config.AVATAR_IMAGE_PATH}")

    avatar_path = _prepare_avatar(config.AVATAR_IMAGE_PATH)
    result_dir = tempfile.mkdtemp(prefix="sadtalker_")

    cmd = [
        sys.executable, inference_script,
        "--driven_audio", audio_path,
        "--source_image", avatar_path,
        "--checkpoint_dir", checkpoint_dir,
        "--result_dir", result_dir,
        "--still",
        "--preprocess", "crop",
        "--size", "256",
        "--enhancer", "gfpgan",   # face enhancement for sharper, realistic output
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=SADTALKER_PATH,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"SadTalker failed (exit {result.returncode}).\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}"
        )

    mp4_files = glob.glob(os.path.join(result_dir, "**", "*.mp4"), recursive=True)
    if not mp4_files:
        raise RuntimeError("SadTalker reported success but no output MP4 was found.")

    return mp4_files[0]
