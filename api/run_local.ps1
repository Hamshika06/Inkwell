<#
Start Inkwell locally (API + web page) on Windows:
    powershell -ExecutionPolicy Bypass -File api\run_local.ps1            # all three models
    powershell -ExecutionPolicy Bypass -File api\run_local.ps1 -SvmOnly   # skip torch (smaller, faster install)
Creates api\.venv with Python 3.10 (via uv, conda, or the py launcher), installs the pinned
packages, and serves everything at http://127.0.0.1:7860. The system Python version does not matter.
#>
param([switch]$SvmOnly, [int]$Port = 7860)
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$Venv = Join-Path $PSScriptRoot ".venv"
$Requirements = Join-Path $PSScriptRoot $(if ($SvmOnly) { "requirements.txt" } else { "requirements-encoders.txt" })
$HasUv = [bool](Get-Command uv -ErrorAction SilentlyContinue)

function Find-VenvPython {
    foreach ($candidate in @("$Venv\Scripts\python.exe", "$Venv\python.exe")) {  # venv/uv layout, conda layout
        if (Test-Path $candidate) { return $candidate }
    }
}

$Python = Find-VenvPython
if (-not $Python) {
    Write-Host "Creating $Venv with Python 3.10..."
    if ($HasUv) {
        uv venv --python 3.10 $Venv              # uv downloads Python 3.10 if it is missing
    } elseif (Get-Command conda -ErrorAction SilentlyContinue) {
        conda create -y -p $Venv python=3.10
    } else {
        $version = @("3.10", "3.11") | Where-Object { & py "-$_" -c "pass" 2>$null; $LASTEXITCODE -eq 0 } | Select-Object -First 1
        if (-not $version) { throw "Need Python 3.10 or 3.11 (numpy 1.26.4 cannot install on 3.13+). Install uv (https://docs.astral.sh/uv/) or Python 3.10." }
        & py "-$version" -m venv $Venv
    }
    if ($LASTEXITCODE -ne 0) { throw "Could not create $Venv" }
    $Python = Find-VenvPython
}

$version = & $Python -c "import sys; print('%d.%d' % sys.version_info[:2])"
if ($version -notin @("3.10", "3.11")) { throw "$Venv uses Python $version; delete the folder and rerun (needs 3.10 or 3.11)." }

Write-Host "Installing $(Split-Path $Requirements -Leaf) into Python $version..."
if ($HasUv) {
    uv pip install --python $Python -r $Requirements --index-strategy unsafe-best-match
} else {
    & $Python -m pip install --disable-pip-version-check -r $Requirements
}
if ($LASTEXITCODE -ne 0) { throw "Package installation failed" }

Write-Host ""
Write-Host "Inkwell is starting. Open http://127.0.0.1:$Port  (Ctrl+C to stop)" -ForegroundColor Green
Set-Location $Root
& $Python -m uvicorn api.app:app --host 127.0.0.1 --port $Port
