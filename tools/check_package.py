from __future__ import annotations
import base64, hashlib, json, marshal, os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def ok(msg): print("[PASS]", msg)
def fail(msg): print("[FAIL]", msg); raise SystemExit(1)

if sys.version_info[:2] != (3,13):
    fail(f"Python 3.13 required, got {sys.version.split()[0]}")
ok(f"Python {sys.version.split()[0]}")

try:
    import cryptography, PIL
except Exception as exc:
    fail(f"dependencies: {exc}")
ok("cryptography + Pillow")

for rel in [
    "open_runner.py",
    "tools/club_profile.py",
    "SET_CLUB_NAME.cmd",
    "SET_COINS.cmd",
    "SHOW_MY_CLUB.cmd",
    "runtime-open/runtime_entries.json",
    "localfut20/players.json",
    "localfut20/managers.json",
    "localfut20/player_pick_state.py",
    "promo_packs.py",
    "tests/test_player_pick_state.py",
    "runtime-source/certs/spring18-cert.pem",
    "runtime-source/certs/spring18-key.pem",
    "runtime-source/gos2015-original-modulus.bin",
    "runtime-source/local-gos2015-modulus.bin",
]:
    if not (ROOT/rel).is_file():
        fail(f"missing {rel}")
ok("required parity files")

if (ROOT/"runtime/secure_payload.f20").exists() or (ROOT/"secure_runner.pyc").exists():
    fail("encrypted/private runtime artifacts are still present")
ok("no secure_payload.f20 / secure_runner.pyc")

obj=json.loads((ROOT/"runtime-open/runtime_entries.json").read_text(encoding="utf-8"))
entries=obj.get("entries",{})
expected={
 "localfut20.auth_guard","localfut20.config_loader","localfut20.sbc_catalog",
 "localfut20.offline_data","localfut20.control_server","localfut20.server",
 "redirector_tls","trust_patch"
}
if set(entries)!=expected:
    fail("runtime entry set mismatch: "+repr(sorted(entries)))
total=0
for name, meta in entries.items():
    code=marshal.loads(base64.b64decode(meta["code"]))
    total += 1
ok(f"plaintext runtime: {len(entries)} modules ({total} top-level code objects)")

# Ensure Discord/private launcher code was stripped from this runtime.
blob=(ROOT/"runtime-open/runtime_entries.json").read_text(encoding="utf-8", errors="ignore").lower()
if "discord.com/oauth2" in blob or "fut20_launch_token" in blob or "launcher-auth.json" in blob:
    fail("launcher authorization material unexpectedly present in runtime")
ok("Discord/session gate stripped from runtime")

# Python syntax for our readable wrapper/tools.
for rel in ["open_runner.py","promo_packs.py","localfut20/player_pick_state.py","tests/test_player_pick_state.py","tools/collect_diagnostics.py","tools/club_profile.py"]:
    compile((ROOT/rel).read_text(encoding="utf-8"), str(ROOT/rel), "exec")
ok("readable Python wrapper/tools syntax")

result=subprocess.run([sys.executable,str(ROOT/"tests/test_player_pick_state.py")],cwd=ROOT,text=True,capture_output=True)
if result.returncode:
    fail("Player Pick lifecycle: "+result.stdout+result.stderr)
ok(result.stdout.strip())


# CSV-driven player database validation.
players = json.loads((ROOT/"localfut20"/"players.json").read_text(encoding="utf-8"))
if not isinstance(players, dict):
    fail("players.json is not a JSON object")
required_player_fields = {
    "name","rating","preferredPosition","leagueId","teamid","nation",
    "assetId","resourceId","rareflag","rarityName","rarityClass","tier","special","face"
}
csv_rows = 0
for key, meta in players.items():
    if not isinstance(meta, dict):
        fail(f"invalid player record {key}")
    if int(key) != int(meta.get("resourceId",-1)):
        fail(f"player key/resourceId mismatch at {key}")
    missing = required_player_fields.difference(meta)
    if missing:
        fail(f"player {key} missing fields: {sorted(missing)}")
    if isinstance(meta.get("csvSource"), dict):
        csv_rows += 1
if len(players) < 25000:
    fail(f"CSV player catalog unexpectedly small: {len(players)}")
if csv_rows != 25034:
    fail(f"expected 25,034 CSV-backed rows, found {csv_rows}")
cfg = json.loads((ROOT/"localfut20"/"config.json").read_text(encoding="utf-8"))
missing_starters=[rid for rid in cfg.get("starter_players",[]) if str(rid) not in players]
if missing_starters:
    fail(f"starter player IDs missing from CSV catalog: {missing_starters}")
ok(f"CSV player database: {len(players)} definitions / {csv_rows} CSV-backed rows")

print()
print("OPENFUT20 PARITY PACKAGE CHECK: PASS")
