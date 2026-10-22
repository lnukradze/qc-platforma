# -*- coding: utf-8 -*-
"""
განაწილების ალგორითმი.

ძველი პროგრამიდან (NAPR_Distributor) — უცვლელი პრინციპები:
  1. ბლოკი = საკადასტრო კოდი ბოლო სეგმენტის გარეშე; ბლოკი **განუყოფელია**;
  2. ოპერატორებზე: დიდი ბლოკები ჯერ, ყველაზე ნაკლებად დატვირთულს (დანიშნული ÷ რაოდენობა).

ახალი (მომხმარებლის გადაწყვეტილება, 2026-10-20):
  • **პროცენტული დაფარვა** — ნაგულისხმევი (მაგ. 70%) + ზონის, სექტორის ან მენეჯერის
    საკუთარი პროცენტი; თუ რამდენიმე ერთდროულად ეხება — მოქმედებს **უფრო დიდი**.
    შერჩევა ხდება თითოეულ ზონაში × მენეჯერზე ცალკე, რომ „ყველა არეალიდან ~70%" იყოს;
  • ოპერატორის რაოდენობა **მაქსიმუმია** — რაც არ ჩაეტია, შემდეგ განაწილებაზე პირველი შედის;
  • მენეჯერების ძველი გათანაბრება („წყლის შევსება") პროცენტებმა ჩაანაცვლა.
"""
import math
from collections import defaultdict


# ── ბლოკები ───────────────────────────────────────────────────────────
def block_key(cadcode):
    """'202.69.11.60.030.017' → '202.69.11.60.030'. წერტილის გარეშე — თავისივე ჯგუფი."""
    s = ("" if cadcode is None else str(cadcode)).strip()
    if not s:
        return ""
    return s.rsplit(".", 1)[0]


def zone_of(cadcode):
    """'202.43.12.42.095.042' → '43' (cadastre.py-ის წესი)."""
    parts = str(cadcode or "").split("/")[0].strip().split(".")
    return parts[1].zfill(2) if len(parts) > 2 and parts[1].isdigit() else None


def sector_of(cadcode):
    parts = str(cadcode or "").split("/")[0].strip().split(".")
    if len(parts) > 2 and parts[1].isdigit() and parts[2].isdigit():
        return f"{parts[1].zfill(2)}.{parts[2].zfill(2)}"
    return None


def _norm_status(s):
    return " ".join(str(s or "").split())


def exclude_status(records, statuses):
    """ღია საველე წარმოების ოქმების გამორიცხვა. აბრუნებს (kept, {სტატუსი: რაოდენობა})."""
    bad = {_norm_status(s) for s in (statuses or []) if _norm_status(s)}
    if not bad:
        return list(records), {}
    kept, removed = [], {}
    for r in records:
        st = _norm_status(r.get("first_status"))
        if st in bad:
            removed[st] = removed.get(st, 0) + 1
        else:
            kept.append(r)
    return kept, removed


def group_blocks(records):
    """
    ჩანაწერები → {ბლოკი: {recs, n, zone, sector, manager_id, managers, first_dt, backlog}}.
    `manager_id` — ბლოკის პასუხისმგებელი მენეჯერი (უმრავლესობით), `managers` — ყველა.
    """
    out = {}
    for r in records:
        k = block_key(r.get("cadcode", ""))
        g = out.setdefault(k, {"recs": [], "mgr": defaultdict(int), "managers": set()})
        g["recs"].append(r)
        g["mgr"][r.get("manager_id")] += 1
        g["managers"].update(r.get("manager_ids") or [])
    for g in out.values():
        recs = g["recs"]
        g["n"] = len(recs)
        g["manager_id"] = max(g["mgr"], key=lambda m: (g["mgr"][m], str(m))) if g["mgr"] else None
        g["zone"] = zone_of(recs[0].get("cadcode"))
        g["sector"] = sector_of(recs[0].get("cadcode"))
        g["first_dt"] = min(str(r.get("disp_dt") or "") for r in recs)
        g["backlog"] = any(r.get("backlog") for r in recs)
        del g["mgr"]
    return out


# ── პროცენტული დაფარვა ────────────────────────────────────────────────
def normalize_rules(default_pct, rules):
    """UI-ის წესები → {"default": p, "zone": {..}, "sector": {..}, "manager": {id: p}}."""
    out = {"default": _pct(default_pct, 70), "zone": {}, "sector": {}, "manager": {}}
    for r in rules or []:
        t, key, p = r.get("type"), str(r.get("key") or "").strip(), _pct(r.get("pct"), None)
        if t not in ("zone", "sector", "manager") or not key or p is None:
            continue
        if t == "zone":
            key = key.zfill(2)
        elif t == "sector" and "." in key:
            z, s = key.split(".", 1)
            key = f"{z.zfill(2)}.{s.zfill(2)}"
        out[t][key] = max(p, out[t].get(key, 0))
    return out


