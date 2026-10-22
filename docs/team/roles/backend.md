# როლი: backend — ლოგიკა, მონაცემი, API

ვინ: სალომე · Claude #2 · სალომეს კომპიუტერი · worktree `..\qc-platforma-backend` · პორტი 8201

## ზონა

`app/services/`, `app/routes/`, `app/workflow.py`, `app/scope.py`, `app/security.py`, `app/main.py`, `app/db.py`,
`scripts/` (გარდა `smoke_*.py`, ის qa-ს ზონაა).

## წესები

- ყოველი ახალი route ან endpoint ხილვადობის იმავე წესებს ექვემდებარება (`scope.py`), რასაც დანარჩენი.
  რაც ახალ ტესტს საჭიროებს, PR-ში qa-სთვის ჩამოწერე.
- შაბლონებს (`app/templates/`) და `app/static/`-ს არ ეხები. route შაბლონს მონაცემს ზუსტად იმ სახელით გადასცემს,
  რაც ამოცანის „კონტრაქტშია“. თუ ui-ში რამე უნდა შეიცვალოს, PR-ში „ui-სთვის“ ნაწილში დაწერე.
- `models.py`, `domain.py` ან `config.py` თუ შესაცვლელია — შეჩერდი და სალომეს უთხარი. ამას lead ცვლის.
- სამუშაო პროცესის წესები `docs/ARCHITECTURE.md`-შია. ახალს არ იგონებ.
- ცვლილების შემდეგ `& $env:QCP_PY -m pytest -q` უნდა გადიოდეს.
