# -*- coding: utf-8 -*-
"""
პორტატული პაკეტი — საქაღალდე და ZIP, რომელიც სხვა Windows კომპიუტერზე ინსტალაციის გარეშე ეშვება.

  .venv\\Scripts\\python.exe scripts\\build_portable.py               :: მონაცემის გარეშე (მხოლოდ შემოწმებისთვის)
  .venv\\Scripts\\python.exe scripts\\build_portable.py --data real   :: 🔐 რეალური ბაზის ასლით

შედეგი: dist\\QC-Platforma\\ და dist\\QC-Platforma.zip
  • Python — python.org-ის ოფიციალური embeddable ZIP, იგივე ვერსია, რაც .venv-ში; ხელმოწერა მოწმდება;
  • ბიბლიოთეკები — .venv-იდან (pytest-ის გარეშე): ზუსტად ის, რაზეც ტესტები გადის;
  • data\\.session_secret, data\\raw, განაწილების წყარო და Google-ის კონფიგი პაკეტში არასოდეს ხვდება.
"""
import argparse
import json
import platform
import shutil
import sqlite3
import ssl
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

NAME = "QC-Platforma"
TEMPLATES = ROOT / "scripts" / "portable"
DIST = ROOT / "dist"
# ტესტების ბიბლიოთეკები და .venv-ის დამხმარე ფაილები პაკეტს არ სჭირდება
SKIP_PACKAGES = ("pytest", "_pytest", "pluggy", "iniconfig", "py.py", "_virtualenv", "__pycache__")
DATA_NOTES = {
    "none": "ბაზა არ მოჰყვება — ეს პაკეტი მხოლოდ შემოწმებისთვისაა და ასე არ გაეშვება.",
    "real": "🔐 შეიცავს რეალურ მონაცემს: თანამშრომლების სახელები, პირადი ნომრები, QC კომენტარები.\n"
            "  არ გადასცეთ სხვას. გამოყენების შემდეგ წაშალეთ საქაღალდეც და ZIP-იც.",
}


def download_python(version: str) -> Path:
    """embeddable ZIP python.org-იდან (ერთხელ; შემდეგ dist\\.cache-იდან)."""
    url = f"https://www.python.org/ftp/python/{version}/python-{version}-embed-amd64.zip"
    target = DIST / ".cache" / url.rsplit("/", 1)[1]
    if target.exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        import truststore                                # კორპორატიული სერტიფიკატი Windows-ის საცავიდან
        ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        ctx = ssl.create_default_context()
    print(f"  ჩამოტვირთვა: {url}")
    part = target.with_suffix(".part")
    with urllib.request.urlopen(url, context=ctx, timeout=120) as r, open(part, "wb") as f:
        shutil.copyfileobj(r, f)
    part.replace(target)
    return target


def check_signature(exe: Path):
    """python.exe უნდა იყოს ხელმოწერილი Python Software Foundation-ის მიერ — თორემ ვჩერდებით."""
    ps = (f"$s = Get-AuthenticodeSignature -LiteralPath '{exe}'; "
          "$s.Status; $s.SignerCertificate.Subject")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                         capture_output=True, text=True).stdout.splitlines()
    status = out[0].strip() if out else ""
    subject = out[1].strip() if len(out) > 1 else ""
    if status != "Valid" or "Python Software Foundation" not in subject:
        raise SystemExit(f"  ✗ python.exe-ს ხელმოწერა არ დადასტურდა ({status or 'უცნობი'}: {subject}). შევჩერდი.")
    print("  ✓ python.exe — ხელმოწერა: Python Software Foundation")


