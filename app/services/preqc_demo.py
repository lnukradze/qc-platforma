# -*- coding: utf-8 -*-
"""
Pre-QC — ფიქსირებული სადემონსტრაციო მონაცემი და შემოწმების გრაფიკი.

⚠️ **ეს მონაცემი გამოგონილია.** ოქმები, ამზომველები და ხარვეზები სადემონსტრაციო
   გუნდს ეკუთვნის (სახელებში „(დემო)") — რეალურ ადამიანს ან ოქმს არ ეხება.
   IT-სგან რესურსების დაზუსტების შემდეგ ეს ნაწილი რეალური Pre-QC შედეგებით
   (Pre-QC Validator-ის ფორმატით) ჩანაცვლდება.

გრაფიკი (მომხმარებლის წესი, 2026-10-19): შემოწმება ავტომატურია და მივლინების
მესამე დღიდან იწყება — მე-3 დღეს მოწმდება პირველი დღის ოქმები, მე-4 დღეს
მეორისა, და ა.შ. (`preqc_lag_days` = 2).
"""
import datetime as dt
import random

from sqlalchemy import delete, select

from .. import domain as D
from ..models import Mission, PreqcCheck, PreqcFinding, Team, TeamMember, User, UserRole
from .people import name_key

# შიდა შემოწმება → (ოფიციალური კოდი, სიმძიმე, შეტყობინება)
CHECKS = [
    ("NOTE_001", "DOC-02", "fail", "სამსახურეობრივი შენიშვნა (F2) ცარიელია"),
    ("SLR_001", "SLR-01", "fail", "A1-ში SLR განაცხადთან დაკავშირება ვერ მოიძებნა"),
    ("SLR_003", "SLR-02", "warn", "SLR განაცხადი პლატფორმაზე დასრულებულ სტატუსში არ არის"),
    ("DOC_002", "EVD-02", "fail", "ატვირთულია მხოლოდ 3 ნაკვეთის ფოტო (საჭიროა მინ. 5)"),
    ("PHOTO_DATE", "EVD-03", "warn", "2 ფოტოს თარიღი აზომვის დღეს არ ემთხვევა"),
    ("DOC_001", "EVD-01", "unknown", "პირადობის დოკუმენტი D3-ში ვერ დადასტურდა — სავარაუდოდ ფოტოშია"),
    ("SIG_001", "DOC-04", "fail", "მიმთითებელი პირის ხელმოწერა აკლია"),
    ("REPORT_REGISTERED", "GEO-02", "fail", "რეგისტრირებულ ნაკვეთთან ზედდება (14.2 მ²) — F2-ში მიზეზი არ ჩანს"),
    ("REPORT_CTRL", "GEO-01", "warn", "„A და B კლასის გზები“ ფენასთან ზედდება განმარტების გარეშე"),
    ("GIS_TOPO", "GEO-03", "fail", "პოლიგონს თვითკვეთა აქვს"),
    ("GIS_AREA_MATCH", "GEO-05", "warn", "ოქმის ფართობი GIS-ის ფართობს 4.8%-ით აღემატება"),
    ("GIS_CATEGORY", "ATR-01", "fail", "კატეგორია „არასასოფლო“ — ორთოფოტოზე სასოფლო-სამეურნეო მიწაა"),
    ("ATR_POSSESSION", "ATR-03", "warn", "„ფაქტობრივად ფლობს“ მონიშნულია, ტექსტში ფლობის აღწერა ვერ ვიპოვე"),
    ("GIS_BLD_MATCH", "ATR-04", "warn", "ოქმში 1 შენობაა, GIS-ში — 2"),
    ("REPORT_FIELD", "PRC-01", "fail", "ნაკვეთი 97% ემთხვევა ადრე აზომილ ნაკვეთს (ოქმი 6140xxx)"),
    ("DOC_WRONG_FIELD", "DOC-05", "warn", "ინფორმაცია „სხვა შენიშვნები“ ველშია, სამსახურეობრივი შენიშვნა ცარიელია"),
]
WEIGHTS = [16, 6, 7, 9, 6, 5, 4, 10, 9, 5, 6, 4, 6, 4, 3, 3]
CRITICAL_CODES = {"SLR-01", "SLR-03", "ATR-01", "ATR-03", "ATR-04", "EVD-01", "EVD-04", "DOC-01",
                  "DOC-02", "DOC-04", "PRC-01", "PRC-02", "PRC-03", "GEO-02", "GEO-03", "GEO-05"}

