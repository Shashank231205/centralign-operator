<#
.SYNOPSIS
    Run the whole stack natively on Windows: infra, sandbox apps, API, worker and console.
.EXAMPLE
    ./scripts/windows/dev.ps1 up -Reset    # fresh sandbox data, start everything
    ./scripts/windows/dev.ps1 status
    ./scripts/windows/dev.ps1 down
.NOTES
    Calls the virtualenv executables directly (no `uv run` per process), so concurrent
    processes never wait on uv's environment lock. Logs go to var/logs, PIDs to var/run.
#>
param(
    [Parameter(Mandatory)][ValidateSet("up", "down", "status")] [string]$Action,
    [switch]$Reset,
    [int]$ReadyTimeoutSeconds = 60
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$venv = Join-Path $root ".venv\Scripts"
$logs = Join-Path $root "var\logs"
$pidFile = Join-Path $root "var\run\pids.json"

function Read-DotEnv {
    $values = @{}
    Get-Content (Join-Path $root ".env") | Where-Object { $_ -match '^[A-Z0-9_]+=' } | ForEach-Object {
        $key, $value = $_ -split '=', 2; $values[$key] = $value
    }
    return $values
}

function Start-AppProcess([string]$name, [string]$exe, [string]$arguments, [string]$workdir = $root) {
    $process = Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory $workdir `
        -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $logs "$name.log") -RedirectStandardError (Join-Path $logs "$name.err.log")
    return @{ name = $name; pid = $process.Id }
}

function Wait-Port([int]$port) {
    # Infra starts asynchronously; app processes must not race it.
    $deadline = (Get-Date).AddSeconds($ReadyTimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $client = New-Object Net.Sockets.TcpClient
        try { $client.Connect("127.0.0.1", $port); return } catch { Start-Sleep -Milliseconds 500 } finally { $client.Dispose() }
    }
    throw "Port $port not ready after $ReadyTimeoutSeconds s"
}

function Write-FrontendEnv($envValues) {
    $content = "OPERATOR_API_URL=$($envValues['OPERATOR_API_URL'])`nOPERATOR_API_KEY=$($envValues['OPERATOR_API_KEY'])`n"
    [IO.File]::WriteAllText((Join-Path $root "frontend\.env.local"), $content, (New-Object System.Text.UTF8Encoding($false)))
}

function Invoke-Up {
    New-Item -ItemType Directory -Force $logs, (Split-Path $pidFile) | Out-Null
    & (Join-Path $PSScriptRoot "infra.ps1") start | Out-Null
    Wait-Port 5432
    Wait-Port 6379
    $envValues = Read-DotEnv
    Push-Location $root
    try {
        & (Join-Path $venv "python.exe") -m alembic -c backend/alembic.ini upgrade head
        if ($Reset -or -not (Test-Path (Join-Path $root "var\sandbox\erp.db"))) {
            & (Join-Path $venv "python.exe") -m sandbox.seed
        }
    } finally { Pop-Location }
    Write-FrontendEnv $envValues
    $uvicorn = Join-Path $venv "uvicorn.exe"
    $services = @(
        (Start-AppProcess "sandbox-portal" $uvicorn "sandbox.vendor_portal.app:create_app --factory --port 8101"),
        (Start-AppProcess "sandbox-erp" $uvicorn "sandbox.internal_erp.app:create_app --factory --port 8102"),
        (Start-AppProcess "api" $uvicorn "app.main:create_app --factory --port 8000"),
        (Start-AppProcess "worker" (Join-Path $venv "arq.exe") "app.workers.main.WorkerSettings"),
        (Start-AppProcess "frontend" "cmd.exe" "/c npm run dev" (Join-Path $root "frontend"))
    )
    $services | ConvertTo-Json | Set-Content -Path $pidFile -Encoding utf8
    Write-Output "Started. Console: http://localhost:3000   API docs: http://localhost:8000/docs"
    Write-Output "Sandbox: http://localhost:8101 (SupplyLink)   http://localhost:8102 (Ledgerly ERP)"
    Write-Output "Logs: $logs"
}

function Invoke-Down {
    if (Test-Path $pidFile) {
        foreach ($service in (Get-Content $pidFile | ConvertFrom-Json)) {
            if (Get-Process -Id $service.pid -ErrorAction SilentlyContinue) {
                & taskkill.exe /PID $service.pid /T /F | Out-Null
            }
        }
        Remove-Item $pidFile
    }
    Write-Output "Stopped app processes (Postgres and Redis keep running; use infra.ps1 stop)."
}

function Invoke-Status {
    $ports = @{ 8101 = "sandbox-portal"; 8102 = "sandbox-erp"; 8000 = "api"; 3000 = "frontend"; 5432 = "postgres"; 6379 = "redis" }
    $listening = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty LocalPort -Unique
    foreach ($port in $ports.Keys | Sort-Object) {
        $state = if ($listening -contains $port) { "up" } else { "down" }
        Write-Output ("{0,-15} {1,-5} :{2}" -f $ports[$port], $state, $port)
    }
    $worker = if ((Test-Path $pidFile) -and ((Get-Content $pidFile | ConvertFrom-Json) | Where-Object { $_.name -eq "worker" -and (Get-Process -Id $_.pid -ErrorAction SilentlyContinue) })) { "up" } else { "down" }
    Write-Output ("{0,-15} {1,-5}" -f "worker", $worker)
}

switch ($Action) {
    "up" { Invoke-Up }
    "down" { Invoke-Down }
    "status" { Invoke-Status }
}
