from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import time
import traceback
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = ROOT / "logs" / "crash-reports"
REPORT_ROOT.mkdir(parents=True, exist_ok=True)

parser = argparse.ArgumentParser(description="Collect OpenFUT20 FIFA/player-pick exit diagnostics")
parser.add_argument("--reason", default="manual", help="Reason recorded in the report metadata")
parser.add_argument("--keep", type=int, default=10, help="How many previous report ZIPs to keep")
args = parser.parse_args()

stamp = time.strftime("%Y%m%d-%H%M%S")
tmp = REPORT_ROOT / f".collecting-{stamp}-{os.getpid()}"
tmp.mkdir(parents=True, exist_ok=True)


def copy_file(src: Path, dst: Path) -> None:
    try:
        if not src.is_file():
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    except Exception as exc:
        errors.append(f"copy {src}: {exc!r}")


def copy_rel(rel: str, dest_name: str | None = None) -> None:
    src = ROOT / rel
    dst = tmp / (dest_name or rel.replace("/", "__").replace("\\", "__"))
    copy_file(src, dst)


def run_cmd(name: str, cmd: list[str] | str, timeout: int = 25) -> None:
    try:
        cp = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            shell=isinstance(cmd, str),
        )
        (tmp / name).write_text(
            (cp.stdout or "") + "\n--- STDERR ---\n" + (cp.stderr or "") + f"\n--- EXIT CODE ---\n{cp.returncode}\n",
            encoding="utf-8",
            errors="replace",
        )
    except Exception:
        (tmp / name).write_text(traceback.format_exc(), encoding="utf-8", errors="replace")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


errors: list[str] = []

# 1) Copy every runtime log, including the detailed Blaze/FUT binary traces.
runtime_logs = ROOT / "runtime" / "logs"
if runtime_logs.is_dir():
    for src in runtime_logs.rglob("*"):
        if src.is_file():
            copy_file(src, tmp / "runtime_logs" / src.relative_to(runtime_logs))

# 2) Copy top-level runtime state/log files that are not necessarily under runtime/logs.
runtime_root = ROOT / "runtime"
if runtime_root.is_dir():
    for src in runtime_root.iterdir():
        if src.is_file() and src.suffix.lower() in {".log", ".json", ".txt"}:
            copy_file(src, tmp / "runtime_root" / src.name)

# 3) Build/config/source context needed to reproduce the exact run.
for rel in [
    "launcher-settings.json",
    "localfut20/config.json",
    "localfut20-manifest.json",
    "promo_packs.py",
    "START_LOCAL_FUT.cmd",
    "Launch-LocalFUT.ps1",
    "open_runner.py",
    "runtime/launcher-status.json",
    "runtime/status.json",
    "runtime/build-info.json",
    "runtime/launcher-profile.json",
    "runtime/launcher-processes.json",
    "runtime/session.json",
]:
    copy_rel(rel)

# 4) Safely snapshot SQLite while Local FUT is still alive. SQLite backup is preferable
#    to raw-copying an open WAL-mode database.
db = ROOT / "runtime" / "data" / "localfut20.sqlite3"
if db.is_file():
    try:
        src = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=5)
        dst_path = tmp / "localfut20-snapshot.sqlite3"
        dst = sqlite3.connect(dst_path)
        src.backup(dst)
        dst.close()
        src.close()
    except Exception:
        errors.append("sqlite backup:\n" + traceback.format_exc())

    try:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=5)
        con.row_factory = sqlite3.Row
        schema = [
            dict(r)
            for r in con.execute(
                "SELECT type,name,tbl_name,sql FROM sqlite_master "
                "WHERE type IN ('table','index') ORDER BY type,name"
            )
        ]
        (tmp / "sqlite_schema.json").write_text(
            json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        tables = [r["name"] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        recent: dict[str, object] = {}
        for table in tables:
            try:
                cols = [r["name"] for r in con.execute(f'PRAGMA table_info("{table}")')]
                order = "id DESC" if "id" in cols else "rowid DESC"
                rows = [dict(r) for r in con.execute(f'SELECT * FROM "{table}" ORDER BY {order} LIMIT 120')]
                recent[table] = rows
            except Exception as exc:
                recent[table] = {"error": repr(exc)}
        (tmp / "sqlite_recent_rows.json").write_text(
            json.dumps(recent, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
        )
        con.close()
    except Exception:
        errors.append("sqlite inspection:\n" + traceback.format_exc())

# 5) Windows/process/network crash context. These commands are read-only.
run_cmd("tasklist.txt", ["tasklist", "/v"])
run_cmd("netstat.txt", ["netstat", "-ano"])
run_cmd(
    "application_events.txt",
    [
        "wevtutil", "qe", "Application",
        "/q:*[System[TimeCreated[timediff(@SystemTime) <= 1800000]]]",
        "/f:text", "/c:350",
    ],
)
run_cmd(
    "wer_events.txt",
    [
        "wevtutil", "qe", "Application",
        '/q:*[System[Provider[@Name="Windows Error Reporting"] and TimeCreated[timediff(@SystemTime) <= 1800000]]]',
        "/f:text", "/c:150",
    ],
)
run_cmd(
    "app_error_events.txt",
    [
        "wevtutil", "qe", "Application",
        '/q:*[System[Provider[@Name="Application Error"] and TimeCreated[timediff(@SystemTime) <= 1800000]]]',
        "/f:text", "/c:150",
    ],
)

# 6) Hash critical files so each report identifies the exact build actually run.
critical = [
    "promo_packs.py",
    "START_LOCAL_FUT.cmd",
    "Launch-LocalFUT.ps1",
    "open_runner.py",
    "runtime-open/runtime_entries.json",
    "launcher-settings.json",
]
hashes: dict[str, str] = {}
for rel in critical:
    path = ROOT / rel
    if path.is_file():
        try:
            hashes[rel] = sha256(path)
        except Exception as exc:
            errors.append(f"hash {rel}: {exc!r}")
(tmp / "sha256.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")

meta = {
    "created_local": time.strftime("%Y-%m-%d %H:%M:%S"),
    "created_epoch": time.time(),
    "reason": args.reason,
    "python": sys.version,
    "platform": platform.platform(),
    "package_root": str(ROOT),
    "report_directory": str(REPORT_ROOT),
    "purpose": "Automatic FIFA20 exit/crash diagnostics with native Player Pick confirmation tracing",
}
(tmp / "diagnostic_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
if errors:
    (tmp / "collector_errors.txt").write_text("\n\n".join(errors), encoding="utf-8", errors="replace")

zip_path = REPORT_ROOT / f"OpenFUT20-PlayerPick-Crash-{stamp}.zip"
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
    for path in tmp.rglob("*"):
        if path.is_file():
            zf.write(path, path.relative_to(tmp))
shutil.rmtree(tmp, ignore_errors=True)

# Keep only the newest N reports to avoid unbounded disk use.
try:
    reports = sorted(
        REPORT_ROOT.glob("OpenFUT20-PlayerPick-Crash-*.zip"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in reports[max(1, args.keep):]:
        old.unlink(missing_ok=True)
except Exception:
    pass

print(zip_path)
