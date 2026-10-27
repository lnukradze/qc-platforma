# -*- coding: utf-8 -*-
"""
მონაცემთა მოდელი.

ცენტრალური ერთეული — `QcItem`: **ერთი ოქმი + ერთი საკადასტრო კოდი**
(ერთ კოდზე ერთი პასუხი იგზავნება). მასზე ინახება მიმდინარე მდგომარეობა,
ხოლო ყოველი ცვლილება `QcEvent`-ში იწერება — ის არასოდეს იცვლება და
არასოდეს იშლება. ასე სრული ისტორია (ვინ, რა როლით, როდის, რა→რა) რჩება.

ტიპები განზრახ პორტატულია (JSON, String) — იგივე სქემა SQLite-ზეც და
PostgreSQL-ზეც მუშაობს.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (JSON, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index,
                        Integer, String, Text, UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import domain as D
from .db import Base


def _now():
    return dt.datetime.now()


def _in(col, values):
    return f"{col} IN (" + ",".join(f"'{v}'" for v in values) + ")"


# ══════════════════════════════════════════════════════════════════════
#  ვინაობა და სტრუქტურა
# ══════════════════════════════════════════════════════════════════════
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    # შესადარებელი გასაღები — ჰარეებისა და პირადი ნომრის გარეშე
    name_key: Mapped[str] = mapped_column(String(200), index=True)
    # პირადი Gmail, რომლითაც შევა (მენეჯერები აგროვებენ)
    email: Mapped[str | None] = mapped_column(String(320), unique=True)
    # 🔐 მხოლოდ ვინაობის შესადარებლად; ინტერფეისში არასოდეს ჩანს სრულად
    personal_id: Mapped[str | None] = mapped_column(String(32))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(32), default="manual")
    note: Mapped[str | None] = mapped_column(String(300))
    # პირადი პარამეტრები, მაგ. QC მენეჯერის ნაგულისხმევი მიმართულება {"kind": "sporadic"}
    prefs: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    roles: Mapped[list["UserRole"]] = relationship(back_populates="user",
                                                   cascade="all, delete-orphan")

    @property
    def role_set(self) -> set[str]:
        return {r.role for r in self.roles}

    def has_role(self, *roles) -> bool:
        return bool(self.role_set & set(roles))

    def __repr__(self):  # 🔐 personal_id არ იბეჭდება
        return f"<User {self.id} {self.full_name}>"


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"),
                                         primary_key=True)
    role: Mapped[str] = mapped_column(String(32), primary_key=True)
    user: Mapped[User] = relationship(back_populates="roles")

    __table_args__ = (CheckConstraint(_in("role", D.ROLES), name="ck_user_role"),)


class Team(Base):
    """საველე გუნდი = მენეჯერი + მისი ამზომველები (Field Group-იდან)."""
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(16), default="field")
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    manager: Mapped[User | None] = relationship(foreign_keys=[manager_id])
    members: Mapped[list["TeamMember"]] = relationship(back_populates="team",
                                                       cascade="all, delete-orphan")


class TeamMember(Base):
    """წევრობა თარიღებით — ისტორიული მიკუთვნებისთვის."""
    __tablename__ = "team_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    valid_from: Mapped[dt.date | None] = mapped_column(Date)
    valid_to: Mapped[dt.date | None] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(32), default="field_group")

    team: Mapped[Team] = relationship(back_populates="members")
    user: Mapped[User] = relationship()


class PersonAlias(Base):
    """სახელის ვარიანტი → მომხმარებელი (ძველი ცხრილის ნედლი ჩანაწერებისთვის)."""
    __tablename__ = "person_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alias_key: Mapped[str] = mapped_column(String(200), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(32), default="auto")


# ══════════════════════════════════════════════════════════════════════
#  ცნობარები
# ══════════════════════════════════════════════════════════════════════
class DefectCode(Base):
    __tablename__ = "defect_codes"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(400))
    group: Mapped[str] = mapped_column(String(120))
    severity: Mapped[str] = mapped_column(String(16))         # Critical | Major | pending
    page: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)


class Mission(Base):
    __tablename__ = "missions"

    n: Mapped[int] = mapped_column(Integer, primary_key=True)
    start: Mapped[dt.date] = mapped_column(Date)
    end: Mapped[dt.date] = mapped_column(Date)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict | list | str | int | bool | None] = mapped_column(JSON)


# ══════════════════════════════════════════════════════════════════════
#  განაწილება
# ══════════════════════════════════════════════════════════════════════
class DistributionRun(Base):
    __tablename__ = "distribution_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    params: Mapped[dict] = mapped_column(JSON)
    seed: Mapped[int] = mapped_column(Integer)
    source_info: Mapped[dict | None] = mapped_column(JSON)
    summary: Mapped[dict | None] = mapped_column(JSON)
    item_count: Mapped[int] = mapped_column(Integer, default=0)

    created_by: Mapped[User | None] = relationship()


class DistributionPreset(Base):
    """შენახული წესი: „შემდეგ დღეებში ეს დიაპაზონი ამ ოპერატორებზე, ამ რაოდენობით"."""
    __tablename__ = "distribution_presets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    params: Mapped[dict] = mapped_column(JSON)
    valid_from: Mapped[dt.date | None] = mapped_column(Date)
    valid_to: Mapped[dt.date | None] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


