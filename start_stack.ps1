$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$logDir = Join-Path $root ".tmp\stack"

if (-not (Test-Path $python)) {
    throw "Missing virtual environment Python: $python"
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$services = @(
    @{
        Name = "api.main:app"
        Port = 8010
        File = $python
        Args = @("-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", "8010")
        Stdout = Join-Path $logDir "api.stdout.log"
        Stderr = Join-Path $logDir "api.stderr.log"
    },
    @{
        Name = "dashboard.streamlit_app"
        Port = 8510
        File = $python
        Args = @("-m", "streamlit", "run", "dashboard\\streamlit_app.py", "--server.headless", "true", "--server.port", "8510")
        Stdout = Join-Path $logDir "dashboard.stdout.log"
        Stderr = Join-Path $logDir "dashboard.stderr.log"
    }
)

foreach ($service in $services) {
    $listener = Get-NetTCPConnection -LocalPort $service.Port -State Listen -ErrorAction SilentlyContinue
    if ($listener) {
        Write-Output ("Already running: {0} on port {1}" -f $service.Name, $service.Port)
        continue
    }

    $process = Start-Process `
        -FilePath $service.File `
        -ArgumentList $service.Args `
        -WorkingDirectory $root `
        -RedirectStandardOutput $service.Stdout `
        -RedirectStandardError $service.Stderr `
        -PassThru

    Write-Output ("Started {0} PID={1}" -f $service.Name, $process.Id)
}

Write-Output "Assembly optimizer stack startup requested."
