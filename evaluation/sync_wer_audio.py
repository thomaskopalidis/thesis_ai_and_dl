"""
Sync the "frozen reference set" of synthetic WER audio.

Policy (D-014):
- If the set exists in --drive (all 10 WAVs + transcripts.json + audio_manifest.json)
  AND all SHA-256 hashes match the manifest: copy to workspace, skip generation.
- If the edge-tts version differs from the one recorded in the manifest: WARNING, no regen.
- If anything is missing: ERROR (no silent regeneration), unless --regenerate is passed.
- With --regenerate: archive the old set to synthetic_archived_<YYYYMMDD>/ and
  generate a fresh set + fresh manifest.
- First run (no set in Drive): generate + save + write manifest.
- --drive is optional; without it, the script runs locally and only writes to the
  workspace (no caching).

Usage:
    python evaluation/sync_wer_audio.py
    python evaluation/sync_wer_audio.py --drive /content/drive/MyDrive/thesis_ai_and_dl/audio/synthetic
    python evaluation/sync_wer_audio.py --drive <path> --regenerate
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import shutil
import subprocess
import sys
from importlib import metadata as _ilmd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
import config  # noqa: E402

from evaluation.generate_wer_audio import (  # noqa: E402
    WER_QUESTION_IDS,
    QUESTIONS_PATH,
    OUT_DIR as WORKSPACE_AUDIO_DIR,
    TRANSCRIPTS_PATH as WORKSPACE_TRANSCRIPTS,
    VOICE as _GENERATION_VOICE,  # single source of truth: whichever voice the generator uses
    main as _generate_main,
)
import asyncio  # noqa: E402

MANIFEST_NAME = "audio_manifest.json"
EXPECTED_WAVS = [f"{qid}.wav" for qid in WER_QUESTION_IDS]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _ffprobe(path: Path) -> tuple[int, int, float]:
    """Return (sample_rate, channels, duration_s) via ffprobe."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=sample_rate,channels,duration",
         "-of", "json", str(path)],
        capture_output=True, text=True, timeout=10,
    )
    data = json.loads(out.stdout).get("streams", [{}])[0]
    return (
        int(data.get("sample_rate", 0) or 0),
        int(data.get("channels", 0) or 0),
        float(data.get("duration", 0.0) or 0.0),
    )


def _edge_tts_version() -> str:
    try:
        return _ilmd.version("edge-tts")
    except _ilmd.PackageNotFoundError:
        return "unknown"


def _build_manifest(audio_dir: Path) -> dict:
    files: dict[str, dict] = {}
    for name in EXPECTED_WAVS:
        p = audio_dir / name
        sr, ch, dur = _ffprobe(p)
        files[name] = {
            "sha256": _sha256(p),
            "size_bytes": p.stat().st_size,
            "sample_rate_hz": sr,
            "channels": ch,
            "duration_s": round(dur, 3),
        }
    # Include transcripts.json alongside WAVs (verified on copy, same as WAVs).
    transcripts_name = WORKSPACE_TRANSCRIPTS.name
    files[transcripts_name] = {
        "sha256": _sha256(WORKSPACE_TRANSCRIPTS),
        "size_bytes": WORKSPACE_TRANSCRIPTS.stat().st_size,
    }
    return {
        "created_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "edge_tts_version": _edge_tts_version(),
        "voice": _GENERATION_VOICE,  # bound to the generator, cannot drift
        "files": files,
    }


# ─── Policy actions ────────────────────────────────────────────────────────
def _copy_from_drive(drive_dir: Path, manifest: dict) -> None:
    """Copy WAVs + transcripts to workspace, verify SHA-256 of every file."""
    WORKSPACE_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    transcripts_name = WORKSPACE_TRANSCRIPTS.name

    for name, meta in manifest["files"].items():
        src = drive_dir / name
        # transcripts.json lives next to the audio dir in workspace, but inside drive_dir on Drive
        dst = WORKSPACE_TRANSCRIPTS if name == transcripts_name else WORKSPACE_AUDIO_DIR / name
        shutil.copy2(src, dst)
        actual = _sha256(dst)
        if actual != meta["sha256"]:
            raise RuntimeError(
                f"[CORRUPTED] {name} hash mismatch!\n"
                f"  expected (manifest): {meta['sha256']}\n"
                f"  actual   (workspace): {actual}\n"
                f"  The reference set has been altered. Investigate before continuing."
            )
    print(f"[OK] Copied {len(manifest['files'])} files from Drive, SHA-256 verified.")

    current = _edge_tts_version()
    pinned = manifest.get("edge_tts_version", "unknown")
    if current != pinned:
        print(
            f"[WARN] edge-tts version drift: manifest={pinned}, installed={current}. "
            f"Reference set remains frozen. If audio must be regenerated, pass --regenerate."
        )


