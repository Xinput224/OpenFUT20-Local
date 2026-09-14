from __future__ import annotations
import json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
p=json.loads((ROOT/"localfut20"/"players.json").read_text(encoding="utf-8"))
csv_count=sum(1 for v in p.values() if isinstance(v,dict) and isinstance(v.get("csvSource"),dict))
hold=sum(1 for v in p.values() if isinstance(v,dict) and v.get("catalogSource")=="0.2.1-compatibility-holdover")
synthetic=sum(1 for v in p.values() if isinstance(v,dict) and str(v.get("nativeDatabase",{}).get("table","")).startswith("csv.synthetic"))
r=Counter(str(v.get("rarityName","Unknown")) for v in p.values() if isinstance(v,dict))
print("OpenFUT20 CSV Player Database")
print("="*52)
print(f"Total player/card definitions : {len(p):,}")
print(f"CSV-backed card rows          : {csv_count:,}")
print(f"Compatibility holdovers       : {hold:,}")
print(f"Synthetic base assets         : {synthetic:,}")
print()
print("Top rarities")
for name,count in r.most_common(20):
    print(f"{name:32} {count:>6,}")
print()
print("Active database:")
print(ROOT/"localfut20"/"players.json")
