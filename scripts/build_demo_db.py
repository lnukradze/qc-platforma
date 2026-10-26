# -*- coding: utf-8 -*-
"""
სადემონსტრაციო ბაზა — **მხოლოდ გამოგონილი მონაცემით** (T-006).

AI აგენტები მუშაობენ მხოლოდ ამ ბაზაზე; რეალურს ადამიანი ამოწმებს.
ბაზა ნულიდან იქმნება — `data\\raw`, Google ცხრილები, რეალური Excel-ები და
განაწილების რეალური წყარო **არ იკითხება**; `seed.py`-ის რეალური სახელები არ გამოიყენება.

  ნაგულისხმევი საქაღალდე: <მთავარი საქაღალდის მშობელი>\\qc-demo-data (git-ის გარეთ,
  ყველა worktree-სთვის ერთი). შიგთავსი:
    platform.db          — პლატფორმის ბაზა (Setting „demo_dataset“ — დემოს მონიშვნა)
    distributor.sqlite   — განაწილების გამოგონილი წყარო (source.py-ის სტრუქტურით)
    sporadic_demo.xlsx   — სპორადულის გამოგონილი ყოველდღიური ფაილი (ატვირთვის შესამოწმებლად)

გაშვება:
  & $env:QCP_PY scripts\\build_demo_db.py                  # ≈400 ოქმი
  & $env:QCP_PY scripts\\build_demo_db.py --items 45000    # სიჩქარის შესამოწმებლად
  & $env:QCP_PY scripts\\build_demo_db.py --force          # არსებული დემო ბაზის გადაწერა
  & $env:QCP_PY scripts\\build_demo_db.py --out <საქაღალდე>

🔐 სკრიპტი უარს ამბობს, თუ სამიზნე პროექტის `data`/`data-real`-ია, `raw`-ს შეიცავს, git-ის
   საქაღალდეშია, ან მასში უკვე არის ბაზა, რომელიც დემოდ არ არის მონიშნული.
"""
import argparse
import datetime as dt
import json
import os
import random
import sqlite3
import sys
import time
import types
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

DB_NAME = "platform.db"
SOURCE_NAME = "distributor.sqlite"
SPORADIC_NAME = "sporadic_demo.xlsx"
# მხოლოდ ეს ფაილები იცვლება გადაწერისას — საქაღალდე მთლიანად არასოდეს იშლება
ARTIFACTS = (DB_NAME, DB_NAME + "-wal", DB_NAME + "-shm", DB_NAME + "-journal", SOURCE_NAME,
             SPORADIC_NAME, ".session_secret")
MARKER_KEY = "demo_dataset"
GENERATOR = "scripts/build_demo_db.py"
MARKER_VERSION = 1
SEED = 20261026
DEFAULT_ITEMS = 400
FORBIDDEN_PARTS = {"data", "data-real", "raw"}

PROTO_ITEMS = 9_500_000         # ოქმები პლატფორმაში
PROTO_SOURCE = 9_700_000        # მხოლოდ განაწილების წყაროში (კანდიდატები)
PROTO_SPORADIC = 9_800_000      # სპორადულის ფაილი


class Refused(Exception):
    """სამიზნე სახიფათოა — არაფერი შეიცვლება."""


# ══════════════════════════════════════════════════════════════════════
#  სამიზნის შემოწმება (app-ის იმპორტამდე — config.py იმპორტისას საქაღალდეებს ქმნის)
# ══════════════════════════════════════════════════════════════════════
def main_checkout(root: Path) -> Path:
    """მთავარი საქაღალდე: worktree-ში `.git` ფაილია (gitdir: <main>/.git/worktrees/<name>)."""
    git = root / ".git"
    if git.is_file():
        line = git.read_text(encoding="utf-8", errors="replace").strip()
        if line.startswith("gitdir:"):
            gd = Path(line[len("gitdir:"):].strip())
            if not gd.is_absolute():
                gd = (root / gd).resolve()
            if gd.parent.name == "worktrees" and gd.parent.parent.name == ".git":
                return gd.parent.parent.parent
    return root


def default_out() -> Path:
    return main_checkout(ROOT).parent / "qc-demo-data"


def _known_real() -> list[Path]:
    """რეალური მონაცემის ცნობილი ადგილები — მათზე ბაზის გახსნაც კი არ ხდება."""
    main = main_checkout(ROOT)
    out = []
    for base in {main, ROOT}:
        out += [base / "data", base / "data-real", base.parent / "dzveli masalebi da saitebi",
                base.parents[1] / "კონტროლ;ის სტატისტიკა", base.parents[1] / "QCS"]
    return [Path(os.path.abspath(p)) for p in out]


def _same_or_inside(p: Path, base: Path) -> bool:
    a, b = os.path.normcase(str(p)), os.path.normcase(str(base))
    return a == b or a.startswith(b.rstrip("\\/") + os.sep)


def _is_link(p: Path) -> bool:
    return p.is_symlink() or p.is_junction()