def _generate_and_save(drive_dir: Path | None) -> None:
    """Generate fresh WAVs in workspace, build manifest, mirror to Drive (if given)."""
    print("[GEN] Generating fresh WAV set via edge-tts…")
    asyncio.run(_generate_main())

    manifest = _build_manifest(WORKSPACE_AUDIO_DIR)
    (WORKSPACE_AUDIO_DIR.parent / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[OK] Wrote manifest ({len(manifest['files'])} files, "
          f"edge-tts={manifest['edge_tts_version']}, voice={manifest['voice']}).")

    if drive_dir is not None:
        drive_dir.mkdir(parents=True, exist_ok=True)
        for name in EXPECTED_WAVS:
            shutil.copy2(WORKSPACE_AUDIO_DIR / name, drive_dir / name)
        shutil.copy2(WORKSPACE_TRANSCRIPTS, drive_dir / WORKSPACE_TRANSCRIPTS.name)
        shutil.copy2(
            WORKSPACE_AUDIO_DIR.parent / MANIFEST_NAME,
            drive_dir / MANIFEST_NAME,
        )
        print(f"[OK] Mirrored WAVs + transcripts + manifest to {drive_dir}")


def _archive_drive_set(drive_dir: Path) -> Path:
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    archive = drive_dir.parent / f"synthetic_archived_{stamp}"
    shutil.move(str(drive_dir), str(archive))
    print(f"[ARCHIVED] Previous set → {archive}")
    return archive


# ─── Entry point ───────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip())
    ap.add_argument("--drive", type=Path, default=None,
                    help="Drive-side cache dir (e.g. /content/drive/MyDrive/…/audio/synthetic). "
                         "Optional: without it, runs locally without caching.")
    ap.add_argument("--regenerate", action="store_true",
                    help="Force fresh generation. Archives the existing Drive set.")
    args = ap.parse_args()

    drive_dir: Path | None = args.drive

    # Local-only mode: generate once in workspace, no cache.
    if drive_dir is None:
        if WORKSPACE_AUDIO_DIR.exists() and all(
            (WORKSPACE_AUDIO_DIR / n).is_file() for n in EXPECTED_WAVS
        ) and WORKSPACE_TRANSCRIPTS.is_file():
            print("[LOCAL] WAVs already present in workspace, skipping generation.")
            return 0
        _generate_and_save(drive_dir=None)
        return 0

    manifest_path = drive_dir / MANIFEST_NAME
    all_present = (
        drive_dir.is_dir()
        and manifest_path.is_file()
        and (drive_dir / WORKSPACE_TRANSCRIPTS.name).is_file()
        and all((drive_dir / n).is_file() for n in EXPECTED_WAVS)
    )

    if args.regenerate:
        if drive_dir.is_dir():
            _archive_drive_set(drive_dir)
        _generate_and_save(drive_dir=drive_dir)
        return 0

    if not drive_dir.is_dir() or not any(drive_dir.iterdir() if drive_dir.is_dir() else []):
        # First run: nothing in Drive.
        print(f"[FIRST RUN] No existing set at {drive_dir}. Generating…")
        _generate_and_save(drive_dir=drive_dir)
        return 0

    if not all_present:
        missing = [n for n in EXPECTED_WAVS + [WORKSPACE_TRANSCRIPTS.name, MANIFEST_NAME]
                   if not (drive_dir / n).is_file()]
        print(
            f"[ERROR] Drive set at {drive_dir} is incomplete. Missing: {missing}\n"
            f"        Refusing to silently regenerate (would break comparability of "
            f"existing WER numbers). Pass --regenerate explicitly to archive the old "
            f"set and build a fresh one.",
            file=sys.stderr,
        )
        return 2

    # Happy path: everything present → verify + copy.
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    # Validate manifest covers exactly the expected files (WAVs + transcripts.json).
    expected = set(EXPECTED_WAVS) | {WORKSPACE_TRANSCRIPTS.name}
    manifest_names = set(manifest.get("files", {}).keys())
    if manifest_names != expected:
        print(
            f"[ERROR] Manifest file list does not match expected set.\n"
            f"        manifest: {sorted(manifest_names)}\n"
            f"        expected: {sorted(expected)}\n"
            f"        Pass --regenerate to rebuild.",
            file=sys.stderr,
        )
        return 2

    _copy_from_drive(drive_dir, manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
