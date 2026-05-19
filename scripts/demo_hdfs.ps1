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
Write-Host "Smart Trace Construction HDFS Defense Demo"
Write-Host "This demo turns raw HDFS logs into reconstructed traces and evaluation tables."
Write-Host "Project root: $RepoRoot"

Show-Step "Step 1: Parse the raw HDFS log and create simple baseline event logs."
Invoke-Python src/run_pipeline_raw.py --input data/HDFS_v1/HDFS.log

Show-Step "Step 2: Create the component-based time-gap baseline."
Invoke-Python src/baseline_component_timegap.py

Show-Step "Step 3: Run STC with a 2-second inactivity threshold."
Invoke-Python src/stc_v2_history_ip.py --delta 2

Show-Step "Step 4: Run STC with a 5-second inactivity threshold."
Invoke-Python src/stc_v2_history_ip.py --delta 5

Show-Step "Step 5: Run STC with a 10-second inactivity threshold."
Invoke-Python src/stc_v2_history_ip.py --delta 10

Show-Step "Step 6: Run DBSCAN exploratory extension."
Invoke-Python src/stc_v3_dbscan.py --input out/eventlog_oracle_blockid.csv --delta 5 --eps 0.2 --min_samples 3 --max_segment_size 1000

Show-Step "Step 7: Build the HDFS purity comparison table."
Invoke-Python src/purity_table_with_baselines.py

Show-Step "Step 8: Evaluate downstream process mining fitness and precision."
Invoke-Python src/pm_quality_eval.py

Show-Step "Optional: Create a downstream process model visualization."
Invoke-Python src/visualize_process_model.py

Show-Step "Final HDFS demo summary"
Write-Host "Input file: data/HDFS_v1/HDFS.log"
Write-Host "Main reconstructed event log: out/eventlog_STC_v2_history_ip_delta5s.csv"
Write-Host "Purity summary table: out/purity_table_with_baselines.csv"
Write-Host "Downstream process mining table: out/pm_quality_table_inductive_rq2.csv"
Write-Host "Optional BPMN image: out/process_model_STC_delta5_bpmn.png or out/process_model_STC_delta5_bpmn.svg"
Write-Host "Optional Petri net fallback: out/process_model_STC_delta5_petri.png or out/process_model_STC_delta5_petri.svg"

if (Test-Path "out/purity_table_with_baselines.csv") {
    Write-Host ""
    Write-Host "Purity summary table contents:"
    Import-Csv "out/purity_table_with_baselines.csv" | Format-Table -AutoSize
}
else {
    Write-Host ""
    Write-Host "Purity summary table was not found: out/purity_table_with_baselines.csv"
}