# ══════════════════════════════════════════════════════════════════════
#  QC — ერთი ოქმი + საკადასტრო კოდი
# ══════════════════════════════════════════════════════════════════════
class QcItem(Base):
    __tablename__ = "qc_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    protocol_number: Mapped[str] = mapped_column(String(32))
    cadcode: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16), default=D.SYSTEMATIC)
    block_key: Mapped[str | None] = mapped_column(String(64))
    zone: Mapped[str | None] = mapped_column(String(8), index=True)
    sector: Mapped[str | None] = mapped_column(String(16))
    drawing_date: Mapped[dt.datetime | None] = mapped_column(DateTime)   # U — ნახაზის შეტანა
    field_status: Mapped[str | None] = mapped_column(String(120))       # საველე წარმოების სტატუსი

    # ოქმის შემდგენი (OQMI_CREATOR) — მისი მენეჯერია პასუხისმგებელი
    protocol_creator_name: Mapped[str | None] = mapped_column(String(200))
    protocol_creator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)

    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    assigned_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    # პასუხისმგებელი მენეჯერი (შემდგენის მენეჯერი). ყველა მიკუთვნებული მენეჯერი — people-ში
    field_manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    distribution_run_id: Mapped[int | None] = mapped_column(ForeignKey("distribution_runs.id"))

    # QC ვერდიქტი
    verdict: Mapped[str | None] = mapped_column(String(16))
    original_verdict: Mapped[str | None] = mapped_column(String(16))   # პირველი გაგზავნილი სტატუსი
    clarified: Mapped[bool] = mapped_column(Boolean, default=False)    # დაზუსტების გავლით
    qc_comment: Mapped[str | None] = mapped_column(Text)
    draft_saved_at: Mapped[dt.datetime | None] = mapped_column(DateTime)  # შენახული, არ გაგზავნილა
    # D — სტატუსის პირველი გაგზავნის დრო; რეპორტები მისით ითვლება და აღარ იცვლება
    checked_at: Mapped[dt.datetime | None] = mapped_column(DateTime, index=True)
    # პირველი გაგზავნა ნებისმიერი ვერდიქტით (დაზუსტების კითხვაც) — დღის რაოდენობა
    first_sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime, index=True)
    sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime)

    state: Mapped[str] = mapped_column(String(24), default=D.PENDING, index=True)
    close_reason: Mapped[str | None] = mapped_column(String(16))
    closed_at: Mapped[dt.datetime | None] = mapped_column(DateTime)

    # ველის პასუხი (J, K, L)
    field_response: Mapped[str | None] = mapped_column(String(16))
    field_comment: Mapped[str | None] = mapped_column(Text)
    field_responded_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    field_responder_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    # QC-ის საბოლოო დადასტურება (M) — მხოლოდ უარყოფითზე/რეკომენდაციაზე
    corrected_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    confirmed_at: Mapped[dt.datetime | None] = mapped_column(DateTime)

    returned_comment: Mapped[str | None] = mapped_column(Text)     # O — ბოლო დაბრუნება
    # „გასწორდა" მოინიშნა, QC-მ კი გაუსწორებელი ნახა — ცალკე აღრიცხვა (არა საერთო სტატისტიკაში)
    false_fix_count: Mapped[int] = mapped_column(Integer, default=0)
    return_count: Mapped[int] = mapped_column(Integer, default=0)
    dispute_count: Mapped[int] = mapped_column(Integer, default=0)
    manager_visa_comment: Mapped[str | None] = mapped_column(Text)
    qcm_explanation: Mapped[str | None] = mapped_column(Text)
    qcm_decision: Mapped[str | None] = mapped_column(String(16))   # stand | field_right | both_right
    # QC მენეჯერი: ველი მართალია → ოპერატორის შეცდომა (შეზღუდული სტატისტიკა)
    qc_error: Mapped[bool] = mapped_column(Boolean, default=False)
    both_right: Mapped[bool] = mapped_column(Boolean, default=False)
    # მიმდინარე დაბრუნებაზე სავალდებულოა საველე მენეჯერის ჩართვა (CC პრინციპი)
    manager_required: Mapped[bool] = mapped_column(Boolean, default=False)
    sporadic_meta: Mapped[dict | None] = mapped_column(JSON)

    # ძველი ცხრილიდან გადმოტანა
    is_legacy: Mapped[bool] = mapped_column(Boolean, default=False)
    legacy_source: Mapped[str | None] = mapped_column(String(120))
    legacy_row: Mapped[int | None] = mapped_column(Integer)
    legacy_extra: Mapped[dict | None] = mapped_column(JSON)

    version: Mapped[int] = mapped_column(Integer, default=1)       # ერთდროული ცვლილებისგან დაცვა
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    operator: Mapped[User | None] = relationship(foreign_keys=[operator_id])
    field_manager: Mapped[User | None] = relationship(foreign_keys=[field_manager_id])
    protocol_creator: Mapped[User | None] = relationship(foreign_keys=[protocol_creator_id])
    people: Mapped[list["ItemPerson"]] = relationship(back_populates="item",
                                                      cascade="all, delete-orphan",
                                                      order_by="ItemPerson.position")
    codes: Mapped[list["QcItemCode"]] = relationship(back_populates="item",
                                                     cascade="all, delete-orphan",
                                                     order_by="QcItemCode.code")
    events: Mapped[list["QcEvent"]] = relationship(back_populates="item",
                                                   order_by="QcEvent.id")
    attachments: Mapped[list["Attachment"]] = relationship(back_populates="item",
                                                           order_by="Attachment.id")

    __table_args__ = (
        UniqueConstraint("protocol_number", "cadcode", name="uq_item_protocol_cad"),
        CheckConstraint(_in("state", D.STATES), name="ck_item_state"),
        CheckConstraint("verdict IS NULL OR " + _in("verdict", D.VERDICTS), name="ck_item_verdict"),
        CheckConstraint(_in("kind", (D.SYSTEMATIC, D.SPORADIC)), name="ck_item_kind"),
        Index("ix_item_operator_state", "operator_id", "state"),
        Index("ix_item_manager_state", "field_manager_id", "state"),
        Index("ix_item_protocol", "protocol_number"),
        Index("ix_item_cadcode", "cadcode"),
    )

    @property
    def code_list(self) -> list[str]:
        return [c.code for c in self.codes]

    @property
    def surveyors(self) -> list["ItemPerson"]:
        return [p for p in self.people if p.kind == D.P_SURVEYOR]

    @property
    def managers(self) -> list["ItemPerson"]:
        """ყველა მიკუთვნებული მენეჯერი — პასუხისმგებელი პირველია."""
        ms = [p for p in self.people if p.kind == D.P_MANAGER]
        return sorted(ms, key=lambda p: (not p.is_primary, p.position))

    @property
    def surveyor_names(self) -> list[str]:
        return [p.display_name for p in self.surveyors]

    @property
    def is_draft(self) -> bool:
        return self.state == D.PENDING and self.draft_saved_at is not None


