<#
.SYNOPSIS
    Start or stop native Postgres and Redis for local development on Windows (no Docker).
.DESCRIPTION
    Expects portable binaries under $env:CENTRALIGN_INFRA_HOME (default: %LOCALAPPDATA%\centralign):
      pgsql\bin\pg_ctl.exe     (EnterpriseDB Windows binaries zip)
      redis\redis-server.exe   (redis-windows build)
.EXAMPLE
    ./scripts/windows/infra.ps1 start
#>
param(
    [Parameter(Mandatory)][ValidateSet("start", "stop", "status", "init")] [string]$Action
)

$ErrorActionPreference = "Stop"
$infraHome = if ($env:CENTRALIGN_INFRA_HOME) { $env:CENTRALIGN_INFRA_HOME } else { Join-Path $env:LOCALAPPDATA "centralign" }
$pgBin = Join-Path $infraHome "pgsql\bin"
$pgData = Join-Path $infraHome "pgdata"
$pgLog = Join-Path $infraHome "postgres.log"
$redisExe = Join-Path $infraHome "redis\redis-server.exe"
$redisCli = Join-Path $infraHome "redis\redis-cli.exe"
$redisData = Join-Path $infraHome "redis-data"
# Single source of truth: the same DATABASE__URL / REDIS__URL the backend reads from .env.
$envFile = Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) ".env"
if (-not (Test-Path $envFile)) { throw "Missing $envFile. Copy .env.example to .env first." }
$envValues = @{}
Get-Content $envFile | Where-Object { $_ -match '^[A-Z0-9_]+=' } | ForEach-Object {
    $key, $value = $_ -split '=', 2; $envValues[$key] = $value
}
$dbUrl = [regex]::Match($envValues["DATABASE__URL"], '//(?<user>[^:]+):(?<password>[^@]+)@(?<host>[^:/]+):(?<port>\d+)/(?<name>\w+)')
if (-not $dbUrl.Success) { throw "DATABASE__URL in .env must look like postgresql+asyncpg://user:password@host:port/name" }
$dbUser = $dbUrl.Groups["user"].Value
$dbPassword = $dbUrl.Groups["password"].Value
$dbPort = $dbUrl.Groups["port"].Value
$dbName = $dbUrl.Groups["name"].Value
$redisPort = [regex]::Match($envValues["REDIS__URL"], ':(\d+)').Groups[1].Value

function Invoke-Sql([string]$sql) {
    & (Join-Path $pgBin "psql.exe") -U postgres -h localhost -p $dbPort -tAc $sql
}

function Initialize-Postgres {
    $superPassword = $envValues["POSTGRES_SUPERUSER_PASSWORD"]
    if (-not $superPassword) { throw "Set POSTGRES_SUPERUSER_PASSWORD in .env" }
    if (-not (Test-Path (Join-Path $pgData "PG_VERSION"))) {
        $pwFile = New-TemporaryFile
        try {
            Set-Content -Path $pwFile -Value $superPassword -NoNewline -Encoding ascii
            & (Join-Path $pgBin "initdb.exe") -D $pgData -U postgres -A scram-sha-256 --pwfile=$pwFile -E UTF8 --locale=C | Out-Null
        } finally { Remove-Item $pwFile }
    }
    Start-Postgres
    $env:PGPASSWORD = $superPassword
    # Idempotent provisioning: safe to run again.
    if (-not (Invoke-Sql "SELECT 1 FROM pg_roles WHERE rolname = '$dbUser'")) {
        Invoke-Sql "CREATE ROLE $dbUser LOGIN PASSWORD '$dbPassword'" | Out-Null
    }
    foreach ($name in @($dbName, "${dbName}_test")) {
        if (-not (Invoke-Sql "SELECT 1 FROM pg_database WHERE datname = '$name'")) {
            Invoke-Sql "CREATE DATABASE $name OWNER $dbUser" | Out-Null
        }
    }
    Write-Output "postgres ready: databases $dbName, ${dbName}_test owned by $dbUser"
}

function Start-Postgres {
    # Detached start: the postmaster must not inherit our stdio, and we wait for pg_ctl only
    # (Start-Process -Wait would also wait for the long-lived postmaster it spawns).
    $pgCtl = Start-Process -FilePath (Join-Path $pgBin "pg_ctl.exe") -WindowStyle Hidden -PassThru `
        -ArgumentList "-D `"$pgData`" -l `"$pgLog`" -o `"-p $dbPort -c listen_addresses=localhost`" -w start"
    $pgCtl.WaitForExit()
}

function Start-Redis {
    New-Item -ItemType Directory -Force $redisData | Out-Null
    Start-Process -FilePath $redisExe -WindowStyle Hidden `
        -ArgumentList "--port $redisPort --bind 127.0.0.1 --appendonly yes --dir `"$redisData`""
}

switch ($Action) {
    "init" { Initialize-Postgres; Start-Redis }
    "start" { Start-Postgres; Start-Redis }
    "stop" {
        & (Join-Path $pgBin "pg_ctl.exe") -D $pgData -m fast stop
        & $redisCli -p $redisPort shutdown nosave
    }
    "status" {
        & (Join-Path $pgBin "pg_ctl.exe") -D $pgData status
        & $redisCli -p $redisPort ping
    }
}
