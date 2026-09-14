from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETTINGS_PATH = ROOT / "launcher-settings.json"
CONFIG_PATH = ROOT / "localfut20" / "config.json"
RUNTIME_DIR = ROOT / "runtime"
DATA_DIR = RUNTIME_DIR / "data"
DEFAULT_DB = DATA_DIR / "localfut20.sqlite3"
BACKUP_DIR = RUNTIME_DIR / "backups"
MAX_CLUB_NAME = 15
MAX_COINS = 2_000_000_000


def load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return data


def atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def resolve_database_path(settings: dict) -> Path:
    value = str(settings.get("database_path") or "").strip()
    if not value:
        return DEFAULT_DB
    p = Path(value)
    if not p.is_absolute():
        p = ROOT / p
    return p.resolve()


def derive_abbr(name: str) -> str:
    compact = "".join(ch for ch in name.upper() if ch.isalnum())
    if not compact:
        return "FUT"
    words = ["".join(ch for ch in w.upper() if ch.isalnum()) for w in name.split()]
    words = [w for w in words if w]
    if len(words) >= 3:
        return "".join(w[0] for w in words[:3])
    if len(words) == 2:
        return (words[0][0] + words[1][:2])[:3].ljust(3, "X")
    return compact[:3].ljust(3, "X")


def validate_name(value: str) -> str:
    value = " ".join(value.strip().split())
    if not value:
        raise ValueError("Club name cannot be empty.")
    if len(value) > MAX_CLUB_NAME:
        raise ValueError(f"Club name must be {MAX_CLUB_NAME} characters or fewer for FIFA 20 compatibility.")
    if any(ord(ch) < 32 for ch in value):
        raise ValueError("Club name contains unsupported control characters.")
    return value


def parse_coin_number(text: str, current: int | None = None, allow_delta: bool = True) -> int:
    raw = text.strip().replace(",", "").replace("_", "").replace(" ", "")
    if not raw:
        if current is None:
            raise ValueError("Coin amount cannot be empty.")
        return int(current)
    is_delta = allow_delta and raw[:1] in {"+", "-"}
    if not re.fullmatch(r"[+-]?\d+", raw):
        raise ValueError("Coins must be a whole number, for example 2500000 or +500000.")
    number = int(raw)
    result = int(current or 0) + number if is_delta else number
    if result < 0:
        raise ValueError("Coin balance cannot be negative.")
    if result > MAX_COINS:
        raise ValueError(f"Coin balance cannot exceed {MAX_COINS:,}.")
    return result


def read_db_value(db_path: Path, key: str):
    if not db_path.is_file():
        return None
    try:
        with sqlite3.connect(str(db_path), timeout=1.0) as conn:
            row = conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
            if not row:
                return None
            try:
                return json.loads(row[0])
            except Exception:
                return row[0]
    except sqlite3.Error:
        return None


def current_values(settings: dict, db_path: Path) -> tuple[str, int]:
    db_name = read_db_value(db_path, "club_name")
    db_coins = read_db_value(db_path, "credits")
    name = str(db_name if db_name not in (None, "") else settings.get("club_name", "OpenFUT FC"))
    try:
        coins = int(db_coins if db_coins is not None else settings.get("credits", 0))
    except Exception:
        coins = 0
    return name, coins


def backup_database(db_path: Path, reason: str) -> Path | None:
    if not db_path.is_file():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = BACKUP_DIR / f"before-{reason}-{stamp}.sqlite3"
    with sqlite3.connect(str(db_path), timeout=5.0) as src, sqlite3.connect(str(dest)) as dst:
        src.backup(dst)
    return dest