DEMO_MANAGER = "საველე მენეჯერი (დემო)"
DEMO_SURVEYORS = ["ამზომველი ა (დემო)", "ამზომველი ბ (დემო)", "ამზომველი გ (დემო)",
                  "ამზომველი დ (დემო)"]


def mission_day(missions, day: dt.date):
    """თარიღი → (მისია, მისიის დღე 1..N) ან (None, None)."""
    for m in missions:
        if m.start <= day <= m.end:
            return m, (day - m.start).days + 1
    return None, None


def schedule_for(mission, lag=2, today=None):
    """მისიის დღეები: [(დღე, თარიღი, რომლის ოქმები მოწმდება, სტატუსი)]."""
    today = today or dt.date.today()
    out = []
    total = (mission.end - mission.start).days + 1
    for i in range(total + lag):
        day = mission.start + dt.timedelta(days=i)
        checks_day = i + 1 - lag
        target = mission.start + dt.timedelta(days=checks_day - 1) if checks_day >= 1 else None
        status = "done" if day < today else ("today" if day == today else "planned")
        out.append({"n": i + 1, "date": day, "checks_day": checks_day if checks_day >= 1 else None,
                    "target_date": target, "status": status, "after_end": i + 1 > total})
    return out


def _ensure_user(db, name, role, active=True):
    u = db.scalar(select(User).where(User.name_key == name_key(name)))
    if u is None:
        u = User(full_name=name, name_key=name_key(name), source="demo", is_demo=True, active=active)
        db.add(u)
        db.flush()
    if role not in u.role_set:
        u.roles.append(UserRole(role=role))
    return u


def build_demo(db, mission_n=14, seed=20261019):
    """სადემონსტრაციო გუნდი + Pre-QC შედეგები ერთი დასრულებული მივლინებისთვის."""
    rnd = random.Random(seed)
    db.execute(delete(PreqcFinding))
    db.execute(delete(PreqcCheck))
    mgr = _ensure_user(db, DEMO_MANAGER, D.FIELD_MANAGER)
    team = db.scalar(select(Team).where(Team.manager_id == mgr.id))
    if team is None:
        team = Team(name=DEMO_MANAGER, kind="field", manager_id=mgr.id)
        db.add(team)
        db.flush()
    surveyors = []
    for nm in DEMO_SURVEYORS:
        u = _ensure_user(db, nm, D.SURVEYOR)
        if not db.scalar(select(TeamMember).where(TeamMember.team_id == team.id,
                                                   TeamMember.user_id == u.id)):
            db.add(TeamMember(team_id=team.id, user_id=u.id, source="demo"))
        surveyors.append(u)

    mission = db.get(Mission, mission_n)
    days = (mission.end - mission.start).days + 1
    proto = 9_000_000
    n_checks = 0
    for d in range(days):
        pdate = mission.start + dt.timedelta(days=d)
        if pdate.weekday() == 6:                       # კვირა — სამუშაო დღე არ არის
            continue
        for s_i, surveyor in enumerate(surveyors):
            for _ in range(rnd.randint(2, 5)):
                proto += rnd.randint(3, 40)
                k = rnd.choices([0, 1, 2, 3, 4], weights=[38, 27, 18, 11, 6])[0]
                picks = []
                for _ in range(k):
                    c = rnd.choices(CHECKS, weights=WEIGHTS)[0]
                    if c not in picks:
                        picks.append(c)
                score = 100
                for code, off, sev, _msg in picks:
                    score -= {"fail": 14, "warn": 6, "unknown": 3}[sev]
                score = max(35, score - rnd.randint(0, 4))
                crit_fail = any(sev == "fail" and off in CRITICAL_CODES for _, off, sev, _ in picks)
                crit_unknown = any(sev == "unknown" and off in CRITICAL_CODES for _, off, sev, _ in picks)
                status = ("fail" if crit_fail else "review" if crit_unknown else
                          "pass" if score >= 90 else "warn" if score >= 70 else "fail")
                zone = rnd.choice(["36", "38", "51"])
                chk = PreqcCheck(
                    protocol_number=f"D-{proto}", cadcode=f"(დემო) {zone}.{rnd.randint(10, 40)}",
                    surveyor_id=surveyor.id, field_manager_id=mgr.id, zone=zone,
                    mission_n=mission.n, protocol_date=pdate,
                    checked_on=pdate + dt.timedelta(days=2), score=score, status=status,
                    is_demo=True)
                for code, off, sev, msg in picks:
                    chk.findings.append(PreqcFinding(
                        code=code, official_code=off, severity=sev,
                        title=OFFICIAL_TITLES.get(off, off), message=msg,
                        recommendation=OFFICIAL_ACTIONS.get(off)))
                db.add(chk)
                n_checks += 1
    db.flush()
    return {"checks": n_checks, "mission": mission.n, "team": team.name}


