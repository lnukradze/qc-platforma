# tools/ — მესამე მხარის დიზაინის ინსტრუმენტები (შემოწმებული ასლები)

ორივე უცვლელი ასლია ფიქსირებული commit-იდან და თავისით არ განახლდება. განახლება მხოლოდ lead-ს შეუძლია:
ახალი ვერსიის წაკითხვა და შემოწმება, მერე ჩანაცვლება და ამ ფაილის განახლება.
როგორ ვიყენებთ — `DESIGN.md` → „ინსტრუმენტები“ და სკილი `.claude/skills/qc-design/`.

| | UI UX Pro Max | Hallmark |
|---|---|---|
| **წყარო** | https://github.com/nextlevelbuilder/ui-ux-pro-max-skill | https://github.com/nutlope/hallmark |
| **commit** | `28327f2f214d31bbd7555ed0c012a5df6484ed96` (2026-10-23) | `7ec868225c6caa040558c321ee0fefa0e73f83a8` (2026-10-22) |
| **ლიცენზია** | MIT (`ui-ux-pro-max/LICENSE`) | MIT (`hallmark/LICENSE`) |
| **რა შედის** | `.claude/skills/ui-ux-pro-max/`: `SKILL.md`, `data/`, `references/`, `scripts/*.py` | `skills/hallmark/`: `SKILL.md`, `references/*.md`, `scripts/sloplint.mjs`, `sloplint-render.mjs`, `capture.mjs` |
| **რა არ შედის** | `scripts/tests/`; რეპოს სხვა სკილები (brand, slides, design, ui-styling — Tailwind/shadcn-ზე); npm CLI | `imagegen.mjs` — სურათებს გარე სერვისში ქმნის (Together AI); `install*.mjs`, `lint-hook.mjs` — Claude-ის პარამეტრებში hook-ს წერს; `theme.mjs`, `picture.mjs`, `photos.json` — თემები და ფოტოები გარე სერვერიდან; `agents/openai.yaml` — Codex-ის ავტომატური გამოძახება; `references/` ქვესაქაღალდეები (themes, genres, macrostructures) |

## შემოწმება (2026-10-23, lead)

- **UI UX Pro Max:** სკრიპტები მხოლოდ Python-ის სტანდარტულ ბიბლიოთეკას იყენებს: ქსელი, სხვა პროგრამის გაშვება, `eval` — არ არის.
  ფაილს წერს მხოლოდ `--persist` (ჩვენთან აკრძალულია). ძებნა შემოწმდა `.venv`-ის Python-ით.
- **Hallmark:** `sloplint.mjs` მხოლოდ Node-ის ჩაშენებულ მოდულებს იყენებს, ქსელის გარეშე; წერს მხოლოდ `.hallmark/`-ში (git-ში არ შედის).
  `--render` და `capture.mjs` puppeteer-core-ს და Chrome-ს საჭიროებს (`npm root -g`-ით პოულობს) — ცალკე დასაყენებელია.
  შემოწმდა Node 24-ით `app/templates/home.html` + `app/static/css/app.css`-ზე.
- ორივე ჩვენს კოდს არ ცვლის — მხოლოდ ანგარიშს ან რეკომენდაციას იძლევა.
