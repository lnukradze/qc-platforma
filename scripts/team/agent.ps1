# Start one AI agent of the team in its own git worktree.
# ASCII only: Windows PowerShell 5.1 misreads UTF-8 files without BOM.
#
#   scripts\team\agent.bat lead
#   scripts\team\agent.bat backend salome-1
#   scripts\team\agent.bat ui      salome-2
#   scripts\team\agent.bat qa
#
# Account: a Claude role with an account name gets its own login folder
# (%USERPROFILE%\.claude-profiles\<name>); the first run needs /login there.
# No account name = the normal Claude login of this Windows user.
# qa runs Codex (ChatGPT login, one account).
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

# Worktrees share the main folder's Python env and local data (data\ is never in git)
$env:QCP_PY = Join-Path $main '.venv\Scripts\python.exe'
$env:QCP_DATA_DIR = Join-Path $main 'data'
$env:QCP_PORT = $ports[$Role]
if (-not (Test-Path $env:QCP_PY)) { Write-Warning "No .venv in $main - run setup.bat there first." }

if ($Account -and $Role -ne 'qa') {
    $env:CLAUDE_CONFIG_DIR = Join-Path $env:USERPROFILE ('.claude-profiles\' + $Account)
    New-Item -ItemType Directory -Force $env:CLAUDE_CONFIG_DIR | Out-Null
}

$prompt = "Session role: $Role. Read AGENTS.md and docs/team/roles/$Role.md and follow them for the whole session. " +
          "Then run git fetch, read the latest tasks (git show origin/main:docs/TASKS.md, or docs/TASKS.md if there is no origin) " +
          "and tell me in Georgian, in one or two sentences, your role and the open tasks for this role."

Set-Location $dir
$Host.UI.RawUI.WindowTitle = "QC agent: $Role (port $($env:QCP_PORT))"
Write-Host "Role: $Role | folder: $dir | port: $($env:QCP_PORT) | account: $(if ($Account) { $Account } else { 'default' })"
if ($Role -eq 'qa') { codex $prompt } else { claude $prompt }