def check_target(out: Path) -> Path:
    out = Path(os.path.abspath(out))
    real = Path(os.path.realpath(out))
    for p in (out, real):
        bad = {x.lower() for x in p.parts} & FORBIDDEN_PARTS
        if bad:
            raise Refused(f"სამიზნე „{p}“ შეიცავს საქაღალდეს „{sorted(bad)[0]}“ — "
                          "ეს რეალური მონაცემის ადგილია. აირჩიეთ სხვა საქაღალდე.")
        for known in _known_real():
            if _same_or_inside(p, known):
                raise Refused(f"სამიზნე „{p}“ რეალური მონაცემის საქაღალდეა ({known}).")
        for q in (p, *p.parents):
            if (q / ".git").exists():
                raise Refused(f"სამიზნე „{p}“ git-ის საქაღალდეშია ({q}) — დემო ბაზა git-ის გარეთ უნდა იყოს.")
    if out.exists():
        if _is_link(out):
            raise Refused(f"სამიზნე „{out}“ ბმულია (symlink/junction) სხვა ადგილზე — არ ვეხები.")
        if not out.is_dir():
            raise Refused(f"სამიზნე „{out}“ საქაღალდე არ არის.")
        if (out / "raw").exists():
            raise Refused(f"სამიზნეში არის „raw“ — ეს რეალური მონაცემის საქაღალდეა: {out}")
        for name in ARTIFACTS:
            f = out / name
            if _is_link(f) or (f.exists() and not f.is_file()):
                raise Refused(f"„{f}“ ჩვეულებრივი ფაილი არ არის (ბმული ან საქაღალდე) — არ ვეხები.")
    return out


def read_marker(db_file: Path):
    """მხოლოდ წაკითხვით: Setting „demo_dataset“. სხვა ცხრილი არ იკითხება. გაურკვეველი → None."""
    uri = "file:" + urllib.parse.quote(str(db_file).replace("\\", "/")) + "?mode=ro"
    try:
        con = sqlite3.connect(uri, uri=True, timeout=5)
        try:
            row = con.execute("SELECT value FROM settings WHERE key = ?", (MARKER_KEY,)).fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        return None
    if not row:
        return None
    try:
        v = json.loads(row[0]) if isinstance(row[0], str) else None
    except ValueError:
        return None
    if isinstance(v, dict) and v.get("generator") == GENERATOR and isinstance(v.get("version"), int):
        return v
    return None


def prepare_target(out: Path, force: bool):
    db_file = out / DB_NAME
    if db_file.exists():
        if not force:
            raise Refused(f"დემო ბაზა უკვე არსებობს: {db_file}\n"
                          "  გადასაწერად გაუშვით --force-ით (მხოლოდ დემოდ მონიშნულ ბაზაზე მუშაობს).")
        if read_marker(db_file) is None:
            raise Refused(f"„{db_file}“ დემოდ მონიშნული არ არის (ან დაზიანებულია) — არ ვეხები, "
                          "--force-ითაც. აირჩიეთ სხვა საქაღალდე.")
    out.mkdir(parents=True, exist_ok=True)
    for name in ARTIFACTS:
        f = out / name
        try:
            f.unlink(missing_ok=True)
        except PermissionError:
            raise Refused(f"„{f}“ დაკავებულია — ჯერ გააჩერეთ ამ ბაზაზე გაშვებული სერვერი.")


def isolate_env(out: Path):
    """მემკვიდრეობით მიღებული ცვლადები (ბაზის მისამართი, წყარო, SMTP, Google) — მხოლოდ დემოზე."""
    os.environ.update({
        "QCP_DATA_DIR": str(out),
        "QCP_DATABASE_URL": f"sqlite:///{(out / DB_NAME).as_posix()}",
        "QCP_DISTRIBUTOR_DB": str(out / SOURCE_NAME),
        "QCP_QC_WORKBOOK": str(out / "no-workbook.xlsx"),
        "QCP_SMTP_HOST": "", "QCP_SMTP_USER": "", "QCP_SMTP_PASSWORD": "",
        "QCP_GOOGLE_CLIENT_ID": "", "QCP_GOOGLE_CLIENT_SECRET": "", "QCP_BASE_URL": "",
    })
    os.environ.pop("QCP_SESSION_SECRET", None)


def min_items() -> int:
    return len(SCENARIOS) * 3


# ══════════════════════════════════════════════════════════════════════
#  გამოგონილი ტექსტი
# ══════════════════════════════════════════════════════════════════════
QC_TEXT = {
    "negative": ["ნაკვეთის საზღვარი ორთოფოტოს არ ემთხვევა (დემო)",
                 "F2-ში სავალდებულო შენიშვნა ცარიელია (დემო)",
                 "ფოტომასალა არასრულია — აკლია ნაკვეთის ხედი (დემო)",
                 "შენობა ნახაზზე არ არის ასახული (დემო)"],
    "recommendation": ["სასურველია ფოტოს დამატება სხვა კუთხიდან (დემო)",
                       "შენიშვნაში მიუთითეთ მიმთითებელი პირი (დემო)"],
    "clarification": ["დააზუსტეთ, რომელი შენობაა აზომილი? (დემო)",
                      "მეზობელი ნაკვეთის საზღვარი სადავოა? (დემო)"],
}
FIELD_TEXT = {
    "corrected": "გასწორდა, ნახაზი განახლებულია (დემო)",
    "acknowledge": "გავითვალისწინებთ შემდეგ ოქმებში (დემო)",
    "answer": "აზომილია მთავარი შენობა, დამხმარე ნაგებობა ნგრევადია (დემო)",
    "disagree": "საზღვარი ადგილზე დადასტურდა მიმთითებლის ჩვენებით (დემო)",
}
NORMAL_STATUS = "ოქმი დასრულებულია (დემო)"
TR_NAMES = ["სპორადული აზომვა (დემო)", "საზღვრის დაზუსტება (დემო)"]


# ══════════════════════════════════════════════════════════════════════
#  სცენარები — თითოეული ოქმს სამუშაო პროცესით (workflow.apply) ატარებს
# ══════════════════════════════════════════════════════════════════════
def _sent(v):
    return lambda r: r.send(v)


def _sent_respond(v, resp):
    return lambda r: (r.send(v), r.field("sv", resp))


def _disputed(r, v="negative"):
    r.send(v)
    r.field("sv", "disagree")
    r.do("fm", "manager_approve", comment="ვადასტურებ — ამზომველი მართალია (დემო)")


