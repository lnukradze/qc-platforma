# -*- coding: utf-8 -*-
"""
საერთო ლექსიკონი — როლები, ვერდიქტები, სტატუსები, პასუხები და მათი წარწერები.

⚠️ ერთადერთი ადგილი, სადაც ეს მნიშვნელობები ჩამოთვლილია: შაბლონები,
   სამუშაო პროცესი, სტატისტიკა და ტესტები მხოლოდ აქედან კითხულობენ.
"""
import datetime as dt

# ── როლები ────────────────────────────────────────────────────────────
COORDINATOR = "coordinator"
HEAD_OF_SERVICE = "head_of_service"
FIELD_MANAGER = "field_manager"
QC_MANAGER = "qc_manager"
QC_OPERATOR = "qc_operator"
SURVEYOR = "surveyor"
ADMIN = "admin"

ROLES = (COORDINATOR, HEAD_OF_SERVICE, FIELD_MANAGER, QC_MANAGER, QC_OPERATOR, SURVEYOR, ADMIN)
ROLE_LABELS = {
    COORDINATOR: "კოორდინატორი",
    HEAD_OF_SERVICE: "სამსახურის უფროსი",
    FIELD_MANAGER: "საველე მენეჯერი",
    QC_MANAGER: "კონტროლის მენეჯერი",
    QC_OPERATOR: "კონტროლის ოპერატორი",
    SURVEYOR: "ამზომველი",
    ADMIN: "ადმინისტრატორი",
}
ROLE_SHORT = {
    COORDINATOR: "კოორდინატორი", HEAD_OF_SERVICE: "სამსახურის უფროსი",
    FIELD_MANAGER: "საველე მენეჯერი", QC_MANAGER: "QC მენეჯერი", QC_OPERATOR: "QC ოპერატორი",
    SURVEYOR: "ამზომველი", ADMIN: "ადმინი",
}
FIELD_ROLES = (FIELD_MANAGER, SURVEYOR)
QC_ROLES = (QC_OPERATOR, QC_MANAGER, ADMIN)

# ── QC ვერდიქტი ───────────────────────────────────────────────────────
POSITIVE = "positive"
NEGATIVE = "negative"
RECOMMENDATION = "recommendation"
CLARIFICATION = "clarification"
VERDICTS = (POSITIVE, NEGATIVE, RECOMMENDATION, CLARIFICATION)
# „დაზუსტება" სტატუსი არ არის — კითხვაა. საბოლოო სტატუსი პასუხის შემდეგ ენიჭება
# და სტატისტიკაში დადებითად **არ** ითვლება (მომხმარებლის წესი, 2026-10-20).
FINAL_VERDICTS = (POSITIVE, NEGATIVE, RECOMMENDATION)
VERDICT_LABELS = {
    POSITIVE: "დადებითი",
    NEGATIVE: "უარყოფითი",
    RECOMMENDATION: "რეკომენდაცია",
    CLARIFICATION: "დაზუსტება",
}
# ძველი ცხრილის ტექსტი → ვერდიქტი
VERDICT_FROM_SHEET = {"დადებითი": POSITIVE, "უარყოფითი": NEGATIVE, "რეკომენდაცია": RECOMMENDATION,
                      "დაზუსტება": CLARIFICATION}

# ── სამუშაო მდგომარეობა (state machine) ───────────────────────────────
PENDING = "pending"                         # დანიშნულია, ჯერ არ გაგზავნილა
AWAITING_FIELD = "awaiting_field"           # ველზე — ამზომველის პასუხის მოლოდინში
AWAITING_MANAGER = "awaiting_manager"       # „არ ვეთანხმები" — საველე მენეჯერის დადასტურება
AWAITING_QCM = "awaiting_qcm"               # არ დათანხმებული — QC მენეჯერის გადაწყვეტილება
RETURNED_TO_MANAGER = "returned_to_manager"  # დაბრუნებულია საველე მენეჯერთან (პასუხობს მხოლოდ მენეჯერი)
AWAITING_QC = "awaiting_qc"                 # ველმა უპასუხა — QC-ის გადამოწმება
CLOSED = "closed"

STATES = (PENDING, AWAITING_FIELD, AWAITING_MANAGER, AWAITING_QCM, RETURNED_TO_MANAGER,
          AWAITING_QC, CLOSED)
STATE_LABELS = {
    PENDING: "გასავლელი",
    AWAITING_FIELD: "ველზე — პასუხის მოლოდინში",
    AWAITING_MANAGER: "„არ ვეთანხმები“ — მენეჯერის დადასტურება",
    AWAITING_QCM: "არ დათანხმებული — QC მენეჯერთან",
    RETURNED_TO_MANAGER: "დაბრუნებულია მენეჯერთან",
    AWAITING_QC: "პასუხი მოვიდა — გადასამოწმებელი",
    CLOSED: "დახურული",
}

