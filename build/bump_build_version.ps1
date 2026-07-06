[CmdletBinding(DefaultParameterSetName = 'Bump')]
param(
    [Parameter(ParameterSetName = 'Bump')]
    [switch]$Bump,
    [Parameter(Mandatory = $true, ParameterSetName = 'Restore')]
    [switch]$Restore,
    [Parameter(Mandatory = $true, ParameterSetName = 'Finalize')]
    [switch]$Finalize
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$versionPath = Join-Path $projectRoot 'shared\version.py'
$backupPath = Join-Path $PSScriptRoot '.version-before-build'

if ($Restore) {
    if (Test-Path -LiteralPath $backupPath) {
        Copy-Item -LiteralPath $backupPath -Destination $versionPath -Force
        Remove-Item -LiteralPath $backupPath -Force
    }
    exit 0
}

if ($Finalize) {
    if (Test-Path -LiteralPath $backupPath) {
        Remove-Item -LiteralPath $backupPath -Force
    }
    exit 0
}

# Ein abgebrochener vorheriger Build darf keine halbfertige Erhoehung hinterlassen.
if (Test-Path -LiteralPath $backupPath) {
    Copy-Item -LiteralPath $backupPath -Destination $versionPath -Force
    Remove-Item -LiteralPath $backupPath -Force
}

$source = Get-Content -LiteralPath $versionPath -Raw
$pattern = 'APP_VERSION\s*=\s*"(?<major>\d+)\.(?<minor>\d{2})"\s*\+'
$match = [regex]::Match($source, $pattern)
if (-not $match.Success) {
    throw 'APP_VERSION muss in shared\version.py das Format X.XX verwenden.'
}

$major = [int]$match.Groups['major'].Value
$minor = [int]$match.Groups['minor'].Value
$hundredths = ($major * 100) + $minor + 1
$nextMajor = [math]::Floor($hundredths / 100)
$nextMinor = $hundredths % 100
$oldVersion = '{0}.{1:00}' -f $major, $minor
$newVersion = '{0}.{1:00}' -f $nextMajor, $nextMinor

Copy-Item -LiteralPath $versionPath -Destination $backupPath -Force
$replacement = 'APP_VERSION = "' + $newVersion + '" +'
$updated = [regex]::Replace($source, $pattern, $replacement, 1)
Set-Content -LiteralPath $versionPath -Value $updated -Encoding utf8 -NoNewline

Write-Host ("Build-Version: $oldVersion -> $newVersion") -ForegroundColor Green