class ItemPerson(Base):
    """ოქმზე მიბმული ადამიანი: ამზომველი (ოქმის შემსრულებელი) ან მიკუთვნებული მენეჯერი."""
    __tablename__ = "item_people"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("qc_items.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str | None] = mapped_column(String(200))     # ნედლი სახელი (თუ ვერ დაუკავშირდა)
    kind: Mapped[str] = mapped_column(String(16))             # surveyor | manager
    position: Mapped[int] = mapped_column(Integer, default=0)
    # ამზომველზე — ოქმის შემდგენი; მენეჯერზე — პასუხისმგებელი (მოქმედებს მხოლოდ ის)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(16), default="auto")

    item: Mapped[QcItem] = relationship(back_populates="people")
    user: Mapped[User | None] = relationship()

    __table_args__ = (
        CheckConstraint(_in("kind", (D.P_SURVEYOR, D.P_MANAGER)), name="ck_person_kind"),
        Index("ix_people_user_kind", "user_id", "kind"),
    )

    @property
    def display_name(self) -> str:
        return self.user.full_name if self.user else (self.name or "—")


class QcItemCode(Base):
    __tablename__ = "qc_item_codes"

    item_id: Mapped[int] = mapped_column(ForeignKey("qc_items.id", ondelete="CASCADE"),
                                         primary_key=True)
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    source: Mapped[str] = mapped_column(String(16), default="auto")   # auto | manual | legacy
    item: Mapped[QcItem] = relationship(back_populates="codes")


class QcEvent(Base):
    """ისტორიის ერთი ჩანაწერი. **არასოდეს იცვლება და არასოდეს იშლება.**"""
    __tablename__ = "qc_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("qc_items.id"), index=True)
    at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    actor_role: Mapped[str | None] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(32))
    from_state: Mapped[str | None] = mapped_column(String(24))
    to_state: Mapped[str | None] = mapped_column(String(24))
    comment: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict | None] = mapped_column(JSON)
    approx: Mapped[bool] = mapped_column(Boolean, default=False)   # ძველი მონაცემიდან გამოყვანილი დრო

    item: Mapped[QcItem] = relationship(back_populates="events")
    actor: Mapped[User | None] = relationship()


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("qc_items.id"), index=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("qc_events.id"))
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    filename: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)

    item: Mapped[QcItem] = relationship(back_populates="attachments")
    uploaded_by: Mapped[User | None] = relationship()


