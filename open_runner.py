from __future__ import annotations

import base64
import importlib.abc
import importlib.util
import json
import marshal
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "runtime-open" / "runtime_entries.json"

ALIASES = {
    "auth_guard": "localfut20.auth_guard",
    "config_loader": "localfut20.config_loader",
    "sbc_catalog": "localfut20.sbc_catalog",
}
ENTRY_ALIASES = {
    "offline_data": "localfut20.offline_data",
    "control_server": "localfut20.control_server",
    "server": "localfut20.server",
}

def _load_entries():
    obj = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    if obj.get("format") != "OpenFUT20-plaintext-runtime-v1":
        raise SystemExit("Invalid OpenFUT20 runtime format.")
    entries = obj.get("entries")
    if not isinstance(entries, dict):
        raise SystemExit("Invalid OpenFUT20 runtime: missing entries.")
    return entries

E = _load_entries()

def _code(name: str):
    return marshal.loads(base64.b64decode(E[name]["code"]))

def _walk_code(code):
    yield code
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            yield from _walk_code(const)

class OpenPayloadLoader(importlib.abc.Loader):
    def __init__(self, fullname: str, target: str):
        self.fullname = fullname
        self.target = target

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        meta = E[self.target]
        module.__file__ = str(ROOT / meta["file"])
        module.__package__ = self.fullname.rpartition(".")[0]
        module.__loader__ = self
        exec(_code(self.target), module.__dict__, module.__dict__)

class OpenPayloadFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        mapped = ALIASES.get(fullname, fullname)
        if mapped in E and mapped not in {"redirector_tls", "trust_patch"}:
            return importlib.util.spec_from_loader(
                fullname,
                OpenPayloadLoader(fullname, mapped),
                origin=str(ROOT / E[mapped]["file"]),
            )
        return None

sys.meta_path.insert(0, OpenPayloadFinder())
for q in (ROOT, ROOT / "localfut20", ROOT / "runtime-source"):
    s = str(q)
    if s not in sys.path:
        sys.path.insert(0, s)

def verify() -> int:
    expected = {
        "localfut20.auth_guard",
        "localfut20.config_loader",
        "localfut20.sbc_catalog",
        "localfut20.offline_data",
        "localfut20.control_server",
        "localfut20.server",
        "redirector_tls",
        "trust_patch",
    }
    missing = expected.difference(E)
    if missing:
        raise SystemExit("Missing runtime entries: " + ", ".join(sorted(missing)))
    total = 0
    for name in sorted(E):
        code = _code(name)
        count = sum(1 for _ in _walk_code(code))
        total += count
        print(f"[PASS] {name}: {count} code objects")
    print(f"[PASS] plaintext runtime verified: {len(E)} modules, {total} code objects")
    return 0

def run(name: str, args: list[str]) -> None:
    name = ENTRY_ALIASES.get(name, name)
    if name not in E:
        raise SystemExit(f"Unknown OpenFUT20 runtime component: {name}")
    meta = E[name]
    old_argv = sys.argv[:]
    sys.argv = [str(ROOT / meta["file"]), *args]
    ns = {
        "__name__": "__main__",
        "__file__": str(ROOT / meta["file"]),
        "__package__": None,
        "__cached__": None,
        "__loader__": None,
        "__builtins__": __builtins__,
    }
    try:
        exec(_code(name), ns, ns)
    finally:
        sys.argv = old_argv

if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--verify":
        raise SystemExit(verify())
    if len(sys.argv) < 2:
        print("OpenFUT20 local runtime components:")
        for name in sorted(E):
            print(" -", name)
        raise SystemExit(0)
    run(sys.argv[1], sys.argv[2:])
