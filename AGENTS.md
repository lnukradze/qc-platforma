# AGENTS.md — საერთო წესები ყველა AI აგენტისთვის

ამ ფაილს ყველა აგენტი კითხულობს: Codex პირდაპირ, Claude Code `CLAUDE.md`-ის გავლით.
შენი როლის დეტალები: `docs/team/roles/<როლი>.md`. ამოცანები: `docs/TASKS.md`. ადამიანებს ქართულად ესაუბრე.

## პროექტი

NAPR-ის ხარისხის კონტროლის ერთიანი პლატფორმის პროტოტიპი:
FastAPI + SQLAlchemy (SQLite, საწარმოოში PostgreSQL) + Jinja2 / HTMX / ECharts.
აღწერა — `README.md`, არქიტექტურა — `docs/ARCHITECTURE.md`, გადასაწყვეტი საკითხები — `docs/OPEN_QUESTIONS.md`.

## გუნდი და იერარქია

| როლი | ვინ | ანგარიში | ზონა — რას ცვლის |
|---|---|---|---|
| **lead** | ლუკა | Claude #1 | `AGENTS.md`, `CLAUDE.md`, `docs/`, `app/models.py`, `app/domain.py`, `app/config.py`, `requirements.txt` |
| **backend** | სალომე | Claude #2 | `app/services/`, `app/routes/`, `app/workflow.py`, `app/scope.py`, `app/security.py`, `app/main.py`, `app/db.py`, `scripts/` (გარდა `smoke_*`) |
| **ui** | სალომე | Claude #3 | `app/templates/`, `app/static/`, `app/templating.py`, `.taste-skill/` |
| **qa** | სალომე | GPT (Codex) | `tests/`, `scripts/smoke_*.py`, PR-ების რევიუ |

- ფაილებს მხოლოდ შენს ზონაში ცვლი. სხვის ზონაში თუ რამე გჭირდება, PR-ის აღწერის ნაწილში „სხვა როლებისგან სჭირდება“ წერ.
- **საერთო კონტრაქტი** lead-ისაა: `models.py` (ბაზის სტრუქტურა), `domain.py` (როლები, სტატუსები, წარწერები, ფერები), `config.py`.
  თუ backend-ს ან ui-ს ცვლილება სჭირდება, ჯერ lead ცვლის main-ში და მერე იყენებენ.
- `docs/TASKS.md`-ს **მხოლოდ lead** ცვლის. ასე merge-ის კონფლიქტი არ ჩნდება. დანარჩენები სტატუსს PR-ის აღწერაში წერენ.
- `main`-ში პირდაპირ მხოლოდ lead წერს. PR-ს **მხოლოდ lead აერთიანებს**, qa-ს შემოწმების შემდეგ. ბოლო სიტყვა ადამიანისაა.

## უცვლელი წესები (ყველასთვის)

- 🔐 `data/` შეიცავს რეალურ სახელებს, პირად ნომრებს, ფოტოებს და QC კომენტარებს. არასოდეს მოხვდეს git-ში, PR-ში,
  ლოგში, ტესტში ან ეკრანის ანაბეჭდში. ტესტში მხოლოდ გამოგონილი მონაცემი (`example.com`, ყალბი ნომრები).
- ბიზნეს-წესებს ნუ იგონებ. გაურკვეველი საკითხი → კითხვა PR-ში ან ადამიანთან. lead მას `docs/OPEN_QUESTIONS.md`-ში ჩაწერს.
- არსებულ სისტემებში (Google ცხრილები, REGFIELDALL, განაწილების პროგრამა) არაფერი იწერება — მხოლოდ კითხვა.
- `.bat` ფაილები მხოლოდ ASCII-ით (cmd.exe UTF-8-ს ვერ კითხულობს). ქართული ტექსტი Python-იდან იბეჭდება. `.ps1` ფაილებიც ASCII-ით.
- uvicorn — `--reload`-ის გარეშე.
- `scripts/build_db.py` ბაზას ნულიდან აწყობს და პროტოტიპში შეტანილ ცვლილებებს შლის. აგენტი მას თავისით **არ უშვებს** —
  მხოლოდ ადამიანის თანხმობით, სერვერის გაჩერების შემდეგ.

## ბრძანებები

`scripts\team\agent.bat`-ით გაშვებისას `$env:QCP_PY` (Python), `$env:QCP_PORT` (პორტი) და `$env:QCP_DATA_DIR` უკვე დაყენებულია.
სხვა შემთხვევაში Python არის `.venv\Scripts\python.exe`, პორტი — 8200.

```powershell
& $env:QCP_PY -m pytest -q                              # ტესტები — დროებით ბაზაზე, data\-ს არ ეხება
& $env:QCP_PY scripts\run_local.py --no-browser         # სერვერი: http://127.0.0.1:$env:QCP_PORT
& $env:QCP_PY scripts\smoke_pages.py                    # ყველა გვერდი ყველა როლით (გაშვებულ სერვერზე)
```

## ამოცანის ციკლი

1. lead ამოცანას `docs/TASKS.md`-ში წერს და main-ში ტვირთავს.
   უახლესი ვერსიის წაკითხვა ნებისმიერი ადგილიდან: `git fetch; git show origin/main:docs/TASKS.md`.
2. აგენტი ახალ ბრენჩს ქმნის: `git fetch; git switch -c <როლი>/T-<ნომერი>-<მოკლე-სახელი> origin/main`.
3. მუშაობს მხოლოდ თავის ზონაში → `pytest -q` გადის → commit → `git push -u origin <ბრენჩი>`.
   commit და push მხოლოდ საკუთარ ბრენჩზე და მხოლოდ მაშინ, როცა ადამიანი ეტყვის.
4. PR იხსნება GitHub-ზე, შაბლონით (`.github/pull_request_template.md`).
5. qa ამოწმებს. lead ამოწმებს და აერთიანებს. merge-ის შემდეგ lead `docs/TASKS.md`-ს ანახლებს.