class VerdictRequest(Base):
    """ოპერატორის მოთხოვნა: გაგზავნილი სტატუსის შეცვლა — QC მენეჯერის დადასტურებით."""
    __tablename__ = "verdict_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("qc_items.id", ondelete="CASCADE"), index=True)
    requested_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    requested_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    from_verdict: Mapped[str | None] = mapped_column(String(16))
    to_verdict: Mapped[str] = mapped_column(String(16))
    comment: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending")   # pending | approved | rejected
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    decision_comment: Mapped[str | None] = mapped_column(Text)

    item: Mapped[QcItem] = relationship()
    requested_by: Mapped[User | None] = relationship(foreign_keys=[requested_by_id])
    decided_by: Mapped[User | None] = relationship(foreign_keys=[decided_by_id])


class QcReview(Base):
    """QC მენეჯერის შეფასება ოპერატორის გავლილ ოქმზე (ერთი მიმდინარე; ისტორია — QcEvent-ში)."""
    __tablename__ = "qc_reviews"

    item_id: Mapped[int] = mapped_column(ForeignKey("qc_items.id", ondelete="CASCADE"),
                                         primary_key=True)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    marks: Mapped[list] = mapped_column(JSON)                  # REVIEW_MARKS-ის ქვესიმრავლე
    comment: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16), default="manual")    # manual | legacy

    item: Mapped[QcItem] = relationship()
    reviewer: Mapped[User | None] = relationship()