def build_runtime(out: Path, embed_zip: Path):
    rt = out / "runtime"
    with zipfile.ZipFile(embed_zip) as z:
        z.extractall(rt)
    check_signature(rt / "python.exe")
    # ._pth განსაზღვრავს sys.path-ს: სტანდარტული ბიბლიოთეკა, site-packages და `import site`
    pth = next(rt.glob("python3*._pth"))
    stdlib = next(rt.glob("python3*.zip")).name
    pth.write_text(f"{stdlib}\n.\nLib\\site-packages\nimport site\n", encoding="utf-8")
    src = Path(sys.prefix) / "Lib" / "site-packages"
    dst = rt / "Lib" / "site-packages"
    dst.mkdir(parents=True)
    for p in src.iterdir():
        if p.name.lower().startswith(SKIP_PACKAGES):
            continue
        if p.is_dir():
            shutil.copytree(p, dst / p.name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(p, dst / p.name)


def copy_real_data(out: Path):
    """ბაზის თანმიმდევრული ასლი (backup API) — სესიებისა და IP მისამართების გარეშე."""
    from app.config import DATA_DIR, RAW_DIR
    data = out / "data"
    data.mkdir()
    src = sqlite3.connect(f"file:{(DATA_DIR / 'platform.db').as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(data / "platform.db")
    try:
        src.backup(dst)
        dst.execute("DELETE FROM sessions")
        dst.execute("DELETE FROM presence")
        dst.execute("UPDATE audit_log SET ip = NULL")
        dst.commit()
        dst.execute("VACUUM")
    finally:
        dst.close()
        src.close()
    if (DATA_DIR / "uploads").is_dir():
        shutil.copytree(DATA_DIR / "uploads", data / "uploads")
    manifest = RAW_DIR / "control" / "manifest.json"
    if manifest.is_file():                               # ქვედა ზოლის თარიღისთვის — მხოლოდ fetched_at
        fetched = json.loads(manifest.read_text(encoding="utf-8")).get("fetched_at")
        (data / "raw" / "control").mkdir(parents=True)
        (data / "raw" / "control" / "manifest.json").write_text(
            json.dumps({"fetched_at": fetched}, ensure_ascii=False), encoding="utf-8")


def size_mb(path: Path) -> float:
    if path.is_file():
        return path.stat().st_size / 1e6
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1e6


def main():
    ap = argparse.ArgumentParser(description="პორტატული პაკეტის აწყობა")
    ap.add_argument("--data", choices=sorted(DATA_NOTES), default="none")
    ap.add_argument("--no-zip", action="store_true")
    args = ap.parse_args()
    if sys.prefix == sys.base_prefix:
        raise SystemExit("  ✗ გაუშვით პროექტის Python-ით: .venv\\Scripts\\python.exe scripts\\build_portable.py")

    out = DIST / NAME
    zip_path = DIST / f"{NAME}.zip"
    print(f"\n  პორტატული პაკეტი — Python {platform.python_version()}, მონაცემი: {args.data}")
    if args.data == "real":
        print("  🔐 პაკეტში რეალური მონაცემი ჩაიდება — გაუგზავნეთ მხოლოდ უფლებამოსილ ადამიანს, დაცული გზით.")
    if out.exists():
        shutil.rmtree(out)
    zip_path.unlink(missing_ok=True)
    out.mkdir(parents=True)

    build_runtime(out, download_python(platform.python_version()))
    shutil.copytree(ROOT / "app", out / "app", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(TEMPLATES / "START.bat", out / "START.bat")
    shutil.copy2(TEMPLATES / "run_portable.py", out / "run_portable.py")
    readme = (TEMPLATES / "README.txt").read_text(encoding="utf-8").replace("{DATA_NOTE}", DATA_NOTES[args.data])
    (out / "README.txt").write_text(readme, encoding="utf-8-sig")   # BOM — ძველ Notepad-შიც ქართულად
    if args.data == "real":
        copy_real_data(out)
    print(f"  ✓ საქაღალდე: {out}  ({size_mb(out):.0f} MB)")

    if not args.no_zip:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for f in sorted(out.rglob("*")):
                if f.is_file():
                    z.write(f, Path(NAME) / f.relative_to(out))
        print(f"  ✓ ZIP: {zip_path}  ({size_mb(zip_path):.0f} MB)")
    print()


if __name__ == "__main__":
    main()
