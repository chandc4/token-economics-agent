# Sample external judge
param([string]$RepoDir)

Write-Host "Judge checking repo at $RepoDir"
if (Test-Path "$RepoDir") {
    exit 0
} else {
    exit 1
}
