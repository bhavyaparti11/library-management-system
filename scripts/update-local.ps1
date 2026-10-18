<#
.SYNOPSIS
    Runs the newest TESTED image of the Library Management System on this laptop.

.DESCRIPTION
    Default   Pulls (downloads) the newest image that GitHub Actions built, tested
              and published to GitHub Container Registry (ghcr.io), then replaces
              the local "library-app" container with a new one from that image.

    -Tag      Pull a specific published version instead of "latest",
              e.g. -Tag sha-1a2b3c4 (the tag is shown in the GitHub Actions summary).

    -Build    Builds the image from the code on this laptop instead of pulling it.

    -Watch    Keeps running and checks GHCR for a newer image every
              -IntervalSeconds. When GitHub Actions publishes a new image, the
              container is replaced automatically. Press Ctrl+C to stop watching
              (the app itself keeps running).

    The replacement is safe: the old container is only deleted after the new one
    passes its health check. If the new one fails, the old one is started again.

    Your books live in the "library-data" volume. This script never deletes it.

.EXAMPLE
    .\scripts\update-local.ps1
    .\scripts\update-local.ps1 -Tag sha-1a2b3c4
    .\scripts\update-local.ps1 -Watch
    .\scripts\update-local.ps1 -Build
    .\scripts\update-local.ps1 -Image ghcr.io/your-username/library-management-system:sha-1a2b3c4
#>
param(
    [switch]$Build,
    [switch]$Watch,
    [int]$IntervalSeconds = 60,
    [string]$Tag = "latest",
    [string]$Image = ""
)

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ContainerName = "library-app"
$PreviousName = "library-app-previous"
$VolumeName = "library-data"
Set-Location $ProjectRoot

function Write-Step($Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Stop-WithError($Message) {
    Write-Host $Message -ForegroundColor Red
    exit 1
}

function Test-ContainerExists($Name) {
    docker container inspect $Name > $null 2>&1
    return ($LASTEXITCODE -eq 0)
}

function Get-RegistryImage {
    # Works out ghcr.io/<owner>/<repo>:<tag> from this project's GitHub address.
    if ($Image) {
        return $Image
    }
    $remote = git remote get-url origin 2>$null
    if ($remote -match 'github\.com[:/]([^/]+)/([^/]+?)(\.git)?/?$') {
        return ("ghcr.io/{0}/{1}" -f $Matches[1], $Matches[2]).ToLower() + ":$Tag"
    }
    Stop-WithError ("Could not find the GitHub repository address. Run this inside your " +
        "project folder (after 'git remote add origin ...') or pass -Image ghcr.io/<user>/<repo>:latest")
}

function Get-ImageId($Reference) {
    $id = docker image inspect --format "{{.Id}}" $Reference 2>$null
    if ($LASTEXITCODE -ne 0) { return "" }
    return $id
}

function Get-RunningImageId {
    # Image ID of the running library-app container, or "" if it is not running.
    $info = docker container inspect --format "{{.State.Running}} {{.Image}}" $ContainerName 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $info) { return "" }
    $running, $id = "$info".Split(" ")
    if ($running -ne "true") { return "" }
    return $id
}

function Wait-ForHealth {
    foreach ($attempt in 1..30) {
        try {
            return Invoke-RestMethod -Uri "http://127.0.0.1:5000/health" -TimeoutSec 2
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    return $null
}

function Start-AppContainer($Reference) {
    Write-Step "Replacing the '$ContainerName' container (your data in '$VolumeName' is kept)"

    # Port 5000 is shared with the development container, so stop that one too.
    if (Test-ContainerExists "library-dev") {
        Write-Host "Stopping the development container (library-dev)."
        docker rm -f library-dev > $null 2>&1
    }

    # Keep the old container (stopped and renamed) until the new one is healthy.
    docker rm -f $PreviousName > $null 2>&1
    $hadOld = Test-ContainerExists $ContainerName
    if ($hadOld) {
        docker stop $ContainerName > $null
        docker rename $ContainerName $PreviousName
    }

    docker run -d --name $ContainerName --restart unless-stopped `
        -p 127.0.0.1:5000:5000 -v "${VolumeName}:/app/data" $Reference > $null
    $started = ($LASTEXITCODE -eq 0)

    $health = $null
    if ($started) {
        $health = Wait-ForHealth
    }

    if ($health) {
        if ($hadOld) {
            docker rm $PreviousName > $null
        }
        Write-Host "Healthy: version $($health.version), database $($health.database)" -ForegroundColor Green
        Write-Host "Open http://localhost:5000"
        return
    }

    # The new container failed: show why, then put the old one back.
    if ($started) {
        docker logs --tail 40 $ContainerName | Out-Host
    }
    docker rm -f $ContainerName > $null 2>&1
    if ($hadOld) {
        docker rename $PreviousName $ContainerName
        docker start $ContainerName > $null
        Stop-WithError "The new container was not healthy, so the previous container was restored."
    }
    Stop-WithError "The new container did not become healthy. Read the logs above (is port 5000 in use?)."
}

function Update-FromRegistry($Reference, [switch]$Quiet) {
    # Returns $true if the app is running the newest image afterwards.
    if (-not $Quiet) {
        Write-Step "Pulling the published image: $Reference"
        docker pull $Reference | Out-Host
    } else {
        docker pull -q $Reference > $null 2>&1
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Host ("Could not pull the image. Check that a GitHub Actions run on 'main' has " +
            "published it, and that the package is Public (or run: docker login ghcr.io).") -ForegroundColor Yellow
        return $false
    }
    $newest = Get-ImageId $Reference
    if ($newest -and $newest -eq (Get-RunningImageId)) {
        if (-not $Quiet) {
            Write-Host "The container is already running this image." -ForegroundColor Green
        }
        return $true
    }
    Write-Host "$(Get-Date -Format 'HH:mm:ss') New image found." -ForegroundColor Yellow
    Start-AppContainer $Reference | Out-Host
    return $true
}

# ---------------------------------------------------------------------------

docker info --format "{{.ServerVersion}}" > $null 2>&1
if ($LASTEXITCODE -ne 0) {
    Stop-WithError "Docker Desktop is not running. Start it and wait for 'Engine running'."
}

# Make sure the data volume exists (does nothing if it already exists).
docker volume create $VolumeName > $null

if ($Build) {
    $sha = git rev-parse --short HEAD 2>$null
    if (-not $sha) { $sha = "nogit" }
    $changes = git status --porcelain 2>$null
    $version = "local-$sha" + $(if ($changes) { "-modified" } else { "" })
    $buildDate = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd HH:mm") + " UTC"

    Write-Step "Building library-app:local from the code on this laptop (version $version)"
    docker build --build-arg "APP_VERSION=$version" --build-arg "BUILD_DATE=$buildDate" `
        -t library-app:local -t library-app:latest .
    if ($LASTEXITCODE -ne 0) {
        Stop-WithError "docker build failed. Read the messages above."
    }
    Start-AppContainer "library-app:local"
    exit 0
}

$reference = Get-RegistryImage

if ($Watch) {
    Update-FromRegistry $reference > $null
    Write-Step "Watching $reference every $IntervalSeconds seconds. Press Ctrl+C to stop watching."
    while ($true) {
        Start-Sleep -Seconds $IntervalSeconds
        Update-FromRegistry $reference -Quiet > $null
    }
}

if (-not (Update-FromRegistry $reference)) {
    exit 1
}
