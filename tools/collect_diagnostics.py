from pathlib import Path
import json, shutil, time, zipfile, platform, sys, os

ROOT=Path(__file__).resolve().parents[1]
stamp=time.strftime("%Y%m%d-%H%M%S")
tmp=ROOT/"runtime"/f"diag-{stamp}"
tmp.mkdir(parents=True,exist_ok=True)

for rel in [
    "launcher-settings.json","localfut20/config.json","localfut20-manifest.json",
    "runtime/launcher-status.json","runtime/status.json","runtime/server.log",
    "runtime/server.error.log","runtime/control.log","runtime/control.error.log",
    "runtime/redirector.log","runtime/redirector.error.log","runtime/trust-patch.log",
    "runtime/offline-data.log","runtime/launcher-processes.json"
]:
    p=ROOT/rel
    if p.is_file():
        target=tmp/rel.replace("/","__").replace("\\","__")
        shutil.copy2(p,target)

env={
 "python":sys.version,
 "platform":platform.platform(),
 "cwd":str(ROOT),
 "runtime_entries":str(ROOT/"runtime-open/runtime_entries.json"),
}
(tmp/"environment.json").write_text(json.dumps(env,indent=2),encoding="utf-8")

z=ROOT/f"OpenFUT20-Diagnostics-{stamp}.zip"
with zipfile.ZipFile(z,"w",zipfile.ZIP_DEFLATED) as f:
    for p in tmp.iterdir():
        f.write(p,p.name)
shutil.rmtree(tmp,ignore_errors=True)
print(z)
