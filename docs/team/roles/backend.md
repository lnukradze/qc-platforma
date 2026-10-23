# როლი: backend — ფუნქციონალი და თავსებადობა

ვინ: სალომე · სალომეს მეორე Claude (`salome-2`) · სალომეს კომპიუტერი · worktree `..\qc-platforma-backend` · პორტი 8201

## ზონა

`app/services/`, `app/routes/`, `app/workflow.py`, `app/scope.py`, `app/security.py`, `app/main.py`, `app/db.py`,
`scripts/` (გარდა `smoke_*.py` — ის qa-ს ზონაა).

## ფუნქციონალი

- ყოველი ახალი route ან endpoint ხილვადობის იმავე წესებს ექვემდებარება (`scope.py`). ყოველი POST — CSRF-ით (`security.py`).
- შაბლონებს და `app/static/`-ს არ ეხები. route შაბლონს მონაცემს ზუსტად კონტრაქტის სახელით გადასცემს.
- `models.py`, `domain.py` ან `config.py` თუ შესაცვლელია — შეჩერდი და სალომეს უთხარი. ამას lead ცვლის.
- სამუშაო პროცესის წესები `docs/ARCHITECTURE.md`-შია. ახალს არ იგონებ.

## თავსებადობა — შენი პასუხისმგებლობა

- **ტელეფონი:** ველისა და ამზომველის გვერდები 360–414px სიგანეზე (ფორმები, ღილაკები, HTMX ქმედებები).
  ვიზუალის ხარვეზს შენ არ ასწორებ — ჩაწერე და lead მას ui-ს ამოცანად აქცევს.
- **ბრაუზერები:** Chrome და Edge (სამსახურის ძირითადი). JS-ის ახალი შესაძლებლობა — მხარდაჭერის შემოწმებით.
- **PostgreSQL:** აპლიკაციის კოდში SQLite-ის სპეციფიკური SQL არა — მხოლოდ SQLAlchemy-ის ტიპები და ფუნქციები.
  გამონაკლისი: `app/services/distribution/source.py` (განაწილების წყარო ცალკე SQLite ფაილია).
- **API:** `/docs` (OpenAPI) — არსებულ endpoint-ს არ არღვევ; ცვლილება მხოლოდ ამოცანაში ჩაწერილი.
- **სიჩქარე:** 44 ათასი ოქმი — სია და სტატისტიკა არ უნდა ნელდებოდეს (N+1 მოთხოვნები, ინდექსები).

## „აიღე T-NNN“

1. `git fetch; git switch -c backend/T-NNN-<სახელი> origin/main` → წაიკითხე `docs/tasks/T-NNN-*.md`, ნაწილები 1 და 2.
2. გააკეთე → `& $env:QCP_PY -m pytest -q` გადის; გაშვებულ სერვერზე (8201) `& $env:QCP_PY scripts\smoke_pages.py`.
3. commit (`T-NNN: <რა გაკეთდა>`) → `git push -u origin backend/T-NNN-<სახელი>` → სალომეს მოკლე ანგარიში.
