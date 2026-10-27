# -*- coding: utf-8 -*-
"""ახალი ინტერფეისი („იზოხაზი“) — რეალურ მონაცემზე: პროცესის ნაბიჯები, დაფის ატრიბუტები,
მთავარის ბლოკები, სტატისტიკის განყოფილებები. მარშრუტებს და ბიზნესწესებს არ ცვლის — მხოლოდ კითხულობს."""
from fastapi.testclient import TestClient

from app import domain as D
from app.main import app
from app.workflow import apply
from conftest import make_item

ORIGIN = {"origin": "http://testserver"}


def login(c, user, role):
    r = c.post("/login/demo", data={"user_id": str(user.id), "role": role}, headers=ORIGIN,
               follow_redirects=False)
    assert r.status_code == 303


def act(db, item, user, role, action, **form):
    form.setdefault("version", item.version)
    apply(db, item, user, role, action, form)
    db.commit()


def page(people, who, role, url):
    c = TestClient(app)
    login(c, people[who], role)
    r = c.get(url)
    assert r.status_code == 200, (url, r.status_code, r.text[:300])
    return r.text


def test_stepper_skips_review_when_no_dispute(db, people, item):
    """„განხილვა“ დავის გარეშე — გამოტოვებული (და არა შესრულებული); მიმდინარე — „გადამოწმება“."""
    act(db, item, people["op"], D.QC_OPERATOR, "send", verdict=D.NEGATIVE, qc_comment="ფოტო აკლია")
    act(db, item, people["sv"], D.SURVEYOR, "field_respond", response=D.R_CORRECTED)
    assert item.state == D.AWAITING_QC
    html = page(people, "op", D.QC_OPERATOR, f"/items/{item.id}")
    assert 'class="stepper"' in html
    assert html.count("step-i skipped") == 1
    assert html.count("step-i done") == 2
    assert 'aria-current="step"' in html


def test_stepper_marks_review_current_on_dispute(db, people, item):
    act(db, item, people["op"], D.QC_OPERATOR, "send", verdict=D.NEGATIVE, qc_comment="ფოტო აკლია")
    act(db, item, people["sv"], D.SURVEYOR, "field_respond", response=D.R_DISAGREE, comment="x")
    act(db, item, people["mgr"], D.FIELD_MANAGER, "manager_approve")
    assert item.state == D.AWAITING_QCM
    html = page(people, "qcm", D.QC_MANAGER, f"/items/{item.id}")
    assert "step-i skipped" not in html
    assert html.count("step-i done") == 2


def test_stepper_positive_close_skips_field_steps(db, people, item):
    act(db, item, people["op"], D.QC_OPERATOR, "send", verdict=D.POSITIVE)
    assert item.state == D.CLOSED
    html = page(people, "op", D.QC_OPERATOR, f"/items/{item.id}")
    assert html.count("step-i skipped") == 3          # ველზე, განხილვა, გადამოწმება
    assert html.count("step-i done") == 2             # შეფასება, დახურული


def assert_no_removed_ui(html):
    for marker in ('data-board=', 'id="bulk-form"', 'id="bulkbar"', 'check-all',
                   'type="checkbox"', 'cmdk-open', 'view-switch', '/qc/bulk-send'):
        assert marker not in html, marker



def test_lists_keep_table_and_peek_without_board(db, people, item):
    html = page(people, "op", D.QC_OPERATOR, "/qc")
    assert_no_removed_ui(html)
    assert '<table class="data cards">' in html and item.protocol_number in html
    assert f'data-peek="/items/{item.id}"' in html
    c = TestClient(app)
    login(c, people["op"], D.QC_OPERATOR)
    r = c.get("/qc?page=1", headers={"HX-Request": "true"})
    assert r.status_code == 200
    assert_no_removed_ui(r.text)
    assert "<html" not in r.text and item.protocol_number in r.text
    assert f'data-peek="/items/{item.id}"' in r.text


def test_field_list_keeps_table_without_board(db, people, item):
    act(db, item, people["op"], D.QC_OPERATOR, "send", verdict=D.NEGATIVE, qc_comment="ფოტო აკლია")
    html = page(people, "mgr", D.FIELD_MANAGER, "/field")
    assert_no_removed_ui(html)
    assert item.protocol_number in html and '<table class="data cards">' in html
    assert f'data-peek="/items/{item.id}"' in html
    assert '<th>სტატუსი</th>' in html and '<th>ველის სტატუსი</th>' in html


def test_home_bento_and_attention(db, people, item):
    html = page(people, "qcm", D.QC_MANAGER, "/")
    assert 'class="bento"' in html and 'class="attention"' in html and 'href="/qc/disagreements"' in html
    html = page(people, "op", D.QC_OPERATOR, "/")
    assert 'href="/qc/next"' in html and 'class="flow-bar"' in html
    html = page(people, "head", D.HEAD_OF_SERVICE, "/")
    assert 'class="brief"' in html


def test_stats_page_has_new_sections(db, people, item):
    html = page(people, "qcm", D.QC_MANAGER, "/stats")
    for el in ('id="ch-trend"', 'id="ch-managers"', 'id="ch-codes"', 'id="ch-map"', 'id="zone-rank"',
               'id="insights"', 'id="trend-mode"', 'id="t-qcerr"'):
        assert el in html, el
    html = page(people, "sv", D.SURVEYOR, "/stats")
    assert 'id="t-qcerr"' not in html                 # შეზღუდული ნაწილი ამზომველს არ უჩანს


def test_base_shell(db, people, item):
    html = page(people, "op", D.QC_OPERATOR, "/qc")
    assert 'id="rail"' in html and 'id="theme-toggle"' in html
    assert_no_removed_ui(html)
    assert 'Ctrl K' not in html and 'ოქმის# ან გვერდი' not in html
    assert "--eyebrow:" in html                       # კონტექსტური წარწერა სათაურზე
    assert 'action="/role"' in html and 'action="/logout"' in html