# დახურვის მიზეზი
CR_POSITIVE = "positive"          # დადებითი ვერდიქტი
CR_CORRECTED = "corrected"        # უარყოფითი → გასწორდა (M)
CR_ACKNOWLEDGED = "acknowledged"  # რეკომენდაცია → გავითვალისწინებთ (M)
CR_QC_ERROR = "qc_error"          # QC მენეჯერი: ველი მართალია → დადებითი + ოპერატორის შეცდომა
CR_BOTH_RIGHT = "both_right"      # QC მენეჯერი: ორივე მართალია → დადებითი, არავის ხარვეზი
CLOSE_REASON_LABELS = {
    CR_POSITIVE: "დადებითი",
    CR_CORRECTED: "გასწორდა",
    CR_ACKNOWLEDGED: "გათვალისწინებულია",
    CR_QC_ERROR: "ველი მართალია → დადებითი",
    CR_BOTH_RIGHT: "ორივე მართალია → დადებითი",
}

# QC მენეჯერის გადაწყვეტილება არ დათანხმებულზე
QCM_STAND = "stand"
QCM_FIELD_RIGHT = "field_right"
QCM_BOTH_RIGHT = "both_right"
QCM_DECISION_LABELS = {
    QCM_STAND: "ხარვეზი რჩება",
    QCM_FIELD_RIGHT: "ველი მართალია — ოპერატორის შეცდომა",
    QCM_BOTH_RIGHT: "ორივე მართალია",
}

# QC მენეჯერის შეფასება ოპერატორის გავლილ ოქმზე (შეზღუდული სტატისტიკა)
MARK_CORRECT = "correct"
MARK_WRONG = "wrong_defect"
MARK_MISSED = "missed_defect"
MARK_INCOMPLETE = "incomplete_info"
REVIEW_MARKS = (MARK_CORRECT, MARK_WRONG, MARK_MISSED, MARK_INCOMPLETE)
MARK_LABELS = {
    MARK_CORRECT: "სწორია",
    MARK_WRONG: "არასწორი ხარვეზი",
    MARK_MISSED: "გამორჩენილი ხარვეზი",
    MARK_INCOMPLETE: "არასრულყოფილი ინფორმაცია ხარვეზზე",
}
ERROR_MARKS = (MARK_WRONG, MARK_MISSED, MARK_INCOMPLETE)
# ძველი ცხრილის TYPE (V სვეტი) → შეფასება
LEGACY_TYPE_TO_MARK = {"correct": MARK_CORRECT, "false defect": MARK_WRONG,
                       "missed defect": MARK_MISSED}

# ── ფერები ────────────────────────────────────────────────────────────
# ოპერატორის ხედი: ნაცრისფერი / ღია ლურჯი (შენახული) / ღია მწვანე / ყვითელი / მწვანე
def operator_color(state, draft=False):
    if state == PENDING:
        return "draft" if draft else "gray"
    if state == AWAITING_QC:
        return "yellow"
    if state == CLOSED:
        return "green"
    return "lightgreen"        # გაგზავნილია — ველის ან მენეჯერების მხარეს


COLOR_LABELS = {
    "gray": "გასავლელი",
    "draft": "შენახული — ჯერ არ გაგზავნილა",
    "lightgreen": "გაგზავნილია",
    "green": "დასრულებული",
    "yellow": "ველმა უპასუხა — გადასამოწმებელი",
    "orange": "პასუხი სჭირდება",
    "blue": "მენეჯერთან",
}


# ველის ხედი
def field_color(state):
    if state == AWAITING_FIELD:
        return "orange"
    if state in (AWAITING_MANAGER, RETURNED_TO_MANAGER):
        return "blue"
    if state == CLOSED:
        return "green"
    return "lightgreen"


# ── ველის პასუხები ────────────────────────────────────────────────────
R_CORRECTED = "corrected"        # შესწორდა
R_DISAGREE = "disagree"          # არ ვეთანხმები
R_ACKNOWLEDGE = "acknowledge"    # გავითვალისწინებთ
R_ANSWER = "answer"              # პასუხი დაზუსტებაზე
RESPONSE_LABELS = {
    R_CORRECTED: "შესწორდა",
    R_DISAGREE: "არ ვეთანხმები",
    R_ACKNOWLEDGE: "გავითვალისწინებთ",
    R_ANSWER: "პასუხი დაზუსტებაზე",
}
# ველის პასუხის მკაფიო ნიშანი სიებსა და ბარათზე
RESPONSE_STYLE = {R_CORRECTED: "ok", R_DISAGREE: "bad", R_ACKNOWLEDGE: "info", R_ANSWER: "cla"}
RESPONSE_ICONS = {R_CORRECTED: "✔", R_DISAGREE: "✖", R_ACKNOWLEDGE: "✓", R_ANSWER: "?"}
RESPONSE_FROM_SHEET = {"შესწორდა": R_CORRECTED, "გასწორდა": R_CORRECTED,
                       "არ ვეთანხმები": R_DISAGREE, "გავითვალისწინებთ": R_ACKNOWLEDGE,
                       "გავითვალისწინე": R_ACKNOWLEDGE, "გავითვალისწინებ": R_ACKNOWLEDGE}

