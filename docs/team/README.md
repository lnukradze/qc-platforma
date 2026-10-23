# გუნდი: ორი ადამიანი, ოთხი AI აგენტი, ორი კომპიუტერი

| კომპიუტერი | ადამიანი | აგენტი | როლი | საქაღალდე | პორტი |
|---|---|---|---|---|---|
| ლუკასი | ლუკა | ლუკას Claude | **lead** — ამოცანები, უსაფრთხოებისა და ვიზუალის შემოწმება, ჩაბარება | `qc-platforma` | 8200 |
| სალომესი | სალომე | სალომეს Claude (`salome-1`) | **ui** — აწყობა: გვერდები და დიზაინი | `qc-platforma-ui` | 8202 |
| სალომესი | სალომე | სალომეს მეორე Claude (`salome-2`) | **backend** — ფუნქციონალი და თავსებადობა | `qc-platforma-backend` | 8201 |
| სალომესი | სალომე | სალომეს Codex | **qa** — lead-ის მარჯვენა ხელი: პრომპტები და მეორე ტესტი | `qc-platforma-qa` | 8203 |

ორ კომპიუტერს GitHub-ის პრივატული რეპო აკავშირებს: https://github.com/lnukradze/qc-platforma.
სალომეს კომპიუტერზე სამი აგენტი ერთ clone-ს იყენებს, მაგრამ თითოეულს ცალკე საქაღალდე აქვს (git worktree).

- ვინ რას ცვლის და ამოცანის ციკლი — `AGENTS.md`
- დიზაინის წესები — `DESIGN.md`
- **ლუკას გზამკვლევი — `docs/team/LEAD.md`; სალომეს გზამკვლევი — `docs/team/SALOME.md`**
- ჩაბარების ჩეკლისტები — `docs/team/checklists/`

## დაყენება — სალომე (ერთხელ)

1. პროგრამები — ადმინის უფლების გარეშე, მომხმარებლის საქაღალდეში:
   - **VS Code-ის გაფართოებები:** `Claude Code` (Anthropic) და `Codex` (OpenAI). CLI მათ მოყვებათ — `agent.bat` თვითონ პოულობს.
   - **Git** (`git --version`; არ არის → PortableGit ან Git for Windows „Install for me only“).
   - **uv** (`winget install astral-sh.uv`) — Python-ს თვითონ ჩამოტვირთავს.
   - **Node.js** — არასავალდებულო, მხოლოდ Hallmark-ის აუდიტისთვის (`docs/team/SALOME.md`).
2. clone იმავე სტრუქტურით: `Desktop\apisaiti\qc-platforma` — მონაცემის მისამართები ამას ეყრდნობა.
3. **მონაცემი git-ით არ გადადის.** `setup.bat`-ს სჭირდება `sheet_config.json`, `QC სამუშაო.xlsx` და `NAPR_Distributor`-ის ფაილები —
   გადაიტანეთ ისე, როგორც სამსახურში დაშვებულია. ტესტებს (`pytest`) მონაცემი არ სჭირდება.
4. ნაბიჯ-ნაბიჯ, Claude-ის დახმარებით: `QC-setup-salome.md` (ლუკამ გამოგიგზავნა).

## გაშვება

- **სალომე:** VS Code → Terminal → Run Task… → **„სალომე: სამივე აგენტი“** — სამი ტერმინალი, თითო აგენტით.
  ხელით: `scripts\team\agent.bat ui salome-1`, `scripts\team\agent.bat backend salome-2`, `scripts\team\agent.bat qa`.
  პირველ გაშვებაზე: ui → `/login` (ანგარიში #1), backend → `/login` (ანგარიში #2, ბმული **InPrivate** ფანჯარაში), qa → Sign in with ChatGPT.
- **ლუკა:** VS Code-ში `qc-platforma` → Claude-ის პანელი → `/role lead`.
- `/clear`-ის შემდეგ Claude-ს როლი ავიწყდება → `/role ui` / `/role backend` / `/role lead`.

## შენიშვნები

- **იერარქია შეთანხმებაა და არა აკრძალვა.** უფასო GitHub-ის პრივატულ რეპოზე main-ის დაცვა (branch protection) არ მუშაობს;
  ამისთვის რეპოს მფლობელს GitHub Pro სჭირდება.
- **ლიმიტები.** lead-ის ანგარიში ერთია და სხვა პროექტებზეც იხარჯება: lead გეგმავს და ჩაიბარებს, კოდს ui და backend წერენ,
  დეტალურ პრომპტს — qa. ამოცანებს შორის `/clear`.