def _pct(v, default):
    try:
        p = float(v)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(100.0, p))


def effective_pct(block, rules):
    """ბლოკზე მოქმედი პროცენტი: ზონა / სექტორი / ნებისმიერი მისი მენეჯერი — უფრო დიდი იმარჯვებს."""
    cands = []
    if block.get("zone") in rules["zone"]:
        cands.append(rules["zone"][block["zone"]])
    if block.get("sector") in rules["sector"]:
        cands.append(rules["sector"][block["sector"]])
    for m in block.get("managers") or ():
        if str(m) in rules["manager"]:
            cands.append(rules["manager"][str(m)])
    return max(cands) if cands else rules["default"]


def select_by_coverage(blocks, rules, rnd):
    """
    თითო ფენაში (პროცენტი × ზონა × მენეჯერი) შემთხვევით ირჩევა ბლოკები, სანამ
    შერჩეული კოდების რაოდენობა პროცენტს არ მიუახლოვდება. 100% — ყველა ბლოკი.
    აბრუნებს (შერჩეული ბლოკები, ფენების ანგარიში).
    """
    strata = defaultdict(list)
    for k, g in blocks.items():
        g["pct"] = effective_pct(g, rules)
        strata[(g["pct"], g["zone"] or "", g["manager_id"] or 0)].append(k)
    chosen, report = [], []
    for (p, zone, mgr), keys in sorted(strata.items(), key=lambda x: (-x[0][0], x[0][1], x[0][2])):
        total = sum(blocks[k]["n"] for k in keys)
        target = total if p >= 100 else int(round(total * p / 100.0))
        keys = sorted(keys)
        rnd.shuffle(keys)
        got = 0
        for k in keys:
            if got >= target:
                break
            n = blocks[k]["n"]
            if got == 0 or got + n - target <= target - got:   # მიზანს თუ აახლოებს
                chosen.append(k)
                got += n
        report.append({"pct": p, "zone": zone, "manager_id": mgr, "codes": total,
                       "target": target, "selected": got})
    return chosen, report


def fit_capacity(blocks, keys, capacity):
    """
    ოპერატორების ჯამურ რაოდენობაში ჩატევა. რიგი: წინა განაწილების ნაშთი → უფრო მაღალი
    პროცენტი → უფრო ძველი ოქმი. აბრუნებს (ჩატეული, ნაშთი).
    """
    order = sorted(keys, key=lambda k: (not blocks[k]["backlog"], -blocks[k].get("pct", 0),
                                        blocks[k]["first_dt"], k))
    take, rest, used = [], [], 0
    for k in order:
        n = blocks[k]["n"]
        if used + n <= capacity:
            take.append(k)
            used += n
        else:
            rest.append(k)
    return take, rest


def assign_to_operators(blocks, keys, quotas, rnd):
    """
    ბლოკები → ოპერატორები. ბლოკი ჯერ დიდიდან პატარისკენ; თითოეული ხვდება იმას,
    ვისაც **ყველაზე მცირე წილი** აქვს შევსებული (დანიშნული ÷ რაოდენობა), ტოლობისას —
    შემთხვევით. ტოლ რაოდენობებზე ეს იგივეა, რაც ძველი „ყველაზე ნაკლებად დატვირთული".
    აბრუნებს {ბლოკი: ოპერატორი} და {ოპერატორი: ოქმები}.
    """
    ops = [o for o, q in quotas.items() if q > 0]
    if not ops:
        raise ValueError("არცერთ ოპერატორს არ აქვს მითითებული რაოდენობა.")
    items = list(keys)
    rnd.shuffle(items)
    items.sort(key=lambda k: blocks[k]["n"], reverse=True)
    loads = {o: 0 for o in ops}
    out = {}
    for k in items:
        best = min(loads[o] / quotas[o] for o in ops)
        cand = [o for o in ops if abs(loads[o] / quotas[o] - best) < 1e-12]
        op = rnd.choice(sorted(cand))
        out[k] = op
        loads[op] += blocks[k]["n"]
    return out, loads


def split_even(total, ops):
    """რაოდენობის გარეშე მონიშნული ოპერატორები → თანაბარი მაქსიმუმი (სპორადული)."""
    if not ops:
        return {}
    per = math.ceil(total / len(ops)) if total else 0
    return {o: max(per, 1) for o in ops}
