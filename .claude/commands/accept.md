---
description: ამოცანის ჩაბარება (lead) — უსაფრთხოება, ვიზუალი, merge
argument-hint: T-NNN
---
შენ ხარ lead (`docs/team/roles/lead.md`). ჩასაბარებელია: **$ARGUMENTS**

1. `git fetch --prune`; წაიკითხე ამოცანის ფაილი origin/main-იდან (`git show origin/main:docs/tasks/<ფაილი>`).
   თუ ნაწილი 3 არ არის, ან დასკვნა „უბრუნდება შემსრულებელს“ — შეჩერდი და ლუკას უთხარი.
2. ბრენჩი ამოცანის ფაილშია. `git diff --stat origin/main...origin/<ბრენჩი>` და სრული diff:
   მხოლოდ შემსრულებლის ზონა? ბრიფის ფარგლებში? (ამოცანის ფაილის ცვლილება qa-ს ნაწილებში — ნორმაა.)
3. შესამოწმებლად ცალკე საქაღალდე — მთავარ საქაღალდეს და ლუკას `run.bat`-ს არ ეხება:
   - `git worktree add --detach ..\qc-platforma-review origin/<ბრენჩი>`
     (უკვე არსებობს → `git -C ..\qc-platforma-review switch --detach origin/<ბრენჩი>`);
   - იქ, ამ გარემოთი: `$env:QCP_DATA_DIR = "<მთავარი>\data"; $env:QCP_PORT = "8209"`,
     Python — `"<მთავარი>\.venv\Scripts\python.exe"`: `-m pytest -q`, შემდეგ `scripts\run_local.py --no-browser` (ფონზე)
     და `scripts\smoke_pages.py`.
4. `docs/team/checklists/security.md` — სათითაოდ, diff-ის მიხედვით.
5. `docs/team/checklists/visual.md` — ბრაუზერში http://127.0.0.1:8209 (თუ ბრაუზერის ინსტრუმენტი გაქვს): 1366px და 390px,
   ღია და მუქი თემა, კონსოლი. Hallmark — `DESIGN.md` → ინსტრუმენტები.
6. ლუკას მოკლედ აჩვენე შედეგი და ჰკითხე: ჩავიბარო?
   - ✅ → ნაწილი 4 და სტატუსი „✅ ჩაბარდა“; `docs/TASKS.md`-ში ხაზი „დასრულებულში“;
     `git merge --no-ff origin/<ბრენჩი> -m "T-NNN: <სათაური>"` → `pytest -q` → push main → `git push origin --delete <ბრენჩი>`.
   - ↩ → ნაწილი 4: მიზეზი და რა გასწორდეს; სტატუსი „↩ დაბრუნდა“ → push main.
     ლუკას მიეცი ტექსტი სალომესთვის: „<შემსრულებელი> — T-NNN დაბრუნდა, გაასწორე ნაწილი 4-ის მიხედვით“.
7. სერვერი გააჩერე. `qc-platforma-review` დატოვე შემდეგი ჩაბარებისთვის.
