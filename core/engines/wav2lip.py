"""
core/engines/wav2lip.py

Wav2Lip adapter wrapping the existing subprocess inference call.

Supports both image and video base:
- image: cropped+resized JPEG, --static True (auto-forced by Wav2Lip anyway)
- video: fps-normalized to 25 fps (cached), --static OMITTED (bool argparse bug)

load_time_s = NaN in Step 0 (new subprocess loads torch+ckpt every call).
Step 2 moves this to a persistent worker that loads once.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from typing import Optional

import config
from core.avatar_engine import (
    LipsyncResult,
    VRAMSampler,
    detect_base_kind,
    probe_video,
    reencode_browser_safe,
    register,
)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
WAV2LIP_PATH = os.path.join(PROJECT_ROOT, "Wav2Lip")
CHECKPOINT_PATH = os.path.join(WAV2LIP_PATH, "checkpoints", "wav2lip_gan.pth")

# Default face resolution factor — Step 4 will tune this to match MuseTalk (256px)
DEFAULT_RESIZE_FACTOR = 2


@register("wav2lip")
class Wav2LipEngine:
    name = "wav2lip"

    def __init__(self, resize_factor: int = DEFAULT_RESIZE_FACTOR) -> None:
        # Rule C: no heavy work here.
        self.resize_factor = resize_factor
        self._prepared_path: Optional[str] = None
        self._prepared_source: Optional[str] = None
        self._prepared_kind: Optional[str] = None  # "image" | "video"

    # ── availability ─────────────────────────────────────────────────────
    def is_available(self) -> bool:
        return (
            os.path.isfile(os.path.join(WAV2LIP_PATH, "inference.py"))
            and os.path.isfile(CHECKPOINT_PATH)
        )

    # ── one-off base prep (image resize OR video fps-normalize) ─────────
    def prepare(self, base_path: str) -> float:
        base_path = os.path.abspath(base_path)
        if (
            self._prepared_source == base_path
            and self._prepared_path
            and os.path.isfile(self._prepared_path)
        ):
            return 0.0  # cache hit

        kind = detect_base_kind(base_path)
        t = time.perf_counter()

        if kind == "image":
            try:
                from PIL import Image
            except ImportError:
                self._prepared_path = base_path
                self._prepared_source = base_path
                self._prepared_kind = kind
                return time.perf_counter() - t

            img = Image.open(base_path)
            if img.mode != "RGB":
                img = img.convert("RGB")
            w, h = img.size
            s = min(w, h)
            img = img.crop(((w - s) // 2, (h - s) // 2, (w + s) // 2, (h + s) // 2))
            img = img.resize((480, 480), Image.LANCZOS)

            out = tempfile.NamedTemporaryFile(suffix="_wav2lip_face.jpg", delete=False)
            img.save(out.name, "JPEG", quality=95)
            out.close()
            prepared = out.name

        else:  # video
            _, fps = probe_video(base_path)
            if abs(fps - 25.0) < 0.05:
                # Already 25 fps — just reference the original (no re-encode)
                prepared = base_path
            else:
                fd, prepared = tempfile.mkstemp(suffix="_wav2lip_base25.mp4",
                                                prefix="base_")
                os.close(fd)
                ff = subprocess.run(
                    ["ffmpeg", "-y", "-i", base_path,
                     "-r", "25", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                     "-an", prepared],
                    capture_output=True, text=True,
                )
                if ff.returncode != 0:
                    raise RuntimeError(
                        f"ffmpeg fps-normalize failed:\n{ff.stderr[-1500:]}"
                    )

        self._prepared_path = prepared
        self._prepared_source = base_path
        self._prepared_kind = kind
        print(f"[Wav2Lip] Prepared {kind}: {prepared}")
        return time.perf_counter() - t

    # ── per-sentence inference ──────────────────────────────────────────
    def generate(
        self,
        audio_path: str,
        base_path: Optional[str] = None,
        out_path: Optional[str] = None,
        is_warmup: bool = False,
    ) -> LipsyncResult:
        if not self.is_available():
            raise FileNotFoundError(
                "Wav2Lip not installed (missing inference.py or checkpoint)."
            )
        # Subprocess runs with cwd=WAV2LIP_PATH, so all paths must be absolute
        audio_path = os.path.abspath(audio_path)
        if base_path is not None:
            base_path = os.path.abspath(base_path)
        if out_path is not None:
            out_path = os.path.abspath(out_path)
        # Wav2Lip calls ffmpeg internally with UNQUOTED paths: a path with spaces
        # (e.g. "AI and DL") silently produces an empty output. Copy audio to a
        # temp path without spaces.
        if " " in audio_path:
            import shutil
            fd, tmp_audio = tempfile.mkstemp(
                suffix=os.path.splitext(audio_path)[1], prefix="w2l_audio_"
            )
            os.close(fd)
            shutil.copyfile(audio_path, tmp_audio)
            audio_path = tmp_audio

        # Fix #1: only auto-prepare if nothing has been prepared yet.
        prepare_t = 0.0
        if base_path is not None:
            prepare_t = self.prepare(base_path)
        elif self._prepared_path is None:
            prepare_t = self.prepare(config.AVATAR_IMAGE_PATH)

        face_path = self._prepared_path
        kind = self._prepared_kind  # set by prepare()

        if out_path is None:
            fd, out_path = tempfile.mkstemp(suffix=".mp4", prefix="wav2lip_")
            os.close(fd)

        raw_fd, raw_path = tempfile.mkstemp(suffix=".mp4", prefix="wav2lip_raw_")
        os.close(raw_fd)

        cmd = [
            sys.executable, os.path.join(WAV2LIP_PATH, "inference.py"),
            "--checkpoint_path", CHECKPOINT_PATH,
            "--face", face_path,
            "--audio", audio_path,
            "--outfile", raw_path,
            "--fps", "25",
            "--pads", "0", "10", "0", "0",
            "--wav2lip_batch_size", "256",
            "--resize_factor", str(self.resize_factor),
            "--nosmooth",
        ]
        # Fix #2: --static only for image (bool argparse treats any string as True)
        if kind == "image":
            cmd += ["--static", "True"]

        os.makedirs(os.path.join(WAV2LIP_PATH, "temp"), exist_ok=True)

        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(
            [WAV2LIP_PATH] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
        )

        with VRAMSampler() as vram:
            t0 = time.perf_counter()
            res = subprocess.run(
                cmd, capture_output=True, text=True, cwd=WAV2LIP_PATH, env=env
            )
            elapsed = time.perf_counter() - t0

        if res.returncode != 0:
            raise RuntimeError(
                f"Wav2Lip failed (exit {res.returncode}).\n"
                f"--- stdout ---\n{res.stdout[-2000:]}\n"
                f"--- stderr ---\n{res.stderr[-2000:]}"
            )
        if not os.path.isfile(raw_path) or os.path.getsize(raw_path) == 0:
            raise RuntimeError(
                "Wav2Lip reported success but output is empty.\n"
                f"--- stdout ---\n{res.stdout[-1500:]}\n"
                f"--- stderr ---\n{res.stderr[-1500:]}"
            )

        encode_t = reencode_browser_safe(raw_path, out_path)
        dur, fps = probe_video(out_path)

        return LipsyncResult(
            video_path=out_path,
            time_s=elapsed,
            video_duration_s=dur,
            fps=fps,
            peak_vram_mb=vram.peak_delta_mb,
            load_time_s=float("nan"),  # per D-012: isolated in Step 2
            prepare_time_s=prepare_t,
            encode_time_s=encode_t,
            engine=self.name,
            base_kind=kind,
            is_warmup=is_warmup,
            extra={"resize_factor": self.resize_factor},
        )
