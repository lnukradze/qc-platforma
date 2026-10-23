---
name: qc-design
description: "QC პლატფორმის დიზაინი „იზოხაზი“: გვერდების აწყობა და დახვეწა (app/templates, app/static), UX და ხელმისაწვდომობის წესები (UI UX Pro Max), ვიზუალის აუდიტი (Hallmark). Use for any UI work or visual review in this repo — templates, CSS, JS, layout, colour, typography, mobile, dark theme, accessibility."
---

# qc-design — დიზაინის სამუშაო ამ პროექტში

1. **ჯერ `DESIGN.md`** (რეპოს ძირში). ის ყველაფერს სჯობს, მათ შორის ქვემოთ ჩამოთვლილ ინსტრუმენტებს.

2. **UX წესი — UI UX Pro Max** (`tools/ui-ux-pro-max/`, უცვლელი ასლი):
   - ძებნა (2–5 სიტყვა, ერთი თემა):
     `& $env:QCP_PY tools\ui-ux-pro-max\scripts\search.py "<query>" --domain <ux|chart|typography|color|icons> -n 3`
     (`$env:QCP_PY` თუ არ არის — მთავარი საქაღალდის `.venv\Scripts\python.exe`).
   - სრული წესები: `tools/ui-ux-pro-max/references/quick-reference.md`; ჩაბარებამდე — `references/pro-rules.md`.
   - **არა:** `--design-system`, `--persist`, `--stack`. ჩვენი სტეკი (Jinja2 + HTMX + საკუთარი CSS) მის ბაზაში არ არის,
     დიზაინის სისტემა კი უკვე გვაქვს. `tools/ui-ux-pro-max/SKILL.md`-ის „Step 2“ ჩვენთან არ მოქმედებს.
   - შედეგი რეკომენდაციაა: წესის აზრი — კი; Tailwind-ის კლასები — არა (ჩვენი `app.css`).

3. **აუდიტი — Hallmark** (`tools/hallmark/`, მხოლოდ შემოწმების ნაწილი):
   - `node tools\hallmark\scripts\sloplint.mjs <შაბლონ(ებ)ი> app\static\css\app.css --scope app` — ყოველთვის `app.css`-თან ერთად.
   - Node არ არის → გამოტოვე და ოქმში დაწერე: „Hallmark — Node არ არის“.
   - ანგარიშია: FAIL / REFLEX / WARN → შენიშვნა ამოცანის ფაილში. თავისით არაფერს ასწორებ; მიღებული გამონაკლისები `DESIGN.md`-შია.
   - `tools/hallmark/SKILL.md`-ის აწყობის ნაწილი (თემები, `redesign`, ფოტოები, სურათების გენერაცია) ჩვენთან არ გამოიყენება.

4. **შედეგის შემოწმება** — `docs/team/checklists/visual.md`.
