import glob
import json
import shutil
import time
from typing import Any


def _campaign_norm(value: Any) -> str:
    return str(value or "").replace("\u2019", "'").strip().casefold()


def dedupe_campaigns(campaigns: Any) -> list:
    if not isinstance(campaigns, list):
        return [{"name": "", "progress": 0, "season": "", "drops": {}}]
    order = []
    by_key = {}
    for c in campaigns:
        if not isinstance(c, dict):
            continue
        name = str(c.get("name", "") or "")
        season = str(c.get("season", "") or "")
        key = (_campaign_norm(name), _campaign_norm(season))
        if key == ("", ""):
            continue
        drops_src = c.get("drops") or {}
        existing = by_key.get(key)
        if existing is None:
            existing = {
                "name": name,
                "progress": int(c.get("progress", 0) or 0),
                "season": season,
                "drops": {},
            }
            by_key[key] = existing
            order.append(key)
        else:
            if not existing["name"] and name:
                existing["name"] = name
            if not existing["season"] and season:
                existing["season"] = season
        if isinstance(drops_src, dict):
            for drop_name, value in drops_src.items():
                if not isinstance(value, dict):
                    continue
                prev = existing["drops"].get(drop_name)
                if (
                    not isinstance(prev, dict)
                    or int(value.get("current", 0) or 0)
                    >= int(prev.get("current", 0) or 0)
                ):
                    existing["drops"][drop_name] = dict(value)
    result = []
    for key in order:
        c = by_key[key]
        values = [
            int(v.get("progress", 0) or 0)
            for v in c["drops"].values()
            if isinstance(v, dict)
        ]
        if values:
            c["progress"] = int(sum(values) / len(values))
        result.append(c)
    if not result:
        result = [{"name": "", "progress": 0, "season": "", "drops": {}}]
    return result


ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
for path in glob.glob("data/users/*/accounts.json"):
    accs = json.load(open(path, encoding="utf-8"))
    if not isinstance(accs, list):
        continue
    changed = 0
    for a in accs:
        if not isinstance(a, dict):
            continue
        camps = a.get("campaigns")
        if not isinstance(camps, list):
            continue
        new = dedupe_campaigns(camps)
        if len(new) != len(camps):
            changed += 1
        a["campaigns"] = new
    shutil.copy(path, f"{path}.{ts}.bak")
    json.dump(accs, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"{path}: accounts={len(accs)} deduped_accounts={changed}")
print("cleanup done", ts)
