"""
core/avatar_engine.py

Common interface for all lipsync/avatar engines (Wav2Lip, SadTalker, MuseTalk).

Rules enforced here:
- Rule C: no model loading at import or __init__; happens lazily in prepare().
- Rule D: is_available() lets the app hide engines missing on the host.
- Rule E: outputs are h264 + yuv420p + faststart (handled by each adapter).
- Measurement (D-011): VRAM via nvidia-smi sampling, separate load/time/encode.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Optional, Protocol


VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def detect_base_kind(path: str) -> str:
    """Return 'video' or 'image' based on file extension."""
    ext = os.path.splitext(path)[1].lower()
    if ext in VIDEO_EXTS:
        return "video"
    if ext in IMAGE_EXTS:
        return "image"
    raise ValueError(f"Cannot determine base_kind from extension: {path}")


# ─── Result ────────────────────────────────────────────────────────────────
@dataclass
class LipsyncResult:
    video_path: str
    time_s: float                      # pure inference wall-clock (per call)
    video_duration_s: float
    fps: float
    peak_vram_mb: float                # peak − baseline (nvidia-smi sampling)
    load_time_s: float = float("nan")  # model load; NaN if cannot be isolated
    prepare_time_s: float = 0.0        # one-off base prep (cache misses only)
    encode_time_s: float = 0.0         # ffmpeg re-encode to h264+yuv420p+faststart
    engine: str = ""
    base_kind: str = ""                # "image" | "video"  (per-call)
    is_warmup: bool = False
    extra: dict = field(default_factory=dict)

    def as_row(self) -> dict:
        d = asdict(self)
        d.pop("extra", None)
        return d


# ─── Protocol ──────────────────────────────────────────────────────────────
class AvatarEngine(Protocol):
    name: str

    def is_available(self) -> bool: ...
    def prepare(self, base_path: str) -> float: ...   # returns prepare_time_s
    def generate(
        self,
        audio_path: str,
        base_path: Optional[str] = None,
        out_path: Optional[str] = None,
        is_warmup: bool = False,
    ) -> LipsyncResult: ...


# ─── Registry ──────────────────────────────────────────────────────────────
ENGINES: dict[str, AvatarEngine] = {}


def register(name: str):
    def deco(cls):
        ENGINES[name] = cls()  # Rule C: cheap __init__, no model load
        return cls
    return deco


def available_engines() -> list[str]:
    return [n for n, e in ENGINES.items() if e.is_available()]


def get(name: str) -> AvatarEngine:
    if name not in ENGINES:
        raise KeyError(f"Unknown avatar engine '{name}'. Registered: {list(ENGINES)}")
    return ENGINES[name]


# ─── ffprobe helper ────────────────────────────────────────────────────────
def probe_video(path: str) -> tuple[float, float]:
    """Returns (duration_s, fps). Falls back to (0.0, 0.0) if ffprobe missing."""
    if not shutil.which("ffprobe") or not os.path.isfile(path):
        return 0.0, 0.0
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=duration,r_frame_rate",
             "-of", "json", path],
            capture_output=True, text=True, timeout=10,
        )
        data = json.loads(out.stdout).get("streams", [{}])[0]
        dur = float(data.get("duration", 0.0) or 0.0)
        num, den = (data.get("r_frame_rate", "0/1") or "0/1").split("/")
        fps = float(num) / float(den) if float(den) else 0.0
        return dur, fps
    except Exception:
        return 0.0, 0.0


# ─── VRAM sampler (uniform for in-process AND subprocess engines) ─────────
class VRAMSampler:
    """
    Background thread sampling `nvidia-smi` every ~200 ms during generate().
    peak_vram_mb = max(samples) − baseline. If no GPU → returns 0.0.
    """

    def __init__(self, interval_s: float = 0.2):
        self.interval_s = interval_s
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._samples: list[float] = []
        self._baseline: float = 0.0

    @staticmethod
    def _query_mb() -> float:
        if not shutil.which("nvidia-smi"):
            return 0.0
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.used",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2,
            )
            return float(out.stdout.strip().splitlines()[0])
        except Exception:
            return 0.0

    def __enter__(self):
        self._baseline = self._query_mb()
        self._samples = [self._baseline]
        self._stop.clear()

        def _loop():
            while not self._stop.is_set():
                self._samples.append(self._query_mb())
                self._stop.wait(self.interval_s)

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)

    @property
    def peak_delta_mb(self) -> float:
        if not self._samples:
            return 0.0
        return max(0.0, max(self._samples) - self._baseline)


# ─── Shared ffmpeg re-encode helper (Rule E + timing per Change 4) ────────
def reencode_browser_safe(src: str, dst: str) -> float:
    """
    Re-encode to h264 + yuv420p + faststart. Returns encode_time_s.
    If ffmpeg fails or output is empty, moves src → dst (fallback).
    """
    t0 = time.perf_counter()
    ff = subprocess.run(
        ["ffmpeg", "-y", "-i", src,
         "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-preset", "ultrafast", "-crf", "23",
         "-c:a", "aac", "-b:a", "128k",
         "-movflags", "+faststart", dst],
        capture_output=True, text=True,
    )
    elapsed = time.perf_counter() - t0
    if ff.returncode != 0 or not os.path.isfile(dst) or os.path.getsize(dst) == 0:
        try:
            os.replace(src, dst)
        except OSError:
            pass
        return elapsed
    try:
        os.unlink(src)
    except OSError:
        pass
    return elapsed


# ─── Side-effect import: register all engines ─────────────────────────────
import core.engines  # noqa: E402, F401
