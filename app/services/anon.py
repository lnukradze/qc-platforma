# -*- coding: utf-8 -*-
"""
კონტროლის ანონიმურობა ველისთვის (ლუკას გადაწყვეტილება, OPEN_QUESTIONS).

  • ველის მნახველი (ამზომველი, საველე მენეჯერი) + QC მოქმედება (ოპერატორი, QC მენეჯერი, ადმინი)
    → D.QC_ANON_LABEL („ხარისხის კონტროლი");
  • სხვა ყველა შემთხვევა → სრული სახელი. ანონიმურობა ერთმხრივია: QC ველის სახელს ხედავს.

როლი — კონკრეტული მოქმედების (`actor_role`), არა მომხმარებლის ყველა როლი: მრავალროლიანი
მომხმარებლის ველის მოქმედება ველისად რჩება. ბაზაში არაფერი იცვლება — მხოლოდ ჩვენება.
"""
from .. import domain as D


def is_qc_actor(user, actor_role) -> bool:
    """QC-ის მოქმედებაა? როლი უცნობია (ძველი ჩანაწერი) → მომხმარებლის როლებით, უსაფრთხოდ."""
    if actor_role:
        return actor_role in D.QC_ROLES
    return user is not None and bool(set(user.role_set) & set(D.QC_ROLES))


def hidden(viewer_role, user, actor_role) -> bool:
    return viewer_role in D.FIELD_ROLES and is_qc_actor(user, actor_role)


def actor_name(viewer_role, user, actor_role) -> str:
    if hidden(viewer_role, user, actor_role):
        return D.QC_ANON_LABEL
    return user.full_name if user is not None else ""
