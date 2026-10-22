# -*- coding: utf-8 -*-
"""ტესტები ცალკე, დროებით ბაზაზე მუშაობს — data/platform.db-ს არ ეხება."""
import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="qcp-test-")
os.environ["QCP_DATA_DIR"] = _TMP
os.environ["QCP_DATABASE_URL"] = f"sqlite:///{Path(_TMP, 'test.db').as_posix()}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app import domain as D  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models import ItemPerson, QcItem, Setting, User, UserRole  # noqa: E402
from app.security import Ctx  # noqa: E402
from app.services.people import name_key  # noqa: E402


@pytest.fixture()
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    s = SessionLocal()
    s.add(Setting(key="allowed_responses", value=D.DEFAULT_ALLOWED_RESPONSES))
    s.commit()
    yield s
    s.close()


def make_user(db, name, *roles, email=None):
    u = User(full_name=name, name_key=name_key(name), email=email)
    for r in roles:
        u.roles.append(UserRole(role=r))
    db.add(u)
    db.flush()
    return u


@pytest.fixture()
def people(db):
    p = {
        "op": make_user(db, "ოპერატორი ერთი", D.QC_OPERATOR),
        "op2": make_user(db, "ოპერატორი ორი", D.QC_OPERATOR),
        "qcm": make_user(db, "QC მენეჯერი", D.QC_MANAGER),
        "mgr": make_user(db, "საველე მენეჯერი", D.FIELD_MANAGER, email="mgr@example.com"),
        "mgr2": make_user(db, "სხვა მენეჯერი", D.FIELD_MANAGER, email="mgr2@example.com"),
        "sv": make_user(db, "ამზომველი F", D.SURVEYOR),
        "sv2": make_user(db, "ამზომველი G", D.SURVEYOR),
        "other": make_user(db, "სხვა ამზომველი", D.SURVEYOR),
        "coord": make_user(db, "კოორდინატორი", D.COORDINATOR),
        "head": make_user(db, "სამსახურის უფროსი", D.HEAD_OF_SERVICE),
        "admin": make_user(db, "ადმინი", D.ADMIN),
    }
    db.commit()
    return p


def ctx(user, role):
    return Ctx(user, role)


def make_item(db, people, protocol="6100001", cad="202.51.12.40.001.001", managers=("mgr",),
              surveyors=("sv", "sv2")):
    i = QcItem(protocol_number=protocol, cadcode=cad, kind=D.SYSTEMATIC,
               operator_id=people["op"].id, field_manager_id=people[managers[0]].id,
               protocol_creator_id=people[surveyors[0]].id, state=D.PENDING)
    i.people = [ItemPerson(kind=D.P_SURVEYOR, user_id=people[s].id, position=n, is_primary=n == 0)
                for n, s in enumerate(surveyors)] + \
               [ItemPerson(kind=D.P_MANAGER, user_id=people[m].id, position=n, is_primary=n == 0)
                for n, m in enumerate(managers)]
    db.add(i)
    db.commit()
    return i


@pytest.fixture()
def item(db, people):
    return make_item(db, people)