def _stand_with_manager(r):
    _disputed(r)
    r.do("qcm", "qcm_stand", comment="ხარვეზი რჩება: ორთოფოტოზე საზღვარი სხვაგანაა (დემო)",
         manager_required="on")
    r.email("qcm_stand")


def _two_surveyors(r):
    from app.workflow import WorkflowError
    r.send("negative")
    stale = r.item.version
    r.field("sv", "corrected")
    try:                                   # მეორე ამზომველი იმავე დროს — უკვე უპასუხეს
        r.do("sv2", "field_respond", response="corrected", comment=FIELD_TEXT["corrected"],
             version=stale)
    except WorkflowError:
        pass
    r.do("sv2", "comment", comment="ერთდროულად ვუპასუხე — პასუხი უკვე გაგზავნილი იყო (დემო)")


SCENARIOS = {
    # flags: two_sv — ორი ამზომველი ერთ გუნდში; no_mgr — მენეჯერი ვერ მოიძებნა
    "pending": ((), lambda r: None),
    "draft": ((), lambda r: r.do("op", "save_review", verdict="negative",
                                 qc_comment=r.text("negative"), codes=r.codes())),
    "positive": ((), _sent("positive")),
    "negative_sent": ((), lambda r: (r.send("negative"), r.email("sent"))),
    "recommendation_sent": ((), _sent("recommendation")),
    "clarification_sent": ((), _sent("clarification")),
    "corrected_waiting": ((), _sent_respond("negative", "corrected")),
    "acknowledged_waiting": ((), _sent_respond("recommendation", "acknowledge")),
    "answered_waiting": ((), _sent_respond("clarification", "answer")),
    "corrected_confirmed": ((), lambda r: (r.send("negative"), r.field("sv", "corrected"),
                                           r.do("op", "qc_confirm"))),
    "acknowledged_confirmed": ((), lambda r: (r.send("recommendation"), r.field("sv", "acknowledge"),
                                              r.do("op", "qc_confirm"))),
    "clarified_positive": ((), lambda r: (r.send("clarification"), r.field("sv", "answer"),
                                          r.do("op", "resolve_clarification", new_verdict="positive"))),
    "clarified_negative": ((), lambda r: (r.send("clarification"), r.field("sv", "answer"),
                                          r.do("op", "resolve_clarification", new_verdict="negative",
                                               qc_comment=r.text("negative"), codes=r.codes()))),
    "clarify_again": ((), lambda r: (r.send("clarification"), r.field("sv", "answer"),
                                     r.do("op", "clarify_again",
                                          comment="დამატებით: ფოტოზე შენობა არ ჩანს (დემო)"))),
    "disagree_surveyor": ((), _sent_respond("negative", "disagree")),
    "disagree_recommendation": ((), _sent_respond("recommendation", "disagree")),
    "manager_rejected": ((), lambda r: (r.send("negative"), r.field("sv", "disagree"),
                                        r.do("fm", "manager_reject",
                                             comment="ხარვეზი მართლაც არის — გაასწორე (დემო)"))),
    "disagree_at_qcm": ((), _disputed),
    "qcm_stand": ((), lambda r: (_disputed(r), r.do("qcm", "qcm_stand",
                                                    comment="ხარვეზი რჩება — იხ. ორთოფოტო (დემო)"),
                                 r.email("qcm_stand"))),
    "qcm_stand_manager": ((), _stand_with_manager),
    "qcm_field_right": ((), lambda r: (_disputed(r), r.do("qcm", "qcm_field_right", confirm_positive="on",
                                                          comment="ველი მართალია (დემო)"),
                                       r.email("qcm_field_right"))),
    "qcm_both_right": ((), lambda r: (_disputed(r, "recommendation"),
                                      r.do("qcm", "qcm_both_right", confirm_positive="on",
                                           comment="ორივე მხარე მართალია (დემო)"))),
    "manager_disagrees_again": ((), lambda r: (_stand_with_manager(r), r.do(
        "fm", "manager_respond", response="disagree",
        comment="მენეჯერი ისევ არ ეთანხმება — ადგილზე გადამოწმდა (დემო)"))),
    "manager_corrected": ((), lambda r: (_stand_with_manager(r), r.do(
        "fm", "manager_respond", response="corrected", comment=FIELD_TEXT["corrected"]))),
    "false_fix_returned": ((), lambda r: (r.send("negative"), r.field("sv", "corrected"),
                                          r.do("op", "qc_return",
                                               comment="არ არის გასწორებული — ნახაზი იგივეა (დემო)"),
                                          r.email("qc_returned"))),
    "returned_to_manager": ((), lambda r: (r.send("negative"), r.field("sv", "corrected"),
                                           r.do("op", "qc_return", manager_required="on",
                                                comment="მეორედ ბრუნდება — მენეჯერის ჩართვით (დემო)"),
                                           r.email("qc_returned"))),
    "manager_answers": ((), lambda r: (r.send("negative"), r.field("fm", "corrected"))),
    "verdict_request_pending": ((), lambda r: (r.send("negative"), r.do(
        "op", "request_verdict_change", new_verdict="recommendation",
        comment="ხარვეზი უმნიშვნელოა — რეკომენდაცია ჯობს (დემო)"))),
    "verdict_request_approved": ((), lambda r: (r.send("negative"), r.do(
        "op", "request_verdict_change", new_verdict="positive", comment="შეცდომით გავგზავნე (დემო)"),
        r.do("qcm", "approve_verdict_change", comment="ვეთანხმები (დემო)"))),
    "verdict_request_rejected": ((), lambda r: (r.send("recommendation"), r.do(
        "op", "request_verdict_change", new_verdict="positive", comment="გადავხედე — სწორია (დემო)"),
        r.do("qcm", "reject_verdict_change", comment="რეკომენდაცია რჩება (დემო)"))),
    "verdict_changed": ((), lambda r: (r.send("negative"), r.do(
        "qcm", "change_verdict", new_verdict="recommendation", comment="რეკომენდაციაა და არა ხარვეზი (დემო)"))),
    "two_surveyors": (("two_sv",), _two_surveyors),
    "reviewed_correct": ((), lambda r: (r.send("positive"), r.do("qcm", "review", marks=["correct"]))),
    "reviewed_missed": ((), lambda r: (r.send("negative"), r.field("sv", "corrected"), r.do("op", "qc_confirm"),
                                       r.do("qcm", "review", marks=["missed_defect", "incomplete_info"],
                                            comment="გამორჩა მეორე ხარვეზი (დემო)"))),
    "reassigned": ((), lambda r: r.do("qcm", "reassign", operator_id=str(r.other_operator().id))),
    "manager_assigned": (("no_mgr",), lambda r: r.do("qcm", "assign_manager",
                                                     manager_id=str(r.world.managers[0].id))),
    "no_manager": (("no_mgr",), lambda r: None),
    "commented": ((), lambda r: (r.send("negative"), r.do("sv", "comment", comment="ხვალ გავასწორებ (დემო)"),
                                 r.do("op", "comment", comment="გელოდებით (დემო)"), r.email("comment"))),
}
# შევსება ამ წონებით — რეალისტური ნარევი (დახურულები ჭარბობს)
FILL_WEIGHTS = {"positive": 30, "corrected_confirmed": 16, "acknowledged_confirmed": 8, "pending": 10,
                "negative_sent": 6, "recommendation_sent": 3, "clarification_sent": 2,
                "corrected_waiting": 4, "acknowledged_waiting": 2, "clarified_positive": 3,
                "disagree_surveyor": 1, "disagree_at_qcm": 1, "qcm_stand": 1, "qcm_field_right": 1,
                "qcm_both_right": 1, "false_fix_returned": 2, "manager_answers": 1, "draft": 2,
                "reviewed_correct": 3, "reviewed_missed": 1, "verdict_changed": 1}


