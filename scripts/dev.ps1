<#
.SYNOPSIS
    Starts (or stops) the DEVELOPMENT container with live code reload.

.DESCRIPTION
    Uses compose.yaml to run the app with your project files mounted into the
    container. Edit app.py, templates or static files in VS Code, save, and
    refresh http://localhost:5000 to see the change. No rebuild needed.

    Your books are kept in the "library-data" volume. This script never
    deletes that volume.

.EXAMPLE
    .\scripts\dev.ps1          # start development mode
    .\scripts\dev.ps1 -Stop    # stop development mode
#>
param(
    [switch]$Stop
)

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VolumeName = "library-data"
Set-Location $ProjectRoot

docker info --format "{{.ServerVersion}}" > $null 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker Desktop is not running. Start it and wait for 'Engine running'." -ForegroundColor Red
    exit 1
}

if ($Stop) {
    docker compose down
    Write-Host "Development container stopped. Your data is still in the '$VolumeName' volume." -ForegroundColor Green
    Write-Host "Start the normal container again with: docker start library-app  (or .\scripts\update-local.ps1)"
    exit 0
}

# Port 5000 can only be used by one container at a time, so STOP (not delete)
# the normal "library-app" container first. Bring it back later with
# "docker start library-app" after ".\scripts\dev.ps1 -Stop".
docker stop library-app > $null 2>&1

# Make sure the data volume exists (does nothing if it already exists).
docker volume create $VolumeName > $null

Write-Host "Starting development mode (first run builds the image)..." -ForegroundColor Cyan
docker compose up --build -d
if ($LASTEXITCODE -ne 0) {
    Write-Host "docker compose failed. Read the messages above." -ForegroundColor Red
    exit 1
}

foreach ($attempt in 1..30) {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:5000/health" -TimeoutSec 2
        Write-Host ""
        Write-Host "Development mode is running: http://localhost:5000" -ForegroundColor Green
        Write-Host "Version shown in the app: $($health.version)"
        Write-Host "Edit app.py, templates\ or static\ in VS Code, save, then refresh the browser."
        Write-Host "Logs: docker compose logs -f     Stop: .\scripts\dev.ps1 -Stop"
        exit 0
    } catch {
        Start-Sleep -Seconds 1
    }
}
Write-Host "The app did not respond. Showing the logs:" -ForegroundColor Red
docker compose logs --tail 40
exit 1