# ნაგულისხმევი: რომელი პასუხია დაშვებული რომელ ვერდიქტზე (ადმინს შეუძლია შეცვალოს)
DEFAULT_ALLOWED_RESPONSES = {          # ლუკა, 2026-10-26: რეკომენდაციაზე — სამივე; დაზუსტებაზე — მხოლოდ კომენტარი
    NEGATIVE: [R_CORRECTED, R_DISAGREE],
    RECOMMENDATION: [R_CORRECTED, R_ACKNOWLEDGE, R_DISAGREE],
    CLARIFICATION: [R_ANSWER],
}

# ── სახეობა ───────────────────────────────────────────────────────────
SYSTEMATIC = "systematic"
SPORADIC = "sporadic"
KIND_LABELS = {SYSTEMATIC: "სისტემური", SPORADIC: "სპორადული"}

# ── ოქმზე მიბმული ადამიანები ──────────────────────────────────────────
P_SURVEYOR = "surveyor"
P_MANAGER = "manager"

# ── მოვლენები (ისტორია) ───────────────────────────────────────────────
EVENT_LABELS = {
    "assigned": "დაინიშნა ოპერატორზე",
    "reassigned": "გადანაწილდა",
    "review_saved": "შენახულია (გაუგზავნელი)",
    "sent": "გაიგზავნა",
    "edited": "შეიცვალა გაგზავნის შემდეგ",
    "verdict_changed": "სტატუსი შეიცვალა (QC მენეჯერი)",
    "verdict_change_requested": "მოთხოვნილია სტატუსის შეცვლა",
    "verdict_change_approved": "სტატუსის შეცვლა დადასტურდა",
    "verdict_change_rejected": "სტატუსის შეცვლა უარყოფილია",
    "field_responded": "ველის პასუხი",
    "manager_approved": "მენეჯერმა დაადასტურა „არ ვეთანხმები“",
    "manager_rejected": "მენეჯერმა ამზომველს დაუბრუნა",
    "manager_responded": "მენეჯერის პასუხი",
    "qcm_stand": "QC მენეჯერი: ხარვეზი რჩება",
    "qcm_field_right": "QC მენეჯერი: ველი მართალია",
    "qcm_both_right": "QC მენეჯერი: ორივე მართალია",
    "qc_confirmed": "QC-მ დაადასტურა",
    "qc_returned": "QC-მ დააბრუნა — არ არის გასწორებული",
    "clarification_resolved": "დაზუსტდა — მიენიჭა სტატუსი",
    "clarify_again": "დამატებითი კითხვა",
    "qc_reviewed": "QC მენეჯერის შეფასება",
    "manager_assigned": "მიეწერა მენეჯერი",
    "converted_to_sporadic": "გადავიდა სპორადულში",
    "comment": "კომენტარი",
    "legacy_import": "გადმოტანილია ძველი ცხრილიდან",
}

SEVERITY_LABELS = {"Critical": "კრიტიკული", "Major": "მნიშვნელოვანი"}

# ── ველისთვის კონტროლი ანონიმურია (ლუკა, 2026-10-26) ─────────────────
# ამზომველს და საველე მენეჯერს QC ოპერატორის / QC მენეჯერის სახელი არსად უჩანს — მხოლოდ ეს წარწერა
QC_ANON_LABEL = "ხარისხის კონტროლი"

# ── სიები: რამდენი ჩანაწერი გვერდზე (ყველა ფილტრის სექციაში, 10–30) ──
PAGE_SIZE_MIN, PAGE_SIZE_MAX, PAGE_SIZE_DEFAULT = 10, 30, 10

# ── ოპერატორების რეპორტი (ლუკა, 2026-10-26) ──────────────────────────
# მხოლოდ ორშ–პარ; „საშუალო ...-დან“ — ფიქსირებული თარიღიდან; „კვირები“ — ნაგულისხმევად ბოლო 4
REPORT_SINCE = dt.date(2026, 7, 1)
REPORT_WEEKS_DEFAULT = 4

# ხელით შესწორება (QC მენეჯერი / ადმინი). ADJ_COUNT რაოდენობას ცვლის, დანარჩენი — დღის სტატუსია
ADJ_COUNT = "count"          # +/−, მაგ. ერთს მოაკლო, მეორეს დაუწერო
ADJ_VACATION = "vacation"
ADJ_SICK = "sick_leave"
ADJ_DUTY = "duty"
ADJ_DAY_OFF = "day_off"
REPORT_ADJ_KINDS = {
    ADJ_COUNT: "შესწორება",
    ADJ_VACATION: "შვებულება",
    ADJ_SICK: "ბიულეტინი",
    ADJ_DUTY: "სამსახურეობრივი დავალება",
    ADJ_DAY_OFF: "დეიოფი",
}
ADJ_STATUS_KINDS = (ADJ_VACATION, ADJ_SICK, ADJ_DUTY, ADJ_DAY_OFF)   # რიგი = უპირატესობა, თუ კვირაში რამდენიმეა
