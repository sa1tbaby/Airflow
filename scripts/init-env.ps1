[CmdletBinding()]
param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$sourcePath = Join-Path $projectRoot ".env.example"
$targetPath = Join-Path $projectRoot ".env"

if ((Test-Path -LiteralPath $targetPath) -and -not $Force) {
    Write-Host ".env already exists. Use -Force to replace it."
    exit 0
}

function New-UrlSafeSecret {
    param(
        [Parameter(Mandatory)]
        [int]$ByteCount,
        [switch]$KeepPadding
    )

    $bytes = New-Object byte[] $ByteCount
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    }
    finally {
        $generator.Dispose()
    }
    $value = [Convert]::ToBase64String($bytes).Replace("+", "-").Replace("/", "_")
    if (-not $KeepPadding) {
        $value = $value.TrimEnd("=")
    }
    return $value
}

$content = Get-Content -Raw -LiteralPath $sourcePath
$content = $content -replace '(?m)^POSTGRES_PASSWORD=.*$', "POSTGRES_PASSWORD=$(New-UrlSafeSecret -ByteCount 24)"
$content = $content -replace '(?m)^AIRFLOW_ADMIN_PASSWORD=.*$', "AIRFLOW_ADMIN_PASSWORD=$(New-UrlSafeSecret -ByteCount 18)"
$content = $content -replace '(?m)^FERNET_KEY=.*$', "FERNET_KEY=$(New-UrlSafeSecret -ByteCount 32 -KeepPadding)"
$content = $content -replace '(?m)^AIRFLOW_WEBSERVER_SECRET_KEY=.*$', "AIRFLOW_WEBSERVER_SECRET_KEY=$(New-UrlSafeSecret -ByteCount 48)"

[System.IO.File]::WriteAllText($targetPath, $content, [System.Text.UTF8Encoding]::new($false))
Write-Host "Created $targetPath with generated development secrets."
Write-Host "The administrator credentials are stored in .env and must not be committed."

