[CmdletBinding()]
param(
    [string]$ServerSecret,
    [string]$PublicHost,
    [switch]$SkipImageLoad,
    [switch]$SkipFirewall
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Invoke-Docker([string[]]$Arguments) {
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker $($Arguments -join ' ') failed (exit code $LASTEXITCODE)."
    }
}

function Invoke-Compose([string[]]$Arguments) {
    if ($script:ComposeStyle -eq "plugin") {
        & docker compose @Arguments
        $displayCommand = "docker compose"
    } else {
        & $script:ComposeExecutable @Arguments
        $displayCommand = $script:ComposeExecutable
    }
    if ($LASTEXITCODE -ne 0) {
        throw "$displayCommand $($Arguments -join ' ') failed (exit code $LASTEXITCODE)."
    }
}

function Write-Utf8NoBom([string]$Path, [string]$Content) {
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $encoding)
}

function New-DeploymentPassword {
    $bytes = [byte[]]::new(24)
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    } finally {
        $generator.Dispose()
    }
    return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', 'A').Replace('/', 'B')
}

function Set-DotEnvValue([string]$Path, [string]$Name, [string]$Value) {
    $content = Get-Content -LiteralPath $Path -Raw
    $line = "$Name=$Value"
    if ($content -match "(?m)^$([regex]::Escape($Name))=") {
        $content = [regex]::Replace($content, "(?m)^$([regex]::Escape($Name))=.*$", $line)
    } else {
        $content = $content.TrimEnd() + "`r`n$line`r`n"
    }
    Write-Utf8NoBom $Path $content
}

function Get-DotEnvValue([string]$Path, [string]$Name) {
    $match = [regex]::Match((Get-Content -LiteralPath $Path -Raw), "(?m)^$([regex]::Escape($Name))=(.*)$")
    if (-not $match.Success) { return $null }
    return $match.Groups[1].Value.Trim()
}

$deploymentDir = $PSScriptRoot
Set-Location -LiteralPath $deploymentDir

$requiredFiles = @("compose.yaml", ".env.example", "config_from_api.yaml")
foreach ($file in $requiredFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $deploymentDir $file) -PathType Leaf)) {
        throw "Missing deployment file: $file. Copy the complete Windows release directory and retry."
    }
}

Write-Step "Checking Docker and Compose"
Invoke-Docker @("version")
$script:ComposeStyle = $null
$script:ComposeExecutable = $null

$standaloneCompose = Get-Command docker-compose -ErrorAction SilentlyContinue
if ($standaloneCompose) {
    $script:ComposeExecutable = $standaloneCompose.Source
} else {
    $localCompose = Join-Path $deploymentDir "docker-compose.exe"
    if (Test-Path -LiteralPath $localCompose -PathType Leaf) {
        $script:ComposeExecutable = $localCompose
    }
}

if ($script:ComposeExecutable) {
    & $script:ComposeExecutable version
    if ($LASTEXITCODE -ne 0) {
        throw "docker-compose was found but could not run."
    }
    $script:ComposeStyle = "standalone"
    Write-Host "Using: $script:ComposeExecutable" -ForegroundColor Green
} else {
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "SilentlyContinue"
        & docker compose version 2>&1 | Out-Null
        $composePluginExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($composePluginExitCode -eq 0) {
        $script:ComposeStyle = "plugin"
        Write-Host "Using: docker compose" -ForegroundColor Green
    } else {
        throw "Docker Compose was not found. Put docker-compose.exe in PATH or copy it beside deploy.ps1."
    }
}

$envPath = Join-Path $deploymentDir ".env"
if (-not (Test-Path -LiteralPath $envPath)) {
    Copy-Item -LiteralPath (Join-Path $deploymentDir ".env.example") -Destination $envPath
    Set-DotEnvValue $envPath "MYSQL_ROOT_PASSWORD" (New-DeploymentPassword)
    Set-DotEnvValue $envPath "REDIS_PASSWORD" (New-DeploymentPassword)
    Write-Host "Created .env with random MySQL and Redis passwords." -ForegroundColor Green
} else {
    Write-Host "Existing .env found; keeping its current settings." -ForegroundColor Yellow
}

foreach ($item in @(
    @{ Name = "MYSQL_ROOT_PASSWORD"; Placeholder = "change-this-mysql-password" },
    @{ Name = "REDIS_PASSWORD"; Placeholder = "change-this-redis-password" }
)) {
    $value = Get-DotEnvValue $envPath $item.Name
    if ([string]::IsNullOrWhiteSpace($value) -or $value -eq $item.Placeholder) {
        Set-DotEnvValue $envPath $item.Name (New-DeploymentPassword)
        Write-Host "Replaced the placeholder value for $($item.Name)." -ForegroundColor Green
    }
}

$dataDir = Join-Path $deploymentDir "data"
$configPath = Join-Path $dataDir ".config.yaml"
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
if (-not (Test-Path -LiteralPath $configPath)) {
    Copy-Item -LiteralPath (Join-Path $deploymentDir "config_from_api.yaml") -Destination $configPath
    Write-Host "Copied config_from_api.yaml to data\.config.yaml." -ForegroundColor Green
} else {
    Write-Host "Existing data\.config.yaml found; keeping it." -ForegroundColor Yellow
}

