# -*- coding: utf-8 -*-
"""
სახელების ნორმალიზება და ადამიანის პოვნა.

წყაროში ერთი ადამიანი რამდენიმე ფორმით გვხვდება (ზედმეტი ჰარე, ტაბი,
სახელზე მიწერილი პირადი ნომერი, ბრჭყალები). წესები გადმოტანილია
qc-dashboard-ის `clean_name`-იდან და განაწილების პროგრამის `strip_spaces`-იდან.
"""
import re

PID_RE = re.compile(r"(?<!\d)(\d{9,11})(?!\d)")     # პირადი ნომერი (\b ქართულზე არ მუშაობს)
QUOTES_RE = re.compile(r"[\"'`«»„“”]+")
BLANKS = {"", "-", "--", "---", ".", ",", "?", "n/a", "na", "null", "none", "test", "ტესტი",
          "შეცდომა", "error", "#n/a"}
# „ოფისი" Field Group-ში ჯგუფის აღნიშვნაა და არა ადამიანი (დასაზუსტებელია, რეალური გუნდია თუ არა)
NON_MANAGER = {"შესავსები", "ჯამი", "შესავსებია", "სულ", "ოფისი"}


def clean_name(s) -> str:
    """ჩვენებისთვის: პირადი ნომერი, ბრჭყალები და ზედმეტი ჰარეები მოცილებული."""
    s = "" if s is None else str(s)
    s = PID_RE.sub(" ", s)
    s = QUOTES_RE.sub(" ", s)
    return " ".join(s.split()).strip()


def name_key(s) -> str:
    """შესადარებელი გასაღები — ყველა ჰარე მოცილებული (`strip_spaces`)."""
    return "".join(clean_name(s).split())


def is_blank_name(s) -> bool:
    t = clean_name(s).lower()
    if t in BLANKS:
        return True
    return not re.search(r"[Ⴀ-ჿA-Za-z]", t)


def split_names(cell) -> list[str]:
    """უჯრა → სახელების სია. ტაბი/ახალი ხაზი გამყოფია (ერთ უჯრაში ორი ამზომველი)."""
    raw = re.split(r"[\r\n]+", "" if cell is None else str(cell))
    out = []
    for part in raw:
        for p in re.split(r"\t+", part):
            c = clean_name(p)
            if c and not is_blank_name(c):
                out.append(c)
    return out


def clean_manager(s) -> str:
    v = clean_name(s)
    return "" if v in NON_MANAGER or is_blank_name(v) else v
