# -*- coding: utf-8 -*-
"""
T-031 — სტატისტიკის KPI „ველზე ღია“: დავის სტატუსის წარწერა მხოლოდ D.labels(role)-იდან.

stats.js ტექსტს თავად არ წერს — კითხულობს #kpis[data-qcm-state]-ს, რომელსაც შაბლონი D.labels()-ით ავსებს.
"""
import html
import re
from pathlib import Path

import pytest

from app import domain as D
from test_confidentiality import FIELD, client, no_smtp, w  # noqa: F401

STATS_JS = Path(__file__).resolve().parents[1] / "app" / "static" / "js" / "stats.js"
# ფუძეები („QC მენეჯერ…“) — ბრუნვაშიც იჭერს: „QC მენეჯერთან“, „კონტროლის მენეჯერს“…
QC_ROLE_WORDS = [D.ROLE_SHORT[r][:-1] for r in (D.QC_MANAGER, D.QC_OPERATOR)] + \
                [D.ROLE_LABELS[r][:-1] for r in (D.QC_MANAGER, D.QC_OPERATOR)]


def kpi_state(c):
    r = c.get("/stats")
    assert r.status_code == 200
    m = re.search(r'<div id="kpis" data-qcm-state="([^"]*)"', r.text)
    assert m, "#kpis[data-qcm-state] არ არის"
    return html.unescape(m.group(1))


@pytest.mark.parametrize("who,role", FIELD)
def test_stats_kpi_field_neutral(db, w, who, role):
    label = kpi_state(client(w["p"][who], role))
    assert label == D.labels(role)["STATE_LABELS"][D.AWAITING_QCM]
    assert D.QC_ANON_LABEL[:-1] in label                       # „ხარისხის კონტროლ…“
    assert not [s for s in QC_ROLE_WORDS if s in label]


@pytest.mark.parametrize("who,role", [("qcm", D.QC_MANAGER), ("admin", D.ADMIN), ("coord", D.COORDINATOR)])
def test_stats_kpi_qc_side_unchanged(db, w, who, role):
    label = kpi_state(client(w["p"][who], role))
    assert label == D.STATE_LABELS[D.AWAITING_QCM]
    assert QC_ROLE_WORDS[0] in label                           # საკონტროლო: QC მხარე „QC მენეჯერ…“-ს ხედავს


def test_stats_js_has_no_hardcoded_qc_role():
    src = STATS_JS.read_text(encoding="utf-8")
    assert "dataset.qcmState" in src
    assert "QC მენეჯერთან" not in src
