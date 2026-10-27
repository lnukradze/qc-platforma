# AGENTS.md — საერთო წესები ყველა AI აგენტისთვის

ამ ფაილს ყველა აგენტი კითხულობს: Codex პირდაპირ, Claude Code `CLAUDE.md`-ის გავლით.
შენი როლი: `docs/team/roles/<როლი>.md`. ამოცანები: `docs/TASKS.md` (სია) და `docs/tasks/T-*.md` (თითო ამოცანა).
დიზაინი: `DESIGN.md`. ადამიანებს ქართულად ესაუბრე.

## პროექტი

NAPR-ის ხარისხის კონტროლის ერთიანი პლატფორმის პროტოტიპი:
FastAPI + SQLAlchemy (SQLite, საწარმოოში PostgreSQL) + Jinja2 / HTMX / ECharts.
აღწერა — `README.md`, არქიტექტურა — `docs/ARCHITECTURE.md`, გადასაწყვეტი საკითხები — `docs/OPEN_QUESTIONS.md`.

## გუნდი და იერარქია

| როლი | ვინ | აგენტი | პასუხისმგებლობა | ზონა — რას ცვლის |
|---|---|---|---|---|
| **lead** | ლუკა | ლუკას Claude | ამოცანების მენეჯერი: წერს ბრიფს, ამოწმებს უსაფრთხოებას და ვიზუალს, ჩაიბარებს და აერთიანებს | `AGENTS.md`, `CLAUDE.md`, `DESIGN.md`, `docs/` (გარდა qa-ს ნაწილებისა `docs/tasks/`-ში), `tools/`, `app/models.py`, `app/domain.py`, `app/config.py`, `requirements.txt` |
| **ui** — აწყობა | სალომე | სალომეს Claude (`salome-1`) | გვერდები და დიზაინი | `app/templates/`, `app/static/`, `app/templating.py` |
| **backend** — ფუნქციონალი და თავსებადობა | სალომე | სალომეს მეორე Claude (`salome-2`) | Python-ის ლოგიკა; თავსებადობა: ტელეფონი, ბრაუზერები, PostgreSQL, API | `app/services/`, `app/routes/`, `app/workflow.py`, `app/scope.py`, `app/security.py`, `app/main.py`, `app/db.py`, `scripts/` (გარდა `smoke_*`) |
| **qa** — lead-ის მარჯვენა ხელი | სალომე | სალომეს Codex | lead-ის ბრიფს შემსრულებლის დეტალურ პრომპტად აქცევს (განსაკუთრებით დიზაინში); მეორე ტესტერი | `docs/tasks/` (ნაწილები 2 და 3), `tests/`, `scripts/smoke_*.py` |

- ფაილებს მხოლოდ შენს ზონაში ცვლი. სხვის ზონაში თუ რამე გჭირდება, commit-ის აღწერაში ან საბოლოო პასუხში დაწერე
  „სხვა როლებისგან სჭირდება“. lead მას ცალკე ამოცანად აქცევს.
- **საერთო კონტრაქტი** lead-ისაა: `models.py` (ბაზის სტრუქტურა), `domain.py` (როლები, სტატუსები, წარწერები, ფერები), `config.py`.
  თუ backend-ს ან ui-ს ცვლილება სჭირდება, ჯერ lead ცვლის main-ში და მერე იყენებენ.
- **ვინ წერს main-ში:** lead — ყველაფერს (merge). qa — მხოლოდ `docs/tasks/`-ს (პრომპტი და ტესტის ოქმი; push-მდე `git pull --rebase`).
  ui და backend — მხოლოდ საკუთარ ბრენჩზე.
- **ჩაბარება და merge მხოლოდ lead-ისაა**, qa-ს ტესტის შემდეგ. ბოლო სიტყვა ლუკასია.
- qa ბრიფს — „რა“ და დასრულების პირობას — არ ცვლის, მხოლოდ „როგორ“-ს ამატებს. ბრიფი თუ გაუგებარია — კითხვა lead-ს, არა ვარაუდი.
- ამოცანის აღება („აიღე T-NNN“) ნიშნავს ნებართვას: ამ ამოცანის ბრენჩზე commit და push.

## უცვლელი წესები (ყველასთვის)

- 🔐 `data/` შეიცავს რეალურ სახელებს, პირად ნომრებს, ფოტოებს და QC კომენტარებს. არასოდეს მოხვდეს git-ში, ამოცანის ფაილში,
  ლოგში, ტესტში ან ეკრანის ანაბეჭდში, რომელიც სადმე იგზავნება. ტესტში მხოლოდ გამოგონილი მონაცემი (`example.com`, ყალბი ნომრები).
