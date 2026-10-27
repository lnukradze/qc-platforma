# Start one AI agent of the team in its own git worktree.
# ASCII only: Windows PowerShell 5.1 misreads UTF-8 files without BOM.
#
#   scripts\team\agent.bat lead
#   scripts\team\agent.bat ui      salome-1
#   scripts\team\agent.bat backend salome-2
#   scripts\team\agent.bat qa
# Or in VS Code: Terminal > Run Task > (.vscode\tasks.json).
#
# Account: a Claude role with an account name gets its own login folder
# (%USERPROFILE%\.claude-profiles\<name>); the first run needs /login there.
# No account name = the normal Claude login of this Windows user.
# qa runs Codex (ChatGPT login, one account).
# No install rights needed: if claude / codex are not on PATH, the copies
# bundled with the VS Code extensions (Claude Code, Codex) are used.
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('lead', 'backend', 'ui', 'qa')]
    [string]$Role,
    [string]$Account = ''
)
$ErrorActionPreference = 'Stop'

# Main folder = the one that owns .git, even when started from a worktree
$common = git -C $PSScriptRoot rev-parse --path-format=absolute --git-common-dir
if ($LASTEXITCODE -ne 0) { throw 'Not a git repository - run "git init" / "git clone" first.' }
$main = Split-Path $common -Parent
$ports = @{ lead = 8200; backend = 8201; ui = 8202; qa = 8203 }

# lead works in the main folder; every other role gets a sibling worktree
if ($Role -eq 'lead') {
    $dir = $main
} else {
    $dir = Join-Path (Split-Path $main -Parent) ((Split-Path $main -Leaf) + '-' + $Role)
    if (-not (Test-Path $dir)) {
        $base = 'main'
        if (git -C $main remote) {
            git -C $main fetch origin
            $base = 'origin/main'
        }
        git -C $main worktree add --detach $dir $base
        if ($LASTEXITCODE -ne 0) { throw "Could not create worktree $dir" }
    }
}

# Worktrees share the main folder's Python env.
# AI agents ALWAYS use the shared demo data (fictional only, T-006) - never the real data\,
# even when data\platform.db exists. Real data is checked by people (run.bat).
$env:QCP_PY = Join-Path $main '.venv\Scripts\python.exe'
$demo = Join-Path (Split-Path $main -Parent) 'qc-demo-data'
$env:QCP_DATA_DIR = $demo
$env:QCP_DISTRIBUTOR_DB = Join-Path $demo 'distributor.sqlite'
$env:QCP_QC_WORKBOOK = Join-Path $demo 'no-workbook.xlsx'
$env:QCP_DEMO_LOGIN = '1'
# app\config.py: agent mode - any non-demo data path is replaced by the demo (Codex has no CLAUDECODE=1)
$env:QCP_AGENT = '1'
# Inherited settings must not lead outside the demo: database URL, mail, Google login
foreach ($name in 'QCP_DATABASE_URL', 'QCP_SESSION_SECRET', 'QCP_BASE_URL', 'QCP_SMTP_HOST',
                  'QCP_SMTP_USER', 'QCP_SMTP_PASSWORD', 'QCP_GOOGLE_CLIENT_ID', 'QCP_GOOGLE_CLIENT_SECRET') {
    Remove-Item "Env:$name" -ErrorAction SilentlyContinue
}
$env:QCP_PORT = $ports[$Role]
if (-not (Test-Path $env:QCP_PY)) { Write-Warning "No .venv in $main - run setup.bat there first." }
Write-Host "DEMO data: $demo"
if (-not (Test-Path (Join-Path $demo 'platform.db'))) {
    Write-Host 'No demo database yet. Create it (fictional data only):'
    Write-Host '  & $env:QCP_PY scripts\build_demo_db.py'
}

if ($Account -and $Role -ne 'qa') {
    $env:CLAUDE_CONFIG_DIR = Join-Path $env:USERPROFILE ('.claude-profiles\' + $Account)
    New-Item -ItemType Directory -Force $env:CLAUDE_CONFIG_DIR | Out-Null
}

# The installed command if there is one, else the newest copy inside a VS Code extension
function Find-Agent([string]$Name, [string]$ExtensionPattern) {
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $exe = Get-ChildItem (Join-Path $env:USERPROFILE '.vscode\extensions') -Directory -Filter $ExtensionPattern -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        ForEach-Object { Get-ChildItem $_.FullName -Recurse -Filter "$Name.exe" -ErrorAction SilentlyContinue } |
        Select-Object -First 1
    if ($exe) { return $exe.FullName }
    throw "$Name not found - install its VS Code extension ($ExtensionPattern) or the $Name CLI."
}
if ($Role -eq 'qa') { $agent = Find-Agent 'codex' 'openai.chatgpt-*' }
else { $agent = Find-Agent 'claude' 'anthropic.claude-code-*' }

$prompt = "Session role: $Role. Read AGENTS.md and docs/team/roles/$Role.md (ui and qa: also DESIGN.md) and follow them for the whole session. " +
          "Then run git fetch, read the task list (git show origin/main:docs/TASKS.md, or docs/TASKS.md if there is no origin) " +
          "and the status line of the open task files in docs/tasks/, " +
          "and tell me in Georgian, in one or two sentences, your role and the open tasks for this role."

Set-Location $dir
$Host.UI.RawUI.WindowTitle = "QC agent: $Role (port $($env:QCP_PORT))"
Write-Host "Role: $Role | folder: $dir | port: $($env:QCP_PORT) | account: $(if ($Account) { $Account } else { 'default' })"
& $agent $prompt
