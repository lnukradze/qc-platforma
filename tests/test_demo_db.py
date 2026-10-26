# -*- coding: utf-8 -*-
"""T-006: დემო ბაზა — მხოლოდ დროებით საქაღალდეებში და გამოგონილი მონაცემით.

სკრიპტი ცალკე პროცესში ეშვება (როგორც ადამიანი უშვებს): ასე მოწმდება, რომ მემკვიდრეობით
მიღებული QCP_* ცვლადები (ბაზის მისამართი, წყარო, SMTP) დემოს იზოლაციას ვერ არღვევს.
"""
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from app import domain as D
from app.services.people import name_key
from app.services.seed import DEVELOPER_ADMINS, QC_MANAGERS

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_demo_db.py"
ITEMS = "200"


def run(*args, cwd=None, env_extra=None):
    env = dict(os.environ, PYTHONIOENCODING="utf-8", **(env_extra or {}))
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd or ROOT, env=env,
                          capture_output=True, text=True, encoding="utf-8", timeout=300)


def snapshot(folder: Path):
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """ერთხელ აწყობილი დემო; „რეალური" გარემო — ყალბი ფაილები, რომლებსაც სკრიპტი არ უნდა შეეხოს."""
    base = tmp_path_factory.mktemp("demo")
    fake_real = base / "fake-real"
    fake_real.mkdir()
    sentinel = fake_real / "real.db"
    env = {"QCP_DATA_DIR": str(fake_real), "QCP_DATABASE_URL": f"sqlite:///{sentinel.as_posix()}",
           "QCP_DISTRIBUTOR_DB": str(fake_real / "napr_data.sqlite"), "QCP_SMTP_HOST": "smtp.invalid"}
    out = base / "qc-demo-data"
    r = run("--out", str(out), "--items", ITEMS, env_extra=env)
    assert r.returncode == 0, r.stderr
    return out, fake_real, r


def query(db_file, sql, *params):
    con = sqlite3.connect(f"file:{db_file.as_posix()}?mode=ro", uri=True)
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


def test_build_covers_every_state(built):
    out, _, _ = built
    db = out / "platform.db"
    states = dict(query(db, "SELECT state, COUNT(*) FROM qc_items GROUP BY state"))
    assert all(states.get(s, 0) >= 3 for s in D.STATES), states
    verdicts = {v for (v,) in query(db, "SELECT DISTINCT verdict FROM qc_items") if v}
    assert verdicts == set(D.VERDICTS)
    decisions = {v for (v,) in query(db, "SELECT DISTINCT qcm_decision FROM qc_items") if v}
    assert decisions == {D.QCM_STAND, D.QCM_FIELD_RIGHT, D.QCM_BOTH_RIGHT}
    roles = {r for (r,) in query(db, "SELECT DISTINCT role FROM user_roles")}
    assert roles == set(D.ROLES)
    kinds = {k for (k,) in query(db, "SELECT DISTINCT kind FROM qc_items")}
    assert kinds == {D.SYSTEMATIC, D.SPORADIC}
    assert query(db, "SELECT COUNT(*) FROM qc_items")[0][0] == int(ITEMS)
    assert query(db, "SELECT COUNT(*) FROM preqc_checks")[0][0] > 0
    assert query(db, "SELECT COUNT(*) FROM emails")[0][0] > 0
    assert (out / "distributor.sqlite").is_file() and (out / "sporadic_demo.xlsx").is_file()
    assert not (out / "raw").exists()


def test_only_fake_people_and_numbers(built):
    out, _, _ = built
    db = out / "platform.db"
    emails = [e for (e,) in query(db, "SELECT email FROM users")]
    assert emails and all(e and e.endswith("@example.com") for e in emails)
    real = {name_key(n) for n in DEVELOPER_ADMINS} | {name_key(n) for n, _ in QC_MANAGERS}
    assert not real & {k for (k,) in query(db, "SELECT name_key FROM users")}
    assert all(p.startswith("000") for (p,) in query(db, "SELECT personal_id FROM users") if p)
    for table in ("qc_items", "preqc_checks"):
        assert all(n.startswith("9") for (n,) in query(db, f"SELECT protocol_number FROM {table}"))


def test_marked_as_demo(built):
    out, _, _ = built
    (value,) = query(out / "platform.db", "SELECT value FROM settings WHERE key = 'demo_dataset'")[0]
    marker = json.loads(value)
    assert marker["generator"] == "scripts/build_demo_db.py" and marker["version"] >= 1


def test_inherited_real_config_is_overridden(built):
    _, fake_real, r = built
    assert list(fake_real.iterdir()) == []            # ბაზის მისამართი, წყარო — არაფერი შეიქმნა
    assert "smtp.invalid" not in r.stdout + r.stderr


def test_second_run_without_force_refuses(built):
    out, _, _ = built
    before = snapshot(out)
    r = run("--out", str(out), "--items", ITEMS)
    assert r.returncode == 2 and "--force" in r.stderr
    assert snapshot(out) == before


def test_force_rebuilds_marked_demo_only(tmp_path):
    out = tmp_path / "demo"
    assert run("--out", str(out), "--items", ITEMS).returncode == 0
    (out / "notes.txt").write_text("სხვისი ფაილი", encoding="utf-8")
    r = run("--out", str(out), "--items", ITEMS, "--force")
    assert r.returncode == 0, r.stderr
    assert (out / "notes.txt").read_text(encoding="utf-8") == "სხვისი ფაილი"   # საქაღალდე არ წაიშალა


@pytest.mark.parametrize("marker", [None, {"generator": "something-else", "version": 1}, "not-json{"])
def test_force_refuses_unmarked_database(tmp_path, marker):
    out = tmp_path / "other"
    out.mkdir()
    db = out / "platform.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    if marker is not None:
        con.execute("INSERT INTO settings VALUES ('demo_dataset', ?)",
                    (marker if isinstance(marker, str) else json.dumps(marker),))
    con.commit()
    con.close()
    before = snapshot(out)
    r = run("--out", str(out), "--items", ITEMS, "--force")
    assert r.returncode == 2 and "მონიშნული" in r.stderr
    assert snapshot(out) == before


def test_refuses_project_data_folder(tmp_path):
    project = tmp_path / "fake-project"
    (project / "data").mkdir(parents=True)
    (project / "data" / "platform.db").write_bytes(b"real-looking bytes")
    before = snapshot(project)
    r = run("--out", "data", "--items", ITEMS, cwd=project)
    assert r.returncode == 2 and "უარი" in r.stderr
    assert snapshot(project) == before


@pytest.mark.parametrize("sub", ["with-raw", "inside/raw/demo"])
def test_refuses_raw(tmp_path, sub):
    out = tmp_path / sub
    if sub == "with-raw":
        (out / "raw").mkdir(parents=True)
    r = run("--out", str(out), "--items", ITEMS)
    assert r.returncode == 2 and "raw" in r.stderr
    assert not (out / "platform.db").exists()
    assert not any(p.is_file() for p in tmp_path.rglob("*"))


def test_refuses_too_few_items(tmp_path):
    r = run("--out", str(tmp_path / "demo"), "--items", "5")
    assert r.returncode == 2 and "--items" in r.stderr
    assert not (tmp_path / "demo").exists()