class Presence(Base):
    """ვინ ხსნის ოქმს ახლა (ყვითელი მოციმციმე ნიშანი). ძველი ჩანაწერები ავტომატურად იშლება."""
    __tablename__ = "presence"

    item_id: Mapped[int] = mapped_column(ForeignKey("qc_items.id", ondelete="CASCADE"),
                                         primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"),
                                         primary_key=True)
    role: Mapped[str | None] = mapped_column(String(32))
    last_seen: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, index=True)

    user: Mapped[User] = relationship()


class EmailMessage(Base):
    """გასაგზავნი/გაგზავნილი მეილი. SMTP-ის გარეშე რჩება „preview" სტატუსით (ნახვა ადმინში)."""
    __tablename__ = "emails"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, index=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    to_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    to_email: Mapped[str | None] = mapped_column(String(320))
    cc: Mapped[list | None] = mapped_column(JSON)
    subject: Mapped[str] = mapped_column(String(300))
    html: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    item_id: Mapped[int | None] = mapped_column(ForeignKey("qc_items.id"))
    kind: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="preview")  # preview | sent | failed | no_address
    sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    error: Mapped[str | None] = mapped_column(String(500))

    to_user: Mapped[User | None] = relationship(foreign_keys=[to_user_id])
    created_by: Mapped[User | None] = relationship(foreign_keys=[created_by_id])


class ManagerOverride(Base):
    """QC მენეჯერმა ხელით მიუწერა მენეჯერი ამზომველს, რომელიც FIELD_GROUP_272-ში აღარ არის."""
    __tablename__ = "manager_overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_key: Mapped[str] = mapped_column(String(200), unique=True)
    person_name: Mapped[str] = mapped_column(String(200))
    manager_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    set_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    set_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    note: Mapped[str | None] = mapped_column(String(300))

    manager: Mapped[User] = relationship(foreign_keys=[manager_id])
    set_by: Mapped[User | None] = relationship(foreign_keys=[set_by_id])


class DistributionBacklog(Base):
    """შერჩეული, მაგრამ ოპერატორების რაოდენობაში ვერ ჩატეული — შემდეგ განაწილებაზე პირველი შედის."""
    __tablename__ = "distribution_backlog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    protocol_number: Mapped[str] = mapped_column(String(32))
    cadcode: Mapped[str] = mapped_column(String(64))
    block_key: Mapped[str | None] = mapped_column(String(64))
    record: Mapped[dict] = mapped_column(JSON)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("distribution_runs.id"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    status: Mapped[str] = mapped_column(String(16), default="open")   # open | assigned

    __table_args__ = (UniqueConstraint("protocol_number", "cadcode", name="uq_backlog_item"),)


class SporadicImport(Base):
    """სპორადულის სიის ატვირთვა და განაწილება (IT-ის ყოველდღიური ფაილი)."""
    __tablename__ = "sporadic_imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    filename: Mapped[str | None] = mapped_column(String(255))
    params: Mapped[dict | None] = mapped_column(JSON)
    summary: Mapped[dict | None] = mapped_column(JSON)
    item_count: Mapped[int] = mapped_column(Integer, default=0)

    created_by: Mapped[User | None] = relationship()


# ══════════════════════════════════════════════════════════════════════
#  Pre-QC (ამ ეტაპზე ფიქსირებული სადემონსტრაციო მონაცემი)
# ══════════════════════════════════════════════════════════════════════
class PreqcCheck(Base):
    __tablename__ = "preqc_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    protocol_number: Mapped[str] = mapped_column(String(32), index=True)
    cadcode: Mapped[str | None] = mapped_column(String(64))
    item_id: Mapped[int | None] = mapped_column(ForeignKey("qc_items.id"))
    surveyor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    field_manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    zone: Mapped[str | None] = mapped_column(String(8))
    mission_n: Mapped[int | None] = mapped_column(Integer)
    protocol_date: Mapped[dt.date | None] = mapped_column(Date)
    checked_on: Mapped[dt.date | None] = mapped_column(Date)
    score: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))     # pass | warn | review | fail
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)

    findings: Mapped[list["PreqcFinding"]] = relationship(back_populates="check",
                                                          cascade="all, delete-orphan")
    surveyor: Mapped[User | None] = relationship(foreign_keys=[surveyor_id])


