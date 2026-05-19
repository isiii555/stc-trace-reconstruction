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

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Invoke-Python src/run_pipeline_raw.py --input data/HDFS_v1/HDFS.log
Invoke-Python src/baseline_component_timegap.py
Invoke-Python src/stc_v2_history_ip.py --delta 2
Invoke-Python src/stc_v2_history_ip.py --delta 5
Invoke-Python src/stc_v2_history_ip.py --delta 10
Invoke-Python src/stc_v3_dbscan.py --input out/eventlog_oracle_blockid.csv --delta 5 --eps 0.2 --min_samples 3 --max_segment_size 1000
Invoke-Python src/purity_table_with_baselines.py
Invoke-Python src/pm_quality_eval.py
