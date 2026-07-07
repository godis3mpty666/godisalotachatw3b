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

function Invoke-Git {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
    try {
        $output = & git @Args 2>$null
        if ($LASTEXITCODE -eq 0) {
            return @($output)
        }
    } catch {
    }
    return @()
}

function Get-ChangedBuildFiles {
    param([string]$CurrentVersion)

    $baseRef = $null
    $versionTags = @(Invoke-Git for-each-ref --sort=-creatordate --format='%(refname:short)' "refs/tags/v$CurrentVersion*")
    if ($versionTags.Count -gt 0) {
        $baseRef = [string]$versionTags[0]
    } else {
        $allTags = @(Invoke-Git for-each-ref --sort=-creatordate --format='%(refname:short)' 'refs/tags/v*')
        if ($allTags.Count -gt 0) {
            $baseRef = [string]$allTags[0]
        }
    }

    $changed = @()
    $messages = @()
    if ($baseRef) {
        $changed += Invoke-Git diff --name-only "$baseRef..HEAD"
        $messages += Invoke-Git log --format=%B "$baseRef..HEAD"
        Write-Host "Versionserkennung: Vergleiche mit $baseRef" -ForegroundColor DarkGray
    } else {
        $changed += Invoke-Git diff --name-only 'HEAD~1..HEAD'
        $messages += Invoke-Git log --format=%B -1
        Write-Host "Versionserkennung: Kein v*-Tag gefunden, vergleiche mit letztem Commit." -ForegroundColor DarkGray
    }

    # Dirty working tree changes count too, except generated version/provenance files below.
    $changed += Invoke-Git diff --name-only HEAD
    return @{
        Files = @($changed | Where-Object { $_ } | Select-Object -Unique)
        Messages = ($messages -join "`n")
    }
}

function Test-CoreVersionChange {
    param(
        [string[]]$Files,
        [string]$Messages
    )

    if ($Messages -match '\[(no-version|no version|skip-version|skip version)\]') {
        Write-Host 'Versionserkennung: [no-version] Override gefunden.' -ForegroundColor Yellow
        return $false
    }
    if ($Messages -match '\[(core|version|bump-version|bump version)\]') {
        Write-Host 'Versionserkennung: [core]/[version] Override gefunden.' -ForegroundColor Green
        return $true
    }

    $corePrefixes = @(
        'core/host/',
        'core/runtime/',
        'shared/',
        'build/',
        'run_webbased.py'
    )
    $ignored = @(
        'shared/version.py',
        'shared/build_provenance.py',
        'README.md'
    )

    foreach ($raw in $Files) {
        $file = ([string]$raw).Replace('\', '/')
        if (-not $file -or $ignored -contains $file) {
            continue
        }
        foreach ($prefix in $corePrefixes) {
            if ($file.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase) -or $file.Equals($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
                Write-Host "Versionserkennung: Core-Aenderung erkannt: $file" -ForegroundColor Green
                return $true
            }
        }
    }

    Write-Host 'Versionserkennung: Keine Core-Aenderung erkannt, APP_VERSION bleibt gleich.' -ForegroundColor Green
    return $false
}

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

$scan = Get-ChangedBuildFiles -CurrentVersion $oldVersion
$shouldBump = Test-CoreVersionChange -Files $scan.Files -Messages $scan.Messages
if (-not $shouldBump) {
    Write-Host ("Build-Version bleibt: $oldVersion") -ForegroundColor Green
    exit 0
}

Copy-Item -LiteralPath $versionPath -Destination $backupPath -Force
$replacement = 'APP_VERSION = "' + $newVersion + '" +'
$updated = [regex]::Replace($source, $pattern, $replacement, 1)
Set-Content -LiteralPath $versionPath -Value $updated -Encoding utf8 -NoNewline

Write-Host ("Build-Version: $oldVersion -> $newVersion") -ForegroundColor Green