# ══════════════════════════════════════════════════════════════════════
#  აწყობა
# ══════════════════════════════════════════════════════════════════════
def build(out: Path, n_items: int, seed: int):
    # app — მხოლოდ გარემოს დაყენების შემდეგ (config.py იმპორტისას ქმნის საქაღალდეებს)
    from sqlalchemy import func, select

    from app import config
    from app import domain as D
    from app import models as M
    from app import workflow
    from app.db import Base, SessionLocal, engine
    from app.services import notify, preqc_demo
    from app.services.distribution import algo
    from app.services.people import name_key
    from app.services.seed import DEFAULT_SETTINGS

    db_file = out / DB_NAME
    if (Path(config.DATA_DIR).resolve() != out.resolve()
            or config.DATABASE_URL != f"sqlite:///{db_file.as_posix()}"
            or Path(config.DISTRIBUTOR_DB).resolve() != (out / SOURCE_NAME).resolve()):
        raise Refused("აპლიკაციის კონფიგურაცია დემო საქაღალდეზე ვერ გადავიდა — ვჩერდები.")

    rnd = random.Random(seed)
    today = dt.date.today()
    real_now = dt.datetime.now().replace(microsecond=0)

    # ── საათი: workflow-ის დრო ოქმის „ცხოვრების" მიხედვით (ისტორია და სტატისტიკა თარიღებით) ──
    clock = types.SimpleNamespace(t=real_now)

    class _Clock(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return clock.t

    real_dt = workflow.dt
    workflow.dt = types.SimpleNamespace(datetime=_Clock, date=dt.date, timedelta=dt.timedelta)

    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        # მონიშვნა — პირველივე ჩანაწერი (შეწყვეტილი აწყობაც დემოდ რჩება და --force-ით გადაიწერება)
        db.add(M.Setting(key=MARKER_KEY, value={
            "generator": GENERATOR, "version": MARKER_VERSION, "seed": seed, "items": n_items,
            "built_at": real_now.isoformat()}))
        db.commit()

        codes = _seed_reference(db, config.SEED_DIR, DEFAULT_SETTINGS, M)
        world = _people(db, M, D, name_key)
        db.commit()

        run = M.DistributionRun(created_by_id=world.qcms[0].id, seed=seed, item_count=0,
                                created_at=real_now - dt.timedelta(days=120),
                                params={"date_from": (today - dt.timedelta(days=127)).isoformat(),
                                        "date_to": (today - dt.timedelta(days=121)).isoformat(),
                                        "default_pct": 70, "demo": True},
                                source_info={"ok": True, "gdb_name": "DEMO", "demo": True},
                                summary={"counts": {}, "operators": [], "demo": True})
        db.add(run)
        db.flush()

        order = [name for name in SCENARIOS for _ in range(3)]
        names, weights = zip(*FILL_WEIGHTS.items())
        order += rnd.choices(names, weights=weights, k=n_items - len(order))
        stats = {"items": 0, "emails": 0}
        t0 = time.time()
        for i, scen in enumerate(order):
            flags, fn = SCENARIOS[scen]
            rep = i % 3 if i < len(SCENARIOS) * 3 else rnd.randrange(10)
            kind = D.SPORADIC if rep == 2 or (rep > 2 and rnd.random() < 0.2) else D.SYSTEMATIC
            cc = rep == 1 and "two_sv" not in flags and "no_mgr" not in flags
            item = _new_item(db, M, D, algo, world, rnd, i, kind, flags, cc, run, clock, today, real_now)
            r = Runner(db, item, world, rnd, clock, codes, D, workflow, notify, M, stats)
            fn(r)
            stats["items"] += 1
            if (i + 1) % 500 == 0:
                db.commit()
                if n_items >= 5000:
                    print(f"  … {i + 1} / {n_items} ({time.time() - t0:.0f} წმ)", flush=True)
        run.item_count = db.scalar(select(func.count()).select_from(M.QcItem)
                                   .where(M.QcItem.distribution_run_id == run.id))
        db.commit()

        _extras(db, M, D, world, real_now, today)
        db.commit()

        demo = preqc_demo.build_demo(db)
        for chk in db.scalars(select(M.PreqcCheck)):        # ოქმის ნომერი 9…-ით (D- პრეფიქსის გარეშე)
            chk.protocol_number = chk.protocol_number.removeprefix("D-")
        db.commit()

        _ensure_emails(db, M)
        db.commit()
        report = _verify(db, M, D, name_key)
        report.update(stats, preqc=demo["checks"])
    finally:
        workflow.dt = real_dt
        db.close()
        engine.dispose()

    con = sqlite3.connect(db_file)                         # ერთი ფაილი, WAL-ის გარეშე
    try:
        con.execute("PRAGMA journal_mode=DELETE")
    finally:
        con.close()

    users = _source_names(db_file)
    report["source"] = build_source(out / SOURCE_NAME, users, rnd, today)
    report["sporadic_file"] = build_sporadic_file(out / SPORADIC_NAME, users, rnd, today)
    return report


def _seed_reference(db, seed_dir, default_settings, M):
    """ცნობარები — მხოლოდ რეპოს app/seed-იდან (რეალური მონაცემი არ არის)."""
    cat = json.loads((seed_dir / "code_catalog.json").read_text(encoding="utf-8"))
    for i, (code, c) in enumerate(cat["codes"].items()):
        db.add(M.DefectCode(code=code, name=c["name"], group=c["group"], severity=c["sev"],
                            page=c.get("page"), description=c.get("desc"), active=True, sort=i))
    p = cat.get("pending") or {}
    if p:
        db.add(M.DefectCode(code=p["code"], name=p["name"], group="დროებითი", severity="pending",
                            description=p.get("desc"), active=True, sort=99))
    ms = json.loads((seed_dir / "missions.json").read_text(encoding="utf-8"))
    for m in ms["missions"]:
        db.add(M.Mission(n=m["n"], start=dt.date.fromisoformat(m["start"]),
                         end=dt.date.fromisoformat(m["end"])))
    for k, v in default_settings.items():
        db.add(M.Setting(key=k, value=v))
    db.flush()
    return list(cat["codes"])


class World(types.SimpleNamespace):
    pass


def _people(db, M, D, name_key):
    """7 როლი; 4 საველე გუნდი; 6 ოპერატორი + ადმინი (ორი როლით); 2 QC მენეჯერი."""
    from app.services.preqc_demo import DEMO_MANAGER, DEMO_SURVEYORS
    n = [0]

    def user(name, *roles, active=True, **kw):
        n[0] += 1
        u = M.User(full_name=name, name_key=name_key(name), email=f"demo.user{n[0]:03d}@example.com",
                   personal_id=f"000{n[0]:08d}", active=active, is_demo=True, source="demo", **kw)
        for r in roles:
            u.roles.append(M.UserRole(role=r))
        db.add(u)
        db.flush()
        return u

    w = World()
    w.admin = user("ადმინისტრატორი (დემო)", D.ADMIN, D.QC_OPERATOR)
    w.qcms = [user("QC მენეჯერი ა", D.QC_MANAGER, prefs={"kind": "systematic"}),
              user("QC მენეჯერი ბ", D.QC_MANAGER, prefs={"kind": "sporadic"})]
    w.operators = [user(f"ოპერატორი {k:02d}", D.QC_OPERATOR) for k in range(1, 7)] + [w.admin]
    w.coordinator = user("კოორდინატორი (დემო)", D.COORDINATOR)
    w.head = user("სამსახურის უფროსი (დემო)", D.HEAD_OF_SERVICE)
    qc_team = M.Team(name="ხარისხის კონტროლი (დემო)", kind="qc", manager_id=w.qcms[0].id)
    db.add(qc_team)
    db.flush()
    for u in w.operators:
        db.add(M.TeamMember(team_id=qc_team.id, user_id=u.id, source="demo"))

    zones = ["36", "38", "51", "43"]
    team_defs = [("საველე მენეჯერი ა", [f"ამზომველი {k:02d}" for k in range(1, 5)]),
                 ("საველე მენეჯერი ბ", [f"ამზომველი {k:02d}" for k in range(5, 9)]),
                 ("საველე მენეჯერი გ", [f"ამზომველი {k:02d}" for k in range(9, 13)]),
                 (DEMO_MANAGER, DEMO_SURVEYORS)]          # Pre-QC-ის გუნდი (preqc_demo იყენებს)
    w.managers, w.teams = [], []
    for (mname, snames), zone in zip(team_defs, zones):
        m = user(mname, D.FIELD_MANAGER)
        t = M.Team(name=mname, kind="field", manager_id=m.id)
        db.add(t)
        db.flush()
        members = []
        for s in snames:
            u = user(s, D.SURVEYOR)
            db.add(M.TeamMember(team_id=t.id, user_id=u.id, source="demo"))
            members.append(u)
        w.managers.append(m)
        w.teams.append(types.SimpleNamespace(team=t, manager=m, surveyors=members, zone=zone))

    # წასული ამზომველები — Field Group-ში არიან, დღეს არცერთ გუნდში („დაუჯგუფებელი")
    w.departed = []
    for k, t in ((90, w.teams[0]), (91, w.teams[1]), (92, w.teams[2])):
        u = user(f"ამზომველი {k} (წასული)", D.SURVEYOR, active=False)
        db.add(M.TeamMember(team_id=t.team.id, user_id=u.id, source="demo",
                            valid_to=dt.date.today() - dt.timedelta(days=40)))
        w.departed.append(u)
    db.add(M.ManagerOverride(person_key=w.departed[2].name_key, person_name=w.departed[2].full_name,
                             manager_id=w.managers[2].id, set_by_id=w.qcms[0].id,
                             note="დემო: ხელით მიწერილი მენეჯერი"))
    db.flush()
    return w


def _new_item(db, M, D, algo, w, rnd, i, kind, flags, cc, run, clock, today, real_now):
    if "no_mgr" in flags:
        team = w.teams[i % 3]
        creator, extra, managers = w.departed[i % 2], [], []
    else:
        team = w.teams[i % len(w.teams)]
        creator = rnd.choice(team.surveyors)
        extra, managers = [], [team.manager]
        if "two_sv" in flags:
            extra = [rnd.choice([s for s in team.surveyors if s.id != creator.id])]
        elif cc:                                   # მეორე ამზომველი სხვა გუნდიდან → მისი მენეჯერი CC-ში
            other = w.teams[(i + 1) % len(w.teams)]
            extra, managers = [rnd.choice(other.surveyors)], [team.manager, other.manager]
    cad = (f"999.{team.zone}.{rnd.randint(10, 40):02d}.{rnd.randint(10, 60):02d}."
           f"{rnd.randint(1, 120):03d}.{i % 1000:03d}")
    base = real_now - dt.timedelta(days=rnd.randint(14, 130), hours=rnd.randint(0, 9))
    clock.t = base
    op = w.operators[i % len(w.operators)]
    item = M.QcItem(protocol_number=str(PROTO_ITEMS + i), cadcode=cad, kind=kind,
                    block_key=algo.block_key(cad), zone=team.zone, sector=algo.sector_of(cad),
                    drawing_date=base - dt.timedelta(days=rnd.randint(2, 10)), field_status=NORMAL_STATUS,
                    protocol_creator_name=creator.full_name, protocol_creator_id=creator.id,
                    operator_id=op.id, assigned_at=base,
                    field_manager_id=managers[0].id if managers else None,
                    distribution_run_id=run.id if kind == D.SYSTEMATIC else None, state=D.PENDING,
                    created_at=base, updated_at=base)
    if kind == D.SPORADIC:
        item.sporadic_meta = {"survey_day": (base.date() - dt.timedelta(days=1)).isoformat(),
                              "call_status": "ადგილზე დათვალიერება დასრულებულია",
                              "tr_name": rnd.choice(TR_NAMES), "scheduler": "დამგეგმავი 01 (დემო)",
                              "regnumber": f"D-{i:05d}", "demo": True}
    item.people = ([M.ItemPerson(kind=D.P_SURVEYOR, user_id=s.id, position=p, is_primary=p == 0)
                    for p, s in enumerate([creator] + extra)]
                   + [M.ItemPerson(kind=D.P_MANAGER, user_id=m.id, position=p, is_primary=p == 0)
                      for p, m in enumerate(managers)])
    db.add(item)
    db.flush()
    qcm = w.qcms[1] if kind == D.SPORADIC else w.qcms[0]
    db.add(M.QcEvent(item_id=item.id, at=base, actor_id=qcm.id, actor_role=D.QC_MANAGER,
                     action="assigned", to_state=D.PENDING,
                     data={"run": run.id if kind == D.SYSTEMATIC else None, "operator": op.full_name,
                           "demo": True}))
    return item


class Runner:
    """ერთი ოქმის სცენარი: მოქმედებები სწორი როლით, დრო — წინ."""

    def __init__(self, db, item, world, rnd, clock, codes, D, workflow, notify, M, stats):
        self.db, self.item, self.world, self.rnd, self.clock = db, item, world, rnd, clock
        self.all_codes, self.D, self.wf, self.notify, self.M, self.stats = codes, D, workflow, notify, M, stats

    def _actor(self, who):
        D, it, w = self.D, self.item, self.world
        if who == "op":
            return self.db.get(self.M.User, it.operator_id), D.QC_OPERATOR
        if who == "qcm":
            return (w.qcms[1] if it.kind == D.SPORADIC else w.qcms[0]), D.QC_MANAGER
        if who == "fm":
            return self.db.get(self.M.User, it.field_manager_id), D.FIELD_MANAGER
        svs = it.surveyors
        return svs[1 if who == "sv2" else 0].user, D.SURVEYOR

    def do(self, who, action, **form):
        self.clock.t += dt.timedelta(hours=self.rnd.randint(2, 30), minutes=self.rnd.randint(0, 59))
        user, role = self._actor(who)
        self.last = self.wf.apply(self.db, self.item, user, role, action, form)
        return self.last

    def text(self, verdict):
        return self.rnd.choice(QC_TEXT[verdict])

    def codes(self):
        return ",".join(self.rnd.sample(self.all_codes, self.rnd.choice((1, 1, 2))))

    def send(self, verdict):
        form = {"verdict": verdict}
        if verdict != "positive":
            form["qc_comment"] = self.text(verdict)
        if verdict in ("negative", "recommendation"):
            form.update(codes=self.codes(), codes_source="manual")
        return self.do("op", "send", **form)

    def field(self, who, response):
        return self.do(who, "field_respond", response=response, comment=FIELD_TEXT[response])

    def email(self, kind):
        sender, _ = self._actor("qcm" if kind.startswith("qcm") else "op")
        msg = self.notify.queue(self.db, self.item, self.last, sender, kind)
        if msg is not None:
            msg.created_at = self.clock.t
            self.stats["emails"] += 1

    def other_operator(self):
        return next(o for o in self.world.operators if o.id != self.item.operator_id)


def _extras(db, M, D, w, now, today):
    """ნარჩენი ეკრანები: სპორადულის იმპორტი, განაწილების ნაშთი, შენახული წესი, აუდიტი.
    ImportRun არ იქმნება — ის ძველი ცხრილის იმპორტის ანგარიშია, დემოში ასეთი არ არის."""
    counts = {k: 0 for k in ("rows", "with_day", "day_ok", "call_status", "open_status", "tr_name",
                             "already", "convert", "missing", "not_field", "unsorted", "ready",
                             "assigned", "overflow")}
    db.add(M.SporadicImport(created_by_id=w.qcms[1].id, at=now - dt.timedelta(days=3),
                            filename=SPORADIC_NAME, params={"demo": True},
                            summary={"counts": counts, "operators": [], "days": []}, item_count=0))
    for k in range(2):
        cad = f"999.38.{20 + k}.30.050.{k + 1:03d}"
        rec = {"cadcode": cad, "first_paper_id": str(PROTO_SOURCE + 900 + k),
               "first_oqmi": w.teams[1].surveyors[k].full_name, "first_moxaz": "",
               "first_status": NORMAL_STATUS, "disp_dt": (today - dt.timedelta(days=20)).isoformat(),
               "protocol_count": 1}
        db.add(M.DistributionBacklog(protocol_number=rec["first_paper_id"], cadcode=cad,
                                     block_key=cad.rsplit(".", 1)[0], record=rec))
    db.add(M.DistributionPreset(name="დემო წესი — ზონა 36 100%",
                                params={"default_pct": 70, "rules": [{"type": "zone", "key": "36",
                                                                      "pct": 100}]},
                                created_by_id=w.qcms[0].id))
    db.add(M.AuditLog(actor_id=w.admin.id, action="demo_build", entity="database",
                      detail={"generator": GENERATOR}))


def _ensure_emails(db, M):
    """ყველა მომხმარებელს — example.com (Pre-QC-ის დემო გუნდი უკვე ჩვენი შექმნილია)."""
    from sqlalchemy import select
    for u in db.scalars(select(M.User).where(M.User.email.is_(None))):
        u.email = f"demo.extra{u.id:04d}@example.com"


def _verify(db, M, D, name_key):
    """აწყობის შემდეგ — ბრიფის მოთხოვნები; დარღვევა → შეცდომა (ბაზა დემოდ რჩება)."""
    from sqlalchemy import func, select

    from app.services.seed import DEVELOPER_ADMINS, QC_MANAGERS
    states = dict(db.execute(select(M.QcItem.state, func.count()).group_by(M.QcItem.state)).all())
    verdicts = {v for (v,) in db.execute(select(M.QcItem.verdict).distinct()) if v}
    decisions = {v for (v,) in db.execute(select(M.QcItem.qcm_decision).distinct()) if v}
    roles = {r for (r,) in db.execute(select(M.UserRole.role).distinct())}
    emails = [e for (e,) in db.execute(select(M.User.email))]
    real = {name_key(n) for n in DEVELOPER_ADMINS} | {name_key(n) for n, _ in QC_MANAGERS}
    problems = [f"მდგომარეობა {s}: {states.get(s, 0)} < 3" for s in D.STATES if states.get(s, 0) < 3]
    problems += [f"ვერდიქტი აკლია: {v}" for v in D.VERDICTS if v not in verdicts]
    problems += [f"QC მენეჯერის გადაწყვეტილება აკლია: {v}"
                 for v in (D.QCM_STAND, D.QCM_FIELD_RIGHT, D.QCM_BOTH_RIGHT) if v not in decisions]
    problems += [f"როლი აკლია: {r}" for r in D.ROLES if r not in roles]
    if any(not (e or "").endswith("@example.com") for e in emails):
        problems.append("ელფოსტა example.com-ის გარეთ")
    if db.scalar(select(func.count()).select_from(M.User).where(M.User.name_key.in_(real))):
        problems.append("რეალური სახელი seed.py-დან")
    if problems:
        raise RuntimeError("დემო ბაზა ბრიფს არ აკმაყოფილებს: " + "; ".join(problems))
    count = lambda model: db.scalar(select(func.count()).select_from(model))  # noqa: E731
    return {"states": {s: states.get(s, 0) for s in D.STATES}, "users": len(emails),
            "kinds": dict(db.execute(select(M.QcItem.kind, func.count()).group_by(M.QcItem.kind)).all()),
            "events": count(M.QcEvent), "requests": count(M.VerdictRequest),
            "reviews": count(M.QcReview)}


# ══════════════════════════════════════════════════════════════════════
#  განაწილების წყარო და სპორადულის ფაილი (მხოლოდ source.py / sporadic.py-ის მოთხოვნებით)
# ══════════════════════════════════════════════════════════════════════
def _source_names(db_file):
    con = sqlite3.connect(db_file)
    try:
        q = ("SELECT u.full_name, u.active, t.name FROM users u JOIN team_members m ON m.user_id = u.id "
             "JOIN teams t ON t.id = m.team_id JOIN user_roles r ON r.user_id = u.id "
             "WHERE t.kind = 'field' AND r.role = 'surveyor' ORDER BY u.id")
        rows = con.execute(q).fetchall()
    finally:
        con.close()
    active = [n for n, a, _ in rows if a]
    departed = [n for n, a, _ in rows if not a]
    return {"active": active, "departed": departed}


def build_source(path: Path, names, rnd, today):
    con = sqlite3.connect(path)
    try:
        con.executescript("""
            CREATE TABLE import_meta (id INTEGER PRIMARY KEY, gdb_name TEXT, imported_at TEXT,
                                      feature_count INTEGER);
            CREATE TABLE parcels (cadcode TEXT, fld_paper_id REAL, mox_create_date TEXT,
                                  oqmi_creator TEXT, moxaz_creator TEXT, fld_status_name TEXT);
            CREATE INDEX ix_parcels_cad ON parcels(cadcode);
            CREATE INDEX ix_parcels_date ON parcels(mox_create_date);
            CREATE INDEX ix_parcels_paper ON parcels(fld_paper_id);
        """)
        rows, pid = [], PROTO_SOURCE
        open_statuses = ["შედგენილია -საველე განცხადება მიღებულია", "აღწერის პროცესი-საველე განცხადება"]
        zones = ["36", "38", "51", "43"]
        for b in range(40):                           # ბლოკები — ბოლო 10 დღე
            zone = zones[b % 4]
            block = f"999.{zone}.{11 + b % 7:02d}.{20 + b:02d}.{100 + b:03d}"
            day = today - dt.timedelta(days=1 + b % 10)
            for k in range(rnd.randint(2, 5)):
                pid += 1
                oqmi = rnd.choice(names["active"])
                moxaz = rnd.choice(names["active"]) if rnd.random() < 0.3 else oqmi
                if b % 9 == 4:
                    oqmi = moxaz = rnd.choice(names["departed"])            # დაუჯგუფებელი
                elif b % 13 == 6:
                    oqmi = moxaz = "რეგისტრატორი (დემო)"                    # Field Group-ში არ არის
                status = rnd.choice(open_statuses) if rnd.random() < 0.08 else NORMAL_STATUS
                ts = f"{day.isoformat()}T{rnd.randint(9, 18):02d}:{rnd.randint(0, 59):02d}:00"
                rows.append((f"{block}.{k + 1:03d}", float(pid), ts, oqmi, moxaz, status))
        old = today - dt.timedelta(days=60)              # კოდი, რომლის პირველი ოქმი ძველია — არ შედის
        rows.append(("999.36.11.20.100.001", float(pid + 1), f"{old.isoformat()}T10:00:00",
                     names["active"][0], names["active"][0], NORMAL_STATUS))
        sp = PROTO_SPORADIC                              # სპორადული: OQMI = „სისტემური სერვისი"
        for k in range(30):
            sp += 1
            day = today - dt.timedelta(days=1 + k % 5)
            rows.append((f"999.51.{30 + k % 5:02d}.40.{200 + k:03d}.001", float(sp),
                         f"{day.isoformat()}T12:00:00", "სისტემური სერვისი",
                         rnd.choice(names["active"]), NORMAL_STATUS))
        con.executemany("INSERT INTO parcels VALUES (?, ?, ?, ?, ?, ?)", rows)
        con.execute("INSERT INTO import_meta (gdb_name, imported_at, feature_count) VALUES (?, ?, ?)",
                    ("DEMO_REGFIELDALL (გამოგონილი)", dt.datetime.now().isoformat(timespec="seconds"),
                     len(rows)))
        con.commit()
    finally:
        con.close()
    return len(rows)


def build_sporadic_file(path: Path, names, rnd, today):
    """IT-ის ყოველდღიური სიის ფორმატი (sporadic.NEEDED) — პირადი სვეტების გარეშე."""
    import openpyxl

    from app.services.sporadic import COMPLETED, NEEDED
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "demo"
    ws.append(list(NEEDED))
    n = 0
    for k in range(34):                               # 30 წყაროში არის, 4 — არა („ვერ მოიძებნა")
        pid = PROTO_SPORADIC + 1 + k
        day = today - dt.timedelta(days=1 + k % 5)
        call = COMPLETED if k % 7 else "დათვალიერება გადაიდო (დემო)"
        ws.append([pid, f"999.51.{30 + k % 5:02d}.40.{200 + k:03d}.001", day.isoformat(),
                   f"{10 + k % 8}:00", call, NORMAL_STATUS, rnd.choice(TR_NAMES),
                   f"დამგეგმავი {1 + k % 3:02d} (დემო)", f"D-{k:05d}", day.isoformat()])
        n += 1
    wb.save(path)
    return n


# ══════════════════════════════════════════════════════════════════════
def main(argv=None):
    ap = argparse.ArgumentParser(description="სადემონსტრაციო ბაზა — მხოლოდ გამოგონილი მონაცემით")
    ap.add_argument("--out", help="საქაღალდე (ნაგულისხმევი: <მთავარის მშობელი>\\qc-demo-data)")
    ap.add_argument("--items", type=int, default=DEFAULT_ITEMS, help=f"ოქმების რაოდენობა (≈{DEFAULT_ITEMS})")
    ap.add_argument("--force", action="store_true", help="არსებული დემო ბაზის გადაწერა")
    ap.add_argument("--seed", type=int, default=SEED, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    t0 = time.time()
    try:
        if args.items < min_items():
            raise Refused(f"--items {args.items} ძალიან ცოტაა: ყველა სცენარს ({len(SCENARIOS)}, "
                          f"თითოში 3 ოქმი) სჭირდება მინიმუმ {min_items()}.")
        out = check_target(Path(args.out) if args.out else default_out())
        prepare_target(out, args.force)
        isolate_env(out)
        report = build(out, args.items, args.seed)
    except Refused as e:
        print(f"✗ უარი: {e}", file=sys.stderr)
        return 2
    print(f"✓ დემო ბაზა მზადაა — {time.time() - t0:.1f} წმ")
    print(f"  საქაღალდე: {out}")
    print(f"  ოქმები: {report['items']} {report['kinds']} · მომხმარებლები: {report['users']} · "
          f"ისტორია: {report['events']} · მეილები: {report['emails']} · Pre-QC: {report['preqc']}")
    print("  მდგომარეობები:", json.dumps(report["states"], ensure_ascii=False))
    print(f"  განაწილების წყარო: {report['source']} ჩანაწერი · სპორადულის ფაილი: {report['sporadic_file']} ხაზი")
    return 0


if __name__ == "__main__":
    sys.exit(main())