def update_db_fields(db_path: Path, values: dict[str, object]) -> bool:
    if not db_path.is_file():
        return False
    try:
        with sqlite3.connect(str(db_path), timeout=2.0) as conn:
            conn.execute("PRAGMA busy_timeout=2000")
            conn.execute("CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            sql = "INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value"
            for key, value in values.items():
                conn.execute(sql, (key, json.dumps(value)))
            conn.commit()
        return True
    except sqlite3.OperationalError as exc:
        if "locked" in str(exc).lower() or "busy" in str(exc).lower():
            raise RuntimeError(
                "The Local FUT database is in use. Close FIFA 20 and run STOP_LOCAL_FUT.cmd, then try again."
            ) from exc
        raise


def set_club_name(name: str) -> tuple[Path | None, bool]:
    settings = load_json(SETTINGS_PATH)
    config = load_json(CONFIG_PATH)
    db_path = resolve_database_path(settings)
    name = validate_name(name)
    abbr = derive_abbr(name)
    backup = backup_database(db_path, "club-name")
    for obj in (settings, config):
        obj["club_name"] = name
        obj["club_abbr"] = abbr
    atomic_write_json(SETTINGS_PATH, settings)
    atomic_write_json(CONFIG_PATH, config)
    updated = update_db_fields(db_path, {"club_name": name, "club_abbr": abbr})
    return backup, updated


def set_coins(coins: int) -> tuple[Path | None, bool]:
    settings = load_json(SETTINGS_PATH)
    config = load_json(CONFIG_PATH)
    db_path = resolve_database_path(settings)
    backup = backup_database(db_path, "coins")
    for obj in (settings, config):
        obj["credits"] = int(coins)
    atomic_write_json(SETTINGS_PATH, settings)
    atomic_write_json(CONFIG_PATH, config)
    updated = update_db_fields(db_path, {"credits": int(coins)})
    return backup, updated


def main() -> int:
    parser = argparse.ArgumentParser(description="Edit the OpenFUT20 local club profile.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--set-club-name", action="store_true", help="Change only the FUT club name.")
    mode.add_argument("--set-coins", action="store_true", help="Change only the coin balance.")
    mode.add_argument("--show", action="store_true", help="Show the current local club profile.")
    parser.add_argument("--club-name")
    parser.add_argument("--coins")
    parser.add_argument("--yes", action="store_true", help="Skip interactive confirmation.")
    args = parser.parse_args()

    settings = load_json(SETTINGS_PATH)
    db_path = resolve_database_path(settings)
    current_name, current_coins = current_values(settings, db_path)

    if args.show:
        print(f"Club : {current_name}")
        print(f"Coins: {current_coins:,}")
        print(f"Save : {db_path}")
        return 0

    try:
        if args.set_club_name:
            if args.club_name is not None:
                new_name = validate_name(args.club_name)
            else:
                print("============================================================")
                print(" OpenFUT20 - SET CLUB NAME")
                print("============================================================")
                print(f"Current club: {current_name}")
                while True:
                    try:
                        new_name = validate_name(input("New club name: "))
                        break
                    except ValueError as exc:
                        print(f"[ERROR] {exc}")
            print(f"Club name: {new_name}")
            print(f"Club abbr: {derive_abbr(new_name)}")
            if not args.yes and input("Apply this change? [Y/N]: ").strip().lower() not in {"y", "yes"}:
                print("No changes were made.")
                return 0
            backup, db_updated = set_club_name(new_name)
            print("[PASS] Club name saved.")
        else:
            if args.coins is not None:
                new_coins = parse_coin_number(args.coins, current=current_coins, allow_delta=True)
            else:
                print("============================================================")
                print(" OpenFUT20 - SET COINS")
                print("============================================================")
                print(f"Current coins: {current_coins:,}")
                print("Use an exact balance (2500000) or a change (+500000 / -100000).")
                while True:
                    try:
                        new_coins = parse_coin_number(input("New coin balance: "), current=current_coins, allow_delta=True)
                        break
                    except ValueError as exc:
                        print(f"[ERROR] {exc}")
            print(f"Coin balance: {new_coins:,}")
            if not args.yes and input("Apply this change? [Y/N]: ").strip().lower() not in {"y", "yes"}:
                print("No changes were made.")
                return 0
            backup, db_updated = set_coins(new_coins)
            print("[PASS] Coin balance saved.")

        if db_updated:
            print("[PASS] Existing local FUT save updated.")
        else:
            print("[INFO] No local FUT database exists yet; this value will seed the next save.")
        if backup:
            print(f"[PASS] Previous save backed up to: {backup.relative_to(ROOT)}")
        print("[PASS] Players, squads and items were not reset.")
        return 0
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
