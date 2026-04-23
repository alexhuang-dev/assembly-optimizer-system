$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$matches = @(
    "*api.main:app*",
    "*dashboard\\streamlit_app.py*"
)

$targets = Get-CimInstance Win32_Process |
    Where-Object {
        $cmd = $_.CommandLine
        if (-not $cmd) {
            return $false
        }
        if ($cmd -notlike "*$root*") {
            return $false
        }
        foreach ($pattern in $matches) {
            if ($cmd -like $pattern) {
                return $true
            }
        }
        return $false
    }

if (-not $targets) {
    Write-Output "No stack processes found."
    exit 0
}

foreach ($target in $targets) {
    $existing = Get-Process -Id $target.ProcessId -ErrorAction SilentlyContinue
    if (-not $existing) {
        Write-Output ("Already stopped PID={0}" -f $target.ProcessId)
        continue
    }

    try {
        Stop-Process -Id $target.ProcessId -Force -ErrorAction Stop
        Write-Output ("Stopped PID={0}" -f $target.ProcessId)
    }
    catch {
        if ($_.Exception.Message -like "*Cannot find a process with the process identifier*") {
            Write-Output ("Already stopped PID={0}" -f $target.ProcessId)
            continue
        }
        Write-Output ("Failed to stop PID={0}: {1}" -f $target.ProcessId, $_.Exception.Message)
    }
}

