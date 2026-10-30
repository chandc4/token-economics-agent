param([string]$RepoDir)

if (-not (Test-Path "$RepoDir\models.py") -or -not (Test-Path "$RepoDir\serializer.py")) {
    Write-Error "Required files not found in $RepoDir"
    exit 1
}

$proc = Start-Process python -ArgumentList "-m", "unittest", "test_user_service.py" -WorkingDirectory $RepoDir -NoNewWindow -PassThru -Wait
if ($proc.ExitCode -eq 0) {
    Write-Host "Judge T02: PASSED"
    exit 0
} else {
    Write-Host "Judge T02: FAILED"
    exit 1
}