class PreqcFinding(Base):
    __tablename__ = "preqc_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    check_id: Mapped[int] = mapped_column(ForeignKey("preqc_checks.id", ondelete="CASCADE"),
                                          index=True)
    code: Mapped[str] = mapped_column(String(32))
    official_code: Mapped[str | None] = mapped_column(String(16))
    severity: Mapped[str] = mapped_column(String(16))   # fail | warn | unknown
    title: Mapped[str] = mapped_column(String(300))
    message: Mapped[str | None] = mapped_column(Text)
    recommendation: Mapped[str | None] = mapped_column(Text)

    check: Mapped[PreqcCheck] = relationship(back_populates="findings")


# ══════════════════════════════════════════════════════════════════════
#  სისტემური
# ══════════════════════════════════════════════════════════════════════
class ImportRun(Base):
    __tablename__ = "import_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    kind: Mapped[str] = mapped_column(String(32))
    source: Mapped[dict | None] = mapped_column(JSON)
    report: Mapped[dict | None] = mapped_column(JSON)
    item_count: Mapped[int] = mapped_column(Integer, default=0)


class Session(Base):
    """სერვერის მხარის სესია — cookie-ში მხოლოდ ხელმოწერილი sid."""
    __tablename__ = "sessions"

    sid: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    active_role: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))

    user: Mapped[User] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(64))
    entity: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[dict | None] = mapped_column(JSON)
    ip: Mapped[str | None] = mapped_column(String(64))

    actor: Mapped[User | None] = relationship()


# ══════════════════════════════════════════════════════════════════════
#  საკადასტრო კოდის ოქმები და ოპერატორების რეპორტი (2026-10-26)
# ══════════════════════════════════════════════════════════════════════
class CadProtocolCount(Base):
    """რამდენი ოქმია შედგენილი საკადასტრო კოდზე — განაწილებისას, წყაროდან (ბარათზე „ოქმების რაოდენობა“)."""
    __tablename__ = "cad_protocol_counts"

    cadcode: Mapped[str] = mapped_column(String(64), primary_key=True)
    count: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class ReportAdjustment(Base):
    """
    ოპერატორის დღის რეპორტის ხელით კორექცია. **არ იშლება** — გაუქმება `revoked_*`-ით,
    რომ ჩანდეს, ვინ რა შეცვალა. სტატუსი (შვებულება და სხვ.) — თითო დღეზე თითო ჩანაწერი.
    `kind` ∈ `D.REPORT_ADJ_KINDS` — მოწმდება კოდში და არა CHECK-ით, რომ ახალი სახე ბაზის შეცვლას არ ითხოვდეს.
    """
    __tablename__ = "report_adjustments"
    __table_args__ = (Index("ix_report_adj_day_operator", "day", "operator_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    day: Mapped[dt.date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(16))
    delta: Mapped[int] = mapped_column(Integer, default=0)          # მხოლოდ D.ADJ_COUNT-ზე: +N / −N
    note: Mapped[str | None] = mapped_column(String(300))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    revoked_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime)

    operator: Mapped[User] = relationship(foreign_keys=[operator_id])
    created_by: Mapped[User | None] = relationship(foreign_keys=[created_by_id])
    revoked_by: Mapped[User | None] = relationship(foreign_keys=[revoked_by_id])


# ══════════════════════════════════════════════════════════════════════
#  ერთჯერადი ფორმის token — კომენტარის დუბლიკატისგან დაცვა (T-019, B-11)
# ══════════════════════════════════════════════════════════════════════
class FormToken(Base):
    """
    გამოყენებული `once` token. ჩაიწერება იმავე ტრანზაქციაში, რაც კომენტარი; მეორედ იგივე token →
    PRIMARY KEY-ის დარღვევა → კომენტარი და მეილი აღარ იქმნება (ორჯერ დაჭერა, განმეორებითი POST).
    ახალი ცხრილია — `create_all` არსებულ ბაზაშიც ქმნის. ძველი ჩანაწერები (> 1 დღე) შეიძლება წაიშალოს.
    """
    __tablename__ = "form_tokens"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    used_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, index=True)