# ოფიციალური კოდის სათაური და მოქმედება ამზომველისთვის (Pre-QC Validator, qc_codes.py)
OFFICIAL_TITLES = {
    "SLR-01": "SLR განაცხადის მიბმა არ არის ან არასწორია",
    "SLR-02": "SLR განაცხადი დასრულებულ სტატუსში არ არის",
    "ATR-01": "მიწის კატეგორია/დანიშნულება არ შეესაბამება მტკიცებულებას",
    "ATR-03": "ფაქტობრივი ფლობის მონიშვნა მტკიცებულებით არ დასტურდება",
    "ATR-04": "შენობა-ნაგებობის აღრიცხვა ან ატრიბუტები არასწორია",
    "EVD-01": "სავალდებულო დოკუმენტის ფოტო აკლია ან შეუსაბამოა",
    "EVD-02": "ფოტომასალა არასრულყოფილია ან დაბალი ხარისხისაა",
    "EVD-03": "ფოტოსა და საველე მოქმედების თარიღები არ ემთხვევა",
    "DOC-02": "F2-ში სავალდებულო ინფორმაცია არასრულია",
    "DOC-04": "სავალდებულო ხელმოწერა აკლია ან არასათანადოდაა შესრულებული",
    "DOC-05": "ინფორმაცია არასწორ ველშია განთავსებული",
    "PRC-01": "განმეორებითი აზომვა სათანადო საფუძვლის გარეშე",
    "GEO-01": "საჯარო სივრცულ ფენასთან ზედდება განმარტების გარეშე",
    "GEO-02": "ზედდების მიზეზი ან სადავოობა დაუზუსტებელია",
    "GEO-03": "გეომეტრიის ტოპოლოგიური დარღვევა (GAP/თვითკვეთა)",
    "GEO-05": "ნახაზი არ ემთხვევა GIS-ის მონაცემებს",
}
OFFICIAL_ACTIONS = {
    "SLR-01": "გადაამოწმეთ შესაბამისი SLR განაცხადი და დააკორექტირეთ მიბმა/ნომერი A1 გრაფაში.",
    "SLR-02": "დაასრულეთ შესაბამისი SLR პროცესი და ხელახლა შეამოწმეთ ოქმი.",
    "ATR-01": "გადაამოწმეთ წყაროები და დააკორექტირეთ კატეგორიის/დანიშნულების ველი.",
    "ATR-03": "გადაამოწმეთ მტკიცებულებები და შესაბამისობაში მოიყვანეთ F2-ის მონიშვნა და ტექსტი.",
    "ATR-04": "გადაამოწმეთ ობიექტი, დააზუსტეთ აზომვას დაქვემდებარება და შეასწორეთ მონაცემები.",
    "EVD-01": "ატვირთეთ დაინტერესებული პირის ვალიდური, მკაფიო პირადობის დოკუმენტის ფოტო.",
    "EVD-02": "დაამატეთ მკაფიო ფოტოები განსხვავებული ხედებიდან.",
    "EVD-03": "ატვირთეთ შესაბამისი პერიოდის ფოტოები ან F2-ში განმარტეთ განსხვავება.",
    "DOC-02": "შეავსეთ შესაბამისი სავალდებულო ველი/მონიშვნა და აღწერეთ საჭირო გარემოება.",
    "DOC-04": "მოიპოვეთ შესაბამისი ხელმოწერა საბოლოო ვერსიაზე (TAG-ის ასახვის შემდეგ).",
    "DOC-05": "გადაიტანეთ ინფორმაცია ფორმით განსაზღვრულ შესაბამის ველში.",
    "PRC-01": "გადაამოწმეთ ხელახალი აზომვის საფუძველი და იმოქმედეთ დადგენილი წესით.",
    "GEO-01": "გადაამოწმეთ საზღვარი და F2-ში აღწერეთ ზედდების საფუძველი/სტატუსი.",
    "GEO-02": "გაასწორეთ გეომეტრია ან F2-ში მიუთითეთ ზედდების მიზეზი და სადავოობის სტატუსი.",
    "GEO-03": "გაასწორეთ პოლიგონის ტოპოლოგია და ხელახლა გაუშვით Pre-QC.",
    "GEO-05": "გადაამოწმეთ გეომეტრია და განაახლეთ TAG/ნახაზი.",
}
