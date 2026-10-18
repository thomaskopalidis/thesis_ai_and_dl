"""core/engines/sadtalker.py — SadTalker adapter (subprocess, image-only).

Parametric constructor so the engine can be reused for:
- live app:   SadTalkerEngine() with its historical defaults
- idle video: SadTalkerEngine(still=False, preprocess="full", enhancer=None, ...)

Working resolution is aspect-preserving (thumbnail max side 1200 px) so that
portrait avatars like teacher_avatar_v2.jpg (1792x2400) are not squashed into
a square. See D-016.
"""
from __future__ import annotations

import glob
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
SADTALKER_PATH = os.path.join(PROJECT_ROOT, "SadTalker")

# Working resolution: max side 1200 px, aspect-preserved (D-016).
MAX_WORKING_SIDE = 1200


@register("sadtalker")
class SadTalkerEngine:
    name = "sadtalker"

    def __init__(
        self,
        still: bool = True,                     # app default
        preprocess: str = "crop",               # app default
        enhancer: Optional[str] = "gfpgan",     # app default
        size: int = 256,
        pose_style: int = 0,
        expression_scale: float = 1.0,
    ) -> None:
        self.still = still
        self.preprocess = preprocess
        self.enhancer = enhancer  # None | "gfpgan" | "RestoreFormer"
        self.size = size
        self.pose_style = pose_style
        self.expression_scale = expression_scale

        self._prepared_path: Optional[str] = None
        self._prepared_source: Optional[str] = None

    # ── availability ─────────────────────────────────────────────────────
    def is_available(self) -> bool:
        return (
            os.path.isfile(os.path.join(SADTALKER_PATH, "inference.py"))
            and os.path.isdir(os.path.join(SADTALKER_PATH, "checkpoints"))
        )

    # ── one-off source image prep (aspect-preserving) ───────────────────
    def prepare(self, base_path: str) -> float:
        base_path = os.path.abspath(base_path)   # subprocess runs with cwd=SADTALKER_PATH
        kind = detect_base_kind(base_path)
        if kind != "image":
            raise ValueError(
                f"SadTalker only drives still images; got {kind}: {base_path}"
            )
        if (
            self._prepared_source == base_path
            and self._prepared_path
            and os.path.isfile(self._prepared_path)
        ):
            return 0.0

        t = time.perf_counter()
        try:
            from PIL import Image
        except ImportError:
            self._prepared_path = base_path
            self._prepared_source = base_path
            return time.perf_counter() - t

        img = Image.open(base_path)
        if img.mode != "RGB":
            img = img.convert("RGB")

        # Aspect-preserving fit inside MAX_WORKING_SIDE box (D-016).
        img.thumbnail((MAX_WORKING_SIDE, MAX_WORKING_SIDE), Image.LANCZOS)

        out = tempfile.NamedTemporaryFile(suffix="_sadtalker_src.jpg", delete=False)
        img.save(out.name, "JPEG", quality=95)
        out.close()

        self._prepared_path = out.name
        self._prepared_source = base_path
        print(f"[SadTalker] Prepared source: {out.name} ({img.size[0]}x{img.size[1]})")
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
            raise FileNotFoundError("SadTalker not installed.")

        # Subprocess runs with cwd=SADTALKER_PATH: all paths must be absolute (Bug 1, Step 0).
        audio_path = os.path.abspath(audio_path)
        if base_path is not None:
            base_path = os.path.abspath(base_path)
        if out_path is not None:
            out_path = os.path.abspath(out_path)

        prepare_t = 0.0
        if base_path is not None:
            prepare_t = self.prepare(base_path)
        elif self._prepared_path is None:
            prepare_t = self.prepare(config.AVATAR_IMAGE_PATH)

        src_path = self._prepared_path
        result_dir = tempfile.mkdtemp(prefix="sadtalker_")

        cmd = [
            sys.executable, os.path.join(SADTALKER_PATH, "inference.py"),
            "--driven_audio", audio_path,
            "--source_image", src_path,
            "--checkpoint_dir", os.path.join(SADTALKER_PATH, "checkpoints"),
            "--result_dir", result_dir,
            "--preprocess", self.preprocess,
            "--size", str(self.size),
            "--pose_style", str(self.pose_style),
            "--expression_scale", str(self.expression_scale),
        ]
        if self.still:
            cmd.append("--still")
        if self.enhancer:
            cmd += ["--enhancer", self.enhancer]

        with VRAMSampler() as vram:
            t0 = time.perf_counter()
            res = subprocess.run(
                cmd, capture_output=True, text=True, cwd=SADTALKER_PATH
            )
            elapsed = time.perf_counter() - t0

        if res.returncode != 0:
            raise RuntimeError(
                f"SadTalker failed (exit {res.returncode}).\n"
                f"--- stdout ---\n{res.stdout[-1500:]}\n"
                f"--- stderr ---\n{res.stderr[-2000:]}"
            )

        mp4s = glob.glob(os.path.join(result_dir, "**", "*.mp4"), recursive=True)
        if not mp4s:
            raise RuntimeError("SadTalker produced no mp4.")
        raw_path = mp4s[0]

        if out_path is None:
            fd, out_path = tempfile.mkstemp(suffix=".mp4", prefix="sadtalker_")
            os.close(fd)

        encode_t = reencode_browser_safe(raw_path, out_path)
        dur, fps = probe_video(out_path)

        return LipsyncResult(
            video_path=out_path,
            time_s=elapsed,
            video_duration_s=dur,
            fps=fps,
            peak_vram_mb=vram.peak_delta_mb,
            load_time_s=float("nan"),
            prepare_time_s=prepare_t,
            encode_time_s=encode_t,
            engine=self.name,
            base_kind="image",
            is_warmup=is_warmup,
            extra={
                "still": self.still,
                "preprocess": self.preprocess,
                "enhancer": self.enhancer,
                "size": self.size,
                "pose_style": self.pose_style,
                "expression_scale": self.expression_scale,
            },
        )
