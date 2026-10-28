# -*- coding: utf-8 -*-
"""
T-031 — სტატისტიკის KPI „ველზე ღია“ (/stats და /stats/tabler-preview): დავის სტატუსის წარწერა მხოლოდ D.labels(role)-იდან.

JS ტექსტს თავად არ წერს — კითხულობს #kpis[data-qcm-state]-ს, რომელსაც შაბლონი D.labels()-ით ავსებს.
ოპერატორების ცხრილი ველს არ აქვს — მისი სათაური („QC ოპერატორები“) ველის HTML-შიც არ არის.
"""
import html
import re
from pathlib import Path

import pytest

from app import domain as D
from test_confidentiality import FIELD, client, no_smtp, w  # noqa: F401

JS = Path(__file__).resolve().parents[1] / "app" / "static" / "js"
PAGES = ["/stats", "/stats/tabler-preview"]
# ფუძეები („QC მენეჯერ…“) — ბრუნვაშიც იჭერს: „QC მენეჯერთან“, „კონტროლის მენეჯერს“…
QC_ROLE_WORDS = [D.ROLE_SHORT[r][:-1] for r in (D.QC_MANAGER, D.QC_OPERATOR)] + \
                [D.ROLE_LABELS[r][:-1] for r in (D.QC_MANAGER, D.QC_OPERATOR)]
OPERATORS_TITLE = "QC ოპერატორები"


def page(c, path):
    r = c.get(path)
    assert r.status_code == 200, path
    m = re.search(r'id="kpis" data-qcm-state="([^"]*)"', r.text)
    assert m, f"{path}: #kpis[data-qcm-state] არ არის"
    return html.unescape(m.group(1)), r.text


@pytest.mark.parametrize("path", PAGES)
@pytest.mark.parametrize("who,role", FIELD)
def test_stats_kpi_field_neutral(db, w, who, role, path):
    label, text = page(client(w["p"][who], role), path)
    assert label == D.labels(role)["STATE_LABELS"][D.AWAITING_QCM]
    assert D.QC_ANON_LABEL[:-1] in label                       # „ხარისხის კონტროლ…“
    assert not [s for s in QC_ROLE_WORDS if s in label]
    assert OPERATORS_TITLE not in text


@pytest.mark.parametrize("path", PAGES)
@pytest.mark.parametrize("who,role", [("qcm", D.QC_MANAGER), ("admin", D.ADMIN), ("coord", D.COORDINATOR)])
def test_stats_kpi_qc_side_unchanged(db, w, who, role, path):
    label, text = page(client(w["p"][who], role), path)
    assert label == D.STATE_LABELS[D.AWAITING_QCM]
    assert QC_ROLE_WORDS[0] in label                           # საკონტროლო: QC მხარე „QC მენეჯერ…“-ს ხედავს
    assert OPERATORS_TITLE in text


@pytest.mark.parametrize("name", ["stats.js", "stats-tabler-preview.js"])
def test_stats_js_has_no_hardcoded_qc_role(name):
    src = (JS / name).read_text(encoding="utf-8")
    assert "dataset.qcmState" in src
    assert "QC მენეჯერთან" not in src
