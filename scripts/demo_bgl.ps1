$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$PythonExe = "C:\Users\islam\AppData\Local\Python\pythoncore-3.14-64\python.exe"

function Test-PythonCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command,
        [string[]]$Arguments = @()
    )

    try {
        $output = & $Command @Arguments --version 2>&1
        if ($LASTEXITCODE -eq 0 -and $output -match "Python") {
            return $true
        }
    }
    catch {
        return $false
    }

    return $false
}

if ((Get-Command py -ErrorAction SilentlyContinue) -and (Test-PythonCommand -Command "py" -Arguments @("-3"))) {
    $PythonCommand = "py"
    $PythonArgs = @("-3")
}
elseif ((Get-Command python -ErrorAction SilentlyContinue) -and (Test-PythonCommand -Command "python")) {
    $PythonCommand = "python"
    $PythonArgs = @()
}
elseif ((Test-Path $PythonExe) -and (Test-PythonCommand -Command $PythonExe)) {
    $PythonCommand = $PythonExe
    $PythonArgs = @()
}
else {
    throw "No valid Python executable found. Edit `$PythonExe at the top of this script and set it to the full python.exe path."
}

$PythonVersion = & $PythonCommand @PythonArgs --version 2>&1
Write-Host "Using Python command: $PythonCommand $($PythonArgs -join ' ')"
Write-Host "Python version: $PythonVersion"

function Invoke-Python {
    & $PythonCommand @PythonArgs @args
}

function Show-Step {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    Write-Host ""
    Write-Host "============================================================"
    Write-Host $Message
    Write-Host "============================================================"
}

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host ""
Write-Host "Smart Trace Construction BGL Defense Demo"
Write-Host "This demo shows the same prototype on a second log dataset for robustness."
Write-Host "Project root: $RepoRoot"

Show-Step "Step 1: Parse the BGL log and create simple baseline event logs."
Invoke-Python src/run_pipeline_bgl.py --input data/BGL/BGL_2k.log

Show-Step "Step 2: Run STC on the BGL event stream."
Invoke-Python src/stc_bgl_v1_history_ip.py

Show-Step "Step 3: Build the BGL trace statistics table."
Invoke-Python src/summarize_eventlogs_bgl.py

Show-Step "Step 4: Evaluate BGL downstream process mining fitness and precision."
Invoke-Python src/pm_quality_eval_bgl_rq3.py

Show-Step "Final BGL demo summary"
Write-Host "Input file: data/BGL/BGL_2k.log"
Write-Host "BGL trace summary table: out_bgl/summary_table_bgl.csv"
Write-Host "BGL downstream process mining table: out_bgl/pm_quality_table_bgl.csv"
