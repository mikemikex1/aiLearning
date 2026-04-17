# git_sync.ps1 - one command for stage + commit + push
# Usage examples:
#   .\git_sync.ps1 -Type add -Action "search page ui update"
#   .\git_sync.ps1 -Type edit -Action "update docs" -Files README.md,A_BROWSER_RAG_VALIDATION_HANDOVER.md
#   .\git_sync.ps1 -Type debug -Action "fix api timeout handling" -NoPush

param(
    [Parameter(Mandatory = $false)]
    [ValidateSet("debug", "add", "edit", "docs", "chore", "test", "perf", "refactor")]
    [string]$Type = "edit",

    [Parameter(Mandatory = $true)]
    [string]$Action,

    [Parameter(Mandatory = $false)]
    [string[]]$Files = @(),

    [Parameter(Mandatory = $false)]
    [string]$Branch = "main",

    [switch]$IncludeAll,
    [switch]$NoPush
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".git")) {
    throw "This folder is not a git repository: $PSScriptRoot"
}

function Run-Git {
    param([string[]]$GitArgs)
    Write-Host ("git " + ($GitArgs -join " "))
    & git @GitArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Git command failed: git $($GitArgs -join ' ')"
    }
}

function Normalize-Message {
    param(
        [string]$Text,
        [string]$MessageType
    )
    $trimmed = ($Text | ForEach-Object { $_.Trim() })
    if (-not $trimmed) {
        throw "Action cannot be empty."
    }
    if ($trimmed -match "^([a-z]+):\s+") {
        $prefix = $Matches[1]
        $allowed = @("debug", "add", "edit", "docs", "chore", "test", "perf", "refactor")
        if ($allowed -contains $prefix) {
            return $trimmed
        }
        throw "Unsupported commit type '$prefix' in Action. Use one of: $($allowed -join ', ')"
    }
    return "$MessageType" + ": " + "$trimmed"
}

Run-Git -GitArgs @("remote", "get-url", "origin")

if ($Files.Count -gt 0) {
    Write-Host "==> Stage selected files"
    Run-Git -GitArgs (@("add", "--") + $Files)
}
elseif ($IncludeAll) {
    Write-Host "==> Stage all changes"
    Run-Git -GitArgs @("add", "-A")
}
else {
    Write-Host "==> Stage changes (exclude data/.venv/__pycache__ by default)"
    Run-Git -GitArgs @("add", "-A", "--", ".", ":(exclude)data/", ":(exclude).venv/", ":(exclude)__pycache__/")
}

$status = git status --porcelain
if (-not $status) {
    Write-Host "Nothing to commit."
    exit 0
}

$message = Normalize-Message -Text $Action -MessageType $Type
Write-Host "==> Commit: $message"
Run-Git -GitArgs @("commit", "-m", $message)

if ($NoPush) {
    Write-Host "==> Skip push (-NoPush)"
    exit 0
}

Write-Host "==> Push to origin/$Branch"
Run-Git -GitArgs @("push", "origin", $Branch)
Write-Host "Done."