if (-not $SkipImageLoad) {
    $archives = @(Get-ChildItem -LiteralPath $deploymentDir -Filter "xiaozhi-images-linux-amd64-*.tar" -File)
    if ($archives.Count -eq 0) {
        throw "No xiaozhi-images-linux-amd64-*.tar archive found. Use -SkipImageLoad if images are already loaded."
    }
    if ($archives.Count -gt 1) {
        throw "Multiple image archives found. Keep only the archive for this deployment."
    }
    $checksumFile = Join-Path $deploymentDir "SHA256SUMS"
    if (Test-Path -LiteralPath $checksumFile) {
        Write-Step "Verifying the offline image archive"
        $expectedHash = ((Get-Content -LiteralPath $checksumFile -First 1) -split '\s+')[0]
        $actualHash = (Get-FileHash -LiteralPath $archives[0].FullName -Algorithm SHA256).Hash
        if ($actualHash -ne $expectedHash) {
            throw "The image archive failed SHA-256 verification. Copy the release again."
        }
    }
    Write-Step "Loading offline Docker images (this can take a while)"
    Invoke-Docker @("load", "-i", $archives[0].FullName)
}

$composeArgs = @("--env-file", $envPath, "-f", (Join-Path $deploymentDir "compose.yaml"))
Write-Step "Validating the Compose configuration"
Invoke-Compose ($composeArgs + @("config", "--quiet"))

Write-Step "Starting MySQL, Redis, manager API, and manager Web"
Invoke-Compose ($composeArgs + @("up", "-d", "mysql", "redis", "manager-api", "manager-web"))
Invoke-Compose ($composeArgs + @("ps"))

if ([string]::IsNullOrWhiteSpace($ServerSecret)) {
    Write-Host "`nOpen http://SERVER-IP:$(Get-DotEnvValue $envPath 'MANAGER_WEB_PORT') and register the first administrator." -ForegroundColor Yellow
    Write-Host "Open Parameter Management and copy server.secret. Closing this window will not stop the services." -ForegroundColor Yellow
    $ServerSecret = Read-Host "Enter server.secret"
}
if ([string]::IsNullOrWhiteSpace($ServerSecret)) {
    throw "server.secret cannot be empty."
}
if ($ServerSecret -match "[\r\n]") {
    throw "server.secret cannot contain a newline."
}

Write-Step "Updating the server configuration"
$yaml = Get-Content -LiteralPath $configPath -Raw
$yaml = [regex]::Replace($yaml, "(?m)^(\s*url:\s*).*$", {
    param($match)
    return $match.Groups[1].Value + "http://manager-api:8002/xiaozhi"
}, 1)
$secretValue = $ServerSecret
$yamlSecretValue = "'" + $secretValue.Replace("'", "''") + "'"
$yaml = [regex]::Replace($yaml, "(?m)^(\s*secret:\s*).*$", {
    param($match)
    return $match.Groups[1].Value + $yamlSecretValue
}, 1)
if (-not [string]::IsNullOrWhiteSpace($PublicHost)) {
    $httpPort = Get-DotEnvValue $envPath "XIAOZHI_HTTP_PORT"
    $visionUrl = "http://${PublicHost}:${httpPort}/mcp/vision/explain"
    $yaml = [regex]::Replace($yaml, "(?m)^(\s*vision_explain:\s*).*$", {
        param($match)
        return $match.Groups[1].Value + $visionUrl
    }, 1)
}
Write-Utf8NoBom $configPath $yaml

if (-not $SkipFirewall) {
    Write-Step "Configuring Windows Firewall ports"
    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator
    )
    if ($isAdmin) {
        foreach ($port in @(
            (Get-DotEnvValue $envPath "MANAGER_WEB_PORT"),
            (Get-DotEnvValue $envPath "XIAOZHI_WS_PORT"),
            (Get-DotEnvValue $envPath "XIAOZHI_HTTP_PORT")
        ) | Select-Object -Unique) {
            $ruleName = "Xiaozhi TCP $port"
            if (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
                New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $port | Out-Null
            }
        }
    } else {
        Write-Warning "PowerShell is not running as Administrator. Rerun as Administrator or manually allow TCP 8000, 8002, and 8003."
    }
}

Write-Step "Starting all services"
Invoke-Compose ($composeArgs + @("up", "-d"))
Invoke-Compose ($composeArgs + @("ps"))

Write-Step "Showing recent logs for verification"
Invoke-Compose ($composeArgs + @("logs", "--tail", "100", "manager-api", "xiaozhi-server"))
Invoke-Compose ($composeArgs + @("exec", "-T", "redis", "sh", "-c", 'redis-cli -a "$REDIS_PASSWORD" ping'))
Write-Host "`nDeployment completed. Follow the server logs with:" -ForegroundColor Green
if ($script:ComposeStyle -eq "plugin") {
    Write-Host "docker compose --env-file .env -f compose.yaml logs -f xiaozhi-server"
} else {
    Write-Host "docker-compose --env-file .env -f compose.yaml logs -f xiaozhi-server"
}