- 🔐 **AI აგენტი რეალურ ბაზას არ ხსნის** — არც სერვერით, არც პირდაპირ (`data\`, `*.db`, `napr_data.sqlite`). სერვერს უშვებს მხოლოდ
  დემო ბაზით: `..\qc-demo-data` (`scripts\build_demo_db.py`, T-006). რეალურ ბაზაზე ამოწმებს ადამიანი.
  `app/config.py` ამას თავად იცავს: Claude Code-ის ბრძანებებში (`CLAUDECODE=1`) და `agent.ps1`-ით (`QCP_AGENT=1`) ყველა მისამართი,
  რომელიც დემო ან დროებით საქაღალდეში არ არის, დემოთი იცვლება. Codex VS Code-ის პანელიდან — მხოლოდ `QCP_AGENT=1`-ით (`docs/team/SALOME.md`).
- ბიზნეს-წესებს ნუ იგონებ. გაურკვეველი საკითხი → კითხვა lead-ს. lead მას `docs/OPEN_QUESTIONS.md`-ში ჩაწერს.
- არსებულ სისტემებში (Google ცხრილები, REGFIELDALL, განაწილების პროგრამა) არაფერი იწერება — მხოლოდ კითხვა.
- დიზაინი უკვე არჩეულია — „იზოხაზი“ (`DESIGN.md`). ახალ დიზაინის სისტემას არ ქმნი. Tailwind, CDN, გარე ფონტი, სურათი ან სკრიპტი — არა.
- `.bat` და `.ps1` ფაილები მხოლოდ ASCII-ით (Windows-ის cmd და PowerShell 5.1 UTF-8-ს ვერ კითხულობენ). ქართული ტექსტი Python-იდან იბეჭდება.
- uvicorn — `--reload`-ის გარეშე.
- `scripts/build_db.py` ბაზას ნულიდან აწყობს და პროტოტიპში შეტანილ ცვლილებებს შლის. აგენტი მას თავისით **არ უშვებს** —
  მხოლოდ ადამიანის თანხმობით, სერვერის გაჩერების შემდეგ.

## ბრძანებები

`scripts\team\agent.bat`-ით გაშვებისას `$env:QCP_PY` (Python), `$env:QCP_PORT` (პორტი) და `$env:QCP_DATA_DIR` უკვე დაყენებულია.
სხვა შემთხვევაში Python არის `.venv\Scripts\python.exe`, პორტი — 8200.

```powershell
& $env:QCP_PY -m pytest -q                              # ტესტები — დროებით ბაზაზე, data\-ს არ ეხება
& $env:QCP_PY scripts\run_local.py --no-browser         # სერვერი: http://127.0.0.1:$env:QCP_PORT
& $env:QCP_PY scripts\smoke_pages.py                    # ყველა გვერდი ყველა როლით (გაშვებულ სერვერზე, $env:QCP_PORT)
& $env:QCP_PY tools\ui-ux-pro-max\scripts\search.py "<query>" --domain ux      # UX წესი (DESIGN.md → ინსტრუმენტები)
node tools\hallmark\scripts\sloplint.mjs <შაბლონები> app\static\css\app.css --scope app   # ვიზუალის აუდიტი (Node)
```

## ამოცანის ციკლი

| # | ვინ | რა | სტატუსი ფაილის თავში |
|---|---|---|---|
| 1 | lead | `docs/tasks/T-NNN-<სახელი>.md` შაბლონიდან (`docs/tasks/_template.md`): ნაწილი 1 „ბრიფი“; ხაზი `docs/TASKS.md`-ში; push main | 📝 ბრიფი |
| 2 | qa | ნაწილი 2 „პრომპტი შემსრულებლისთვის“; push main | ✍️ პრომპტი მზადაა |
| 3 | ui / backend | `git fetch; git switch -c <როლი>/T-NNN-<სახელი> origin/main` → ნაწილები 1–2 → `pytest -q` → commit → `git push -u origin <ბრენჩი>` | (ფაილს არ ეხება) |
| 4 | qa | ბრენჩის ტესტი → ნაწილი 3 „ტესტის ოქმი“; push main | 👀 ჩასაბარებელი ან ↩ დაბრუნდა |
| 5 | lead | ჩეკლისტები (`docs/team/checklists/`) → ნაწილი 4 „ჩაბარება“ → merge და push | ✅ ჩაბარდა ან ↩ დაბრუნდა |

უახლესი ამოცანები ნებისმიერი ადგილიდან: `git fetch; git show origin/main:docs/TASKS.md` და `git show origin/main:docs/tasks/<ფაილი>`.
commit-ის აღწერის პირველი ხაზი: `T-NNN: <რა გაკეთდა>`. PR სურვილისამებრ (`.github/pull_request_template.md`).
