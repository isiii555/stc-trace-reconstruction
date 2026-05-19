param(
    [Parameter(Mandatory = $true)]
    [string]$InputFile,
    [int]$Delta = 60,
    [ValidateSet("correlation_weak", "attribute_based", "id_aware")]
    [string]$Mode = "correlation_weak"
)

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

Show-Step "Generic raw log STC demo"
Write-Host "Input file: $InputFile"
Write-Host "Delta seconds: $Delta"
if ($Mode -eq "id_aware") {
    Write-Host "Mode id_aware is deprecated; using attribute_based."
    $Mode = "attribute_based"
}
Write-Host "Reconstruction mode: $Mode"
Write-Host "This mode uses best-effort parsing and is not part of the evaluated thesis experiments."

Show-Step "Step 1: Parse the selected raw log and run generic STC reconstruction."
Invoke-Python src/run_pipeline_generic.py --input $InputFile --delta $Delta --mode $Mode

Show-Step "Final generic demo summary"
Write-Host "Prepared event log: out_generic/eventlog_generic_prepared.csv"
Write-Host "Reconstructed event log: out_generic/eventlog_STC_generic_${Mode}_delta${Delta}s.csv"
Write-Host "Summary table: out_generic/summary_table_generic.csv"
Write-Host "Process mining table: out_generic/pm_quality_table_generic.csv"
Write-Host "Optional process model images: out_generic/process_model_generic_bpmn.* or out_generic/process_model_generic_petri.*"

if (Test-Path "out_generic/summary_table_generic.csv") {
    Write-Host ""
    Write-Host "Generic summary table contents:"
    Import-Csv "out_generic/summary_table_generic.csv" | Format-Table -AutoSize
}
else {
    Write-Host ""
    Write-Host "Generic summary table was not found: out_generic/summary_table_generic.csv"
}
