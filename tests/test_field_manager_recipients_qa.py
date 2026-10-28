"""T-028 recipient regressions migrated to the approved T-030 contract.

Source: 283d648, test_email_to_never_contains_qc_role_user (four cases).
Only active FIELD_MANAGER recipients are valid; an additional QC role is allowed.
All users and addresses come from fictional, isolated test fixtures.
"""
import pytest

from app import domain as D
from app.models import EmailMessage, QcEvent, User, UserRole
from app.services import notify
from test_confidentiality import no_smtp, w  # noqa: F401


@pytest.mark.parametrize("primary_key", ["op", "qcm", "admin", "multi"])
def test_email_to_always_has_active_field_manager_role(db, w, primary_key):
    """The original four invalid-primary regressions, without mocking selection."""
    primary = w["p"][primary_key]
    primary.email = f"qa-{primary_key}@example.com"
    w["a"].field_manager_id = primary.id
    db.commit()
    msg = notify.queue(db, w["a"], db.get(QcEvent, w["events"]["send"].id),
                       w["p"]["op"], "sent", base_url="http://testserver")
    # This fixture has valid manager fallbacks: silently dropping the email is wrong.
    assert msg is not None
    db.flush()
    to = db.get(User, msg.to_user_id)
    assert to is not None and to.active and to.has_role(D.FIELD_MANAGER), primary_key
    assert msg.to_email == to.email
    assert msg.to_user_id != primary.id and msg.to_email != primary.email
    assert msg.to_user_id in {w["p"]["mgr"].id, w["p"]["mgr2"].id}
    assert all(db.query(User).filter(User.email == address).one().active
               and db.query(User).filter(User.email == address).one().has_role(D.FIELD_MANAGER)
               for address in msg.cc)


@pytest.mark.parametrize("qc_role", D.QC_ROLES)
def test_email_dual_field_manager_qc_role_is_allowed(db, w, qc_role):
    primary = w["p"]["mgr"]
    primary.roles.append(UserRole(role=qc_role))
    db.commit()
    to, cc = notify.recipients(db, w["a"])
    assert to.id == primary.id and primary.active and primary.has_role(D.FIELD_MANAGER)
    msg = notify.queue(db, w["a"], w["events"]["send"], w["p"]["op"],
                       "sent", base_url="http://testserver")
    assert msg is not None and msg.to_user_id == primary.id and msg.to_email == primary.email
    assert msg.cc == [w["p"]["mgr2"].email]
    for body in (msg.text, msg.html):
        assert D.QC_ANON_LABEL in body and w["p"]["op"].full_name not in body


def test_inactive_field_manager_is_excluded_from_to_and_cc(db, w):
    w["p"]["mgr"].active = False
    db.commit()
    to, cc = notify.recipients(db, w["a"])
    assert to.id == w["p"]["mgr2"].id and cc == []
    msg = notify.queue(db, w["a"], w["events"]["send"], w["p"]["op"],
                       "sent", base_url="http://testserver")
    assert msg is not None and msg.to_user_id == w["p"]["mgr2"].id and msg.cc == []
    w["p"]["mgr2"].active = False
    db.commit()
    count = db.query(EmailMessage).count()
    assert notify.recipients(db, w["a"]) == (None, [])
    assert notify.queue(db, w["a"], w["events"]["send"], w["p"]["op"],
                        "sent", base_url="http://testserver") is None
    assert db.query(EmailMessage).count() == count
