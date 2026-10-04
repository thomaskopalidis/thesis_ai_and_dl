"""
core/lipsync.py

Runs Wav2Lip inference on a single sentence's audio to produce a
lip-synced video of the avatar.

Design notes:
- All paths come from config.py (absolute), so this works regardless of
  the process's current working directory (a common source of the
  "exit status 2" error, which usually just means "python couldn't find
  the script file").
- We pre-check that Wav2Lip/inference.py, the checkpoint, and the avatar
  image actually exist, and raise a clear FileNotFoundError naming exactly
  what's missing, instead of letting it fail deep inside subprocess with
  an opaque exit code.
- We capture stdout/stderr as text and include them in the raised error,
  so real Wav2Lip failures (bad checkpoint, CUDA OOM, wrong args, etc.)
  are visible instead of being silently swallowed.
"""
import os
import subprocess
import tempfile

import config


def generate_lipsync_video(audio_path: str) -> str:
    """Runs Wav2Lip inference on a single sentence's audio, returns path to output video."""
    inference_script = os.path.join(config.WAV2LIP_DIR, "inference.py")

    if not os.path.isfile(inference_script):
        raise FileNotFoundError(
            f"Wav2Lip inference.py not found at: {inference_script}\n"
            f"Clone https://github.com/Rudrabha/Wav2Lip into {config.WAV2LIP_DIR} "
            f"(or set WAV2LIP_DIR in your .env to the correct location)."
        )
    if not os.path.isfile(config.WAV2LIP_CHECKPOINT):
        raise FileNotFoundError(
            f"Wav2Lip checkpoint not found at: {config.WAV2LIP_CHECKPOINT}\n"
            f"Download wav2lip_gan.pth into that folder, or set WAV2LIP_CHECKPOINT in your .env."
        )
    if not os.path.isfile(config.AVATAR_IMAGE_PATH):
        raise FileNotFoundError(f"Avatar image not found at: {config.AVATAR_IMAGE_PATH}")

    output_path = tempfile.mktemp(suffix=".mp4")

    cmd = [
        "python", inference_script,
        "--checkpoint_path", config.WAV2LIP_CHECKPOINT,
        "--face", config.AVATAR_IMAGE_PATH,
        "--audio", audio_path,
        "--outfile", output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"Wav2Lip inference failed (exit code {result.returncode}).\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}"
        )

    if not os.path.isfile(output_path):
        raise RuntimeError("Wav2Lip reported success but no output video was produced.")

    return output_path