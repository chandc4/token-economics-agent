param(
    [string]$Command = "ui",
    [string]$Platform = "opencode",
    [string]$Output = "",
    [switch]$Force
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppPy = Join-Path $ScriptDir "tools\te_agent_app.py"
$InitPy = Join-Path $ScriptDir "tools\te_init.py"
$SentinelPy = Join-Path $ScriptDir "tools\te_sentinel.py"
$DoctorPy = Join-Path $ScriptDir "tools\te_doctor.py"
$CleanPy = Join-Path $ScriptDir "tools\te_clean.py"

if ($Command -eq "ui") {
    python $AppPy ui
} elseif ($Command -eq "init") {
    $argsList = @($InitPy, "--platform", $Platform)
    if ($Output) { $argsList += @("--output", $Output) }
    if ($Force) { $argsList += @("--force") }
    python @argsList
} elseif ($Command -eq "audit") {
    python $AppPy audit
} elseif ($Command -eq "watch" -or $Command -eq "sentinel") {
    python $SentinelPy
} elseif ($Command -eq "doctor") {
    python $DoctorPy
} elseif ($Command -eq "clean") {
    python $CleanPy
} elseif ($Command -eq "test") {
    python -m unittest discover -s tests -p "test_*.py" -v
} else {
    Write-Host "TE-Agent Commands:" -ForegroundColor Cyan
    Write-Host "  .\te.ps1 ui                     - Launch zero-dependency web dashboard"
    Write-Host "  .\te.ps1 init [-Platform] [-Output] [-Force] - Generate canonical lean contract"
    Write-Host "  .\te.ps1 audit                  - Audit recent conversation token metrics"
    Write-Host "  .\te.ps1 watch                  - Launch live real-time token-economics sentinel"
    Write-Host "  .\te.ps1 doctor                 - Validate environment, binaries, DB, and configs"
    Write-Host "  .\te.ps1 clean                  - Safely clean up accumulated benchmark runs"
    Write-Host "  .\te.ps1 test                   - Run regression & statistical test suite"
}
