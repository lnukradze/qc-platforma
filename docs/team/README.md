# გუნდი: ორი ადამიანი, ოთხი AI აგენტი, ორი კომპიუტერი

| კომპიუტერი | ადამიანი | აგენტი | როლი | საქაღალდე | პორტი |
|---|---|---|---|---|---|
| ლუკასი | ლუკა | Claude #1 | **lead** — გეგმავს, ანაწილებს, ამოწმებს, აერთიანებს | `qc-platforma` | 8200 |
| სალომესი | სალომე | Claude #2 | **backend** — ლოგიკა, მონაცემი, API | `qc-platforma-backend` | 8201 |
| სალომესი | სალომე | Claude #3 | **ui** — შაბლონები, CSS, JS | `qc-platforma-ui` | 8202 |
| სალომესი | სალომე | GPT (Codex) | **qa** — ტესტები, PR-ების რევიუ | `qc-platforma-qa` | 8203 |

ორ კომპიუტერს GitHub-ის პრივატული რეპოზიტორია აკავშირებს. სალომეს კომპიუტერზე სამი აგენტი ერთ clone-ს იყენებს,
მაგრამ თითოეულს ცალკე საქაღალდე აქვს (git worktree), ამიტომ ერთმანეთის ფაილებს არ ცვლიან.
ვინ რას ცვლის და ვინ აერთიანებს — `AGENTS.md`. როლების დეტალები — `docs/team/roles/`.

## 1. ლუკა: რეპოზიტორიის შექმნა (ერთხელ)

1. GitHub-ზე: **New repository** → სახელი `qc-platforma` → **Private** → README/.gitignore **არ** დაამატოთ → Create.
2. Settings → Collaborators → სალომეს GitHub ანგარიშის დამატება.
3. ლუკას კომპიუტერზე:
   ```powershell
   cd C:\Users\LNUKRADZE\Desktop\apisaiti\qc-platforma
   git config --global user.name  "<სახელი გვარი>"
   git config --global user.email "<GitHub-ის ელფოსტა>"
   git add .
   git status          # დარწმუნდით, რომ data\, .venv\ და *.xlsx სიაში არ არის
   git commit -m "პროტოტიპი v0.2.0 + გუნდის წესები"
   git remote add origin https://github.com/<ანგარიში>/qc-platforma.git
   git push -u origin main
   ```

## 2. სალომე: დაყენება (ერთხელ)

1. დასაყენებელი: Git, [uv](https://docs.astral.sh/uv/) (`winget install astral-sh.uv`), Node.js, შემდეგ:
   ```powershell
   npm install -g @anthropic-ai/claude-code @openai/codex
   ```
2. clone-ი **იმავე სტრუქტურით**, რაც ლუკასთანაა (`Desktop\apisaiti\qc-platforma`).
   მონაცემის წყაროების ნაგულისხმევი მისამართები ამ სტრუქტურას ეყრდნობა.
   ```powershell
   cd $env:USERPROFILE\Desktop\apisaiti
   git clone https://github.com/<ანგარიში>/qc-platforma.git
   ```
3. **მონაცემი git-ით არ გადადის.** `setup.bat`-ს სჭირდება:
   - `Desktop\კონტროლ;ის სტატისტიკა\dashboard\sheet_config.json`
   - `Desktop\კონტროლ;ის სტატისტიკა\QC სამუშაო.xlsx`
   - `Desktop\apisaiti\dzveli masalebi da saitebi\NAPR_Distributor\` (`config.json`, `napr_data.sqlite`)

   ამ ფაილებში პირადი მონაცემი და წვდომის გასაღებებია. გადაიტანეთ ისე, როგორც სამსახურში დაშვებულია.
   ტესტებს (`pytest`) ეს მონაცემი არ სჭირდება.
4. `qc-platforma\setup.bat` — ერთხელ.

## 3. აგენტების გაშვება

სალომე — სამი ცალკე ფანჯარა, თითოეულში ერთი ბრძანება (`qc-platforma`-დან):

| ფანჯარა | ბრძანება | პირველ გაშვებაზე |
|---|---|---|
| 1 | `scripts\team\agent.bat backend salome-1` | `/login` → Claude ანგარიში #1 |
| 2 | `scripts\team\agent.bat ui salome-2` | `/login` → Claude ანგარიში #2 |
| 3 | `scripts\team\agent.bat qa` | Sign in with ChatGPT |
სკრიპტი worktree-ს თავად ქმნის. ყოველ Claude ანგარიშს ცალკე შესვლის საქაღალდე აქვს
(`%USERPROFILE%\.claude-profiles\<სახელი>`), ამიტომ ორი ანგარიში ერთ კომპიუტერზე ერთმანეთში არ ირევა.
თუ შესვლები მაინც აირია, ყველაზე საიმედოა ცალკე Windows მომხმარებელი.

ლუკა — VS Code-ში `qc-platforma`-ს გახსნა → Claude-ის პანელში `/role lead`.
ან ტერმინალიდან: `scripts\team\agent.bat lead` (საჭიროა `claude` CLI).

`/clear`-ის შემდეგ Claude-ს როლი ავიწყდება — `/role backend` / `/role ui` / `/role lead`.

## 4. ყოველდღიური ციკლი

| # | ვინ | რა |
|---|---|---|
| 1 | ლუკა + lead | ამოცანას `docs/TASKS.md`-ში წერენ (როლი, ფაილები, დასრულების პირობა, კონტრაქტი) → push main-ში |
| 2 | სალომე | შესაბამის აგენტს ეუბნება: „აიღე T-005“ |
| 3 | backend / ui | ბრენჩი `ui/T-005-…` → მუშაობა → `pytest -q` → commit → push |
| 4 | სალომე | GitHub-ზე **Compare & pull request** (შაბლონი თავისით ივსება) |
| 5 | qa | „გადახედე ბრენჩს `ui/T-005-…`“ → შენიშვნების სია → სალომე PR-ში წერს |
| 6 | ლუკა + lead | ამოწმებს → merge → `TASKS.md`-ში ✅ |

ერთდროულად შეიძლება იმუშაონ backend-მა და ui-მ სხვადასხვა ამოცანაზე, qa-მ კი წინა PR-ს გადახედოს.

## შენიშვნები

- **იერარქია შეთანხმებაა და არა აკრძალვა.** უფასო GitHub-ის პრივატულ რეპოზე main-ის დაცვა (branch protection) არ მუშაობს.
  თუ გინდათ, რომ GitHub-მა თავად შეზღუდოს main-ში პირდაპირი ჩაწერა, რეპოს მფლობელს GitHub Pro სჭირდება.
- **ლიმიტები.** lead-ის ანგარიში ერთია და სხვა პროექტებზეც იხარჯება — lead გეგმავს, კოდს backend და ui წერენ.
  ამოცანებს შორის `/clear`.
- **სურვილისამებრ:** `winget install GitHub.cli` → `gh auth login`. ამის შემდეგ აგენტებს PR-ის გახსნა თვითონ შეუძლიათ (`gh pr create`).
