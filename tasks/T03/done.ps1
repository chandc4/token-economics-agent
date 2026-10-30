param([string]$RepoDir)

if (-not (Test-Path "$RepoDir\cache.py")) {
    Write-Error "cache.py not found in $RepoDir"
    exit 1
}

$proc = Start-Process python -ArgumentList "-m", "unittest", "test_cache.py" -WorkingDirectory $RepoDir -NoNewWindow -PassThru -Wait
if ($proc.ExitCode -eq 0) {
    Write-Host "Judge T03: PASSED"
    exit 0
} else {
    Write-Host "Judge T03: FAILED"
    exit 1
}
