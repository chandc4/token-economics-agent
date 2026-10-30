param([string]$RepoDir)

if (-not (Test-Path "$RepoDir\calculator.py")) {
    Write-Error "calculator.py not found in $RepoDir"
    exit 1
}

# Run unit tests inside the repo dir
$proc = Start-Process python -ArgumentList "-m", "unittest", "test_calculator.py" -WorkingDirectory $RepoDir -NoNewWindow -PassThru -Wait
if ($proc.ExitCode -eq 0) {
    Write-Host "Judge T01: PASSED"
    exit 0
} else {
    Write-Host "Judge T01: FAILED"
    exit 1
}
