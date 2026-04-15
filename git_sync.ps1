# git_sync.ps1 — one-shot commit + push helper for AILearning
# Usage: .\git_sync.ps1 "your commit message"

param(
    [Parameter(Mandatory=$false)]
    [string]$Message = "chore: sync from Claude session"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path .git)) {
    Write-Host "==> git init (first run)"
    git init -b main
    git remote add origin git@github.com:mikemikex1/aiLearning.git
}

# Ensure remote is correct
$remote = git remote get-url origin 2>$null
if ($remote -ne "git@github.com:mikemikex1/aiLearning.git") {
    git remote set-url origin git@github.com:mikemikex1/aiLearning.git
}

Write-Host "==> Staging changes"
git add -A

$status = git status --porcelain
if (-not $status) {
    Write-Host "Nothing to commit."
    exit 0
}

Write-Host "==> Committing"
git commit -m $Message

Write-Host "==> Pushing to origin/main"
git push -u origin main
Write-Host "✓ Done."
