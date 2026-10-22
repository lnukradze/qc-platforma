# -*- coding: utf-8 -*-
"""
განაწილების წყარო — NAPR_Distributor-ის ლოკალური ბაზა (REGFIELDALL GDB-ის ასლი).

🔒 იხსნება **მხოლოდ წასაკითხად** (`mode=ro`): ამ ბაზაში არაფერი იწერება.
საწარმოო ვერსიაში აქ იქნება ღამის იმპორტი GDB-დან (ან სააგენტოს ბაზის
view-დან) PostgreSQL-ში — ფუნქციების ინტერფეისი იგივე დარჩება.

კანდიდატის წესი (ძველი პროგრამიდან, უცვლელი): კოდი შემოდის, თუ მისი
**პირველი** ოქმი (უადრესი MOX_CREATE_DATE) დიაპაზონშია; „სისტემური სერვისის"
ოქმები სრულად იგნორირდება.
"""
import sqlite3
import urllib.parse
from pathlib import Path

from ...config import DISTRIBUTOR_DB

SYS = "COALESCE({a}.oqmi_creator,'') <> 'სისტემური სერვისი'"


def connect(path: Path = DISTRIBUTOR_DB):
    if not Path(path).exists():
        raise FileNotFoundError(f"განაწილების ბაზა ვერ მოიძებნა: {path}")
    uri = "file:" + urllib.parse.quote(str(path).replace("\\", "/")) + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    return con


def source_info(path: Path = DISTRIBUTOR_DB) -> dict:
    try:
        con = connect(path)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}
    try:
        row = con.execute("SELECT gdb_name, imported_at, feature_count FROM import_meta "
                          "ORDER BY id DESC LIMIT 1").fetchone()
        rng = con.execute("SELECT MAX(mox_create_date) FROM parcels").fetchone()
        return {"ok": True, "gdb_name": row["gdb_name"], "imported_at": row["imported_at"],
                "rows": row["feature_count"], "max_date": (rng[0] or "")[:10], "path": str(path)}
    finally:
        con.close()


def query_candidates(start_iso: str, end_iso: str, path: Path = DISTRIBUTOR_DB) -> list[dict]:
    """[start, end] დიაპაზონის კოდები პირველი ოქმის მიხედვით (`'YYYY-MM-DD'`)."""
    end_excl = end_iso + "Z"            # 'T' < 'Z' → მოიცავს მთელ ბოლო დღეს
    first = lambda col, a: (f"(SELECT {a}.{col} FROM parcels {a} WHERE {a}.cadcode = f.cadcode "
                            f"AND {SYS.format(a=a)} ORDER BY {a}.mox_create_date ASC, "
                            f"{a}.fld_paper_id ASC LIMIT 1)")
    sql = f"""
    WITH in_range AS (
        SELECT DISTINCT cadcode FROM parcels
        WHERE mox_create_date >= ? AND mox_create_date < ?
          AND cadcode IS NOT NULL AND cadcode <> '' AND {SYS.format(a='parcels')}
    ),
    firstok AS (
        SELECT c.cadcode FROM in_range c
        WHERE NOT EXISTS (SELECT 1 FROM parcels p WHERE p.cadcode = c.cadcode
                          AND p.mox_create_date < ? AND {SYS.format(a='p')})
    )
    SELECT f.cadcode AS cadcode,
           (SELECT MIN(p2.mox_create_date) FROM parcels p2
             WHERE p2.cadcode = f.cadcode AND {SYS.format(a='p2')}) AS first_dt,
           (SELECT COUNT(DISTINCT p3.fld_paper_id) FROM parcels p3
             WHERE p3.cadcode = f.cadcode AND {SYS.format(a='p3')}) AS protocol_count,
           {first('fld_paper_id', 'p4')} AS first_paper_id,
           {first('moxaz_creator', 'p5')} AS first_moxaz,
           {first('oqmi_creator', 'p6')} AS first_oqmi,
           {first('fld_status_name', 'p7')} AS first_status
    FROM firstok f
    ORDER BY first_dt ASC, f.cadcode ASC
    """
    con = connect(path)
    try:
        out = []
        for r in con.execute(sql, (start_iso, end_excl, start_iso)):
            pid = r["first_paper_id"]
            try:
                pid = str(int(round(float(pid)))) if pid is not None else ""
            except (TypeError, ValueError):
                pid = str(pid)
            out.append({"cadcode": r["cadcode"], "disp_dt": r["first_dt"],
                        "protocol_count": int(r["protocol_count"] or 0),
                        "first_paper_id": pid,
                        "first_moxaz": r["first_moxaz"] or "", "first_oqmi": r["first_oqmi"] or "",
                        "first_status": r["first_status"] or ""})
        return out
    finally:
        con.close()


def lookup_protocols(protocol_numbers, path: Path = DISTRIBUTOR_DB) -> dict:
    """
    ოქმის ნომრით (FLD_PAPER_ID) → [{cadcode, oqmi, moxaz, status, created}] — სპორადულისთვის.

    სპორადულ ოქმებზე OQMI_CREATOR „სისტემური სერვისია", ნამდვილი ამზომველი MOXAZ_CREATOR-ია
    (შემოწმდა ძველ ჩანაწერებზე: 95% ემთხვევა, 2026-10-20). ერთი გავლა, IN-სიით.
    """
    ids = []
    for x in protocol_numbers or []:
        try:
            ids.append(float(str(x).strip()))
        except ValueError:
            continue
    out = {}
    if not ids:
        return out
    con = connect(path)
    try:
        for i in range(0, len(ids), 900):
            chunk = ids[i:i + 900]
            for r in con.execute(
                    "SELECT fld_paper_id, cadcode, oqmi_creator, moxaz_creator, fld_status_name, "
                    "mox_create_date FROM parcels WHERE fld_paper_id IN (%s)" % ",".join("?" * len(chunk)),
                    chunk):
                pid = str(int(round(float(r["fld_paper_id"]))))
                out.setdefault(pid, []).append({
                    "cadcode": r["cadcode"], "oqmi": r["oqmi_creator"] or "",
                    "moxaz": r["moxaz_creator"] or "", "status": r["fld_status_name"] or "",
                    "created": r["mox_create_date"] or ""})
        return out
    finally:
        con.close()
