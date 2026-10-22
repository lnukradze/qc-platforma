# -*- coding: utf-8 -*-
"""ძველი ცხრილის მწკრივი → ახალი მდგომარეობა (მომხმარებლის წესები, 2026-10-19 / 20)."""
from app import domain as D
from app.services.codes import classify, parse_codes
from app.services.legacy_import import derive_state, parse_bool, parse_dt, row_to_rec
from app.services.people import clean_name, name_key, split_names

HEADER = ["ოქმის N", "CADCODE", "QC სპეციალისტი", "დამატების თარიღი", "შემოწმების სტატუსი",
          "ამგეგმავი", "ამგეგმავი (2)", "ხარვეზის კოდი", "QC კომენტარი", "საველე მენეჯერის სტატუსი",
          "საველე მენეჯერის კომენტარი", "უკუკავშირის თარიღი", "გასწორდა", "ხარვეზია",
          "უკან დაბრუნებული ხარვეზის კომენტარი", "კონტროლი sync", "სინქრონის დრო", "საველე sync",
          "სინქრონის დრო", "მენეჯერი", "ნახაზის შეტანის თარიღი", "TYPE", "anot"]


def test_duplicate_sync_time_headers_map_to_q_and_s():
    row = ["1", "202.1", "ოპ", "2026-06-01T10:00:00", "უარყოფითი", "", "", "", "", "", "", "",
           "false", "false", "", "false", "2026-07-07T13:00:00", "false", "2026-07-09T17:02:00", "მ",
           "", "", ""]
    r = row_to_rec(HEADER, row)
    assert r["qtime"].startswith("2026-07-07") and r["stime"].startswith("2026-07-09")


def test_state_mapping_rules():
    assert derive_state({"status": "დადებითი"})[0] == D.CLOSED
    assert derive_state({"status": "უარყოფითი", "fixed": "true"})[:2] == (D.CLOSED, D.CR_CORRECTED)
    assert derive_state({"status": "რეკომენდაცია", "fixed": "true"})[1] == D.CR_ACKNOWLEDGED
    assert derive_state({"status": "უარყოფითი", "jstatus": "არ ვეთანხმები"})[0] == D.AWAITING_QCM
    assert derive_state({"status": "უარყოფითი", "jstatus": "შესწორდა"})[0] == D.AWAITING_QC
    assert derive_state({"status": "უარყოფითი", "returned": "არ გასწორდა"})[0] == D.RETURNED_TO_MANAGER
    assert derive_state({"status": "უარყოფითი"})[0] == D.AWAITING_FIELD
    assert derive_state({"status": "პროცესშია"})[0] == D.PENDING
    assert derive_state({"status": ""})[0] == D.PENDING


def test_who_has_the_ball_by_sync_times():
    """Q > S და O-ში შენიშვნა → კონტროლმა უკვე უპასუხა → საველე მენეჯერთან (პასუხი №15)."""
    answered = {"qtime": "2026-10-09T17:26:00", "stime": "2026-08-11T11:36:00", "returned": "ისევ GAP"}
    waiting = {"qtime": "2026-08-20T15:01:00", "stime": "2026-10-09T22:49:00", "returned": "ძველი შენიშვნა"}
    no_note = {"qtime": "2026-10-09T17:26:00", "stime": "2026-08-11T11:36:00"}
    dis = {"status": "უარყოფითი", "jstatus": "არ ვეთანხმები"}
    fix = {"status": "უარყოფითი", "jstatus": "შესწორდა"}
    assert derive_state({**dis, **answered})[0] == D.RETURNED_TO_MANAGER
    assert derive_state({**dis, **waiting})[0] == D.AWAITING_QCM
    assert derive_state({**dis, **no_note})[0] == D.AWAITING_QCM          # შენიშვნა არ არის — კონტროლთან
    assert derive_state({**fix, **answered})[0] == D.RETURNED_TO_MANAGER
    assert derive_state({**fix, **waiting})[0] == D.AWAITING_QC
    assert derive_state({**fix, **no_note})[0] == D.AWAITING_QC


def test_dates_and_bools():
    assert parse_dt("2026-06-22 07:44").hour == 7
    assert parse_dt("2026-08-20T17:36:01").minute == 36
    assert parse_dt("წაიშალა") is None
    assert parse_bool("true") and not parse_bool("false")


def test_names_are_normalised():
    assert clean_name("ონისე  თოლორდავა\t01001000000") == "ონისე თოლორდავა"
    assert name_key("ონისე  თოლორდავა") == name_key("ონისე თოლორდავა")
    assert split_names("გიორგი სამუშია\nონისე თოლორდავა") == ["გიორგი სამუშია", "ონისე თოლორდავა"]
    assert split_names("-") == []


def test_codes_and_legacy_type_marks():
    assert parse_codes("GEO-01, geo-01, SLR-03") == ["GEO-01", "SLR-03"]
    assert "DOC-04" in classify("მიმთითებელი პირის ხელმოწერა აკლია")
    assert classify("") == []
    assert D.LEGACY_TYPE_TO_MARK["false defect"] == D.MARK_WRONG
    assert D.LEGACY_TYPE_TO_MARK["missed defect"] == D.MARK_MISSED
