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

function Backup-VersionFile {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    $rootFull = [System.IO.Path]::GetFullPath($projectRoot).TrimEnd('\', '/')
    $pathFull = [System.IO.Path]::GetFullPath($Path)
    if ($pathFull.StartsWith($rootFull + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
        $relative = $pathFull.Substring($rootFull.Length + 1)
    } else {
        $relative = Split-Path -Leaf $pathFull
    }
    $safe = $relative -replace '[^A-Za-z0-9._-]', '_'
    if (-not (Test-Path -LiteralPath $backupPath -PathType Container)) {
        if (Test-Path -LiteralPath $backupPath) {
            Remove-Item -LiteralPath $backupPath -Force
        }
        New-Item -ItemType Directory -Path $backupPath -Force | Out-Null
    }
    $bak = Join-Path $backupPath ($safe + '.bak')
    $rel = Join-Path $backupPath ($safe + '.rel')
    if (-not (Test-Path -LiteralPath $bak)) {
        Copy-Item -LiteralPath $Path -Destination $bak -Force
        Set-Content -LiteralPath $rel -Value $relative -Encoding utf8 -NoNewline
    }
}

function Restore-VersionBackups {
    if (Test-Path -LiteralPath $backupPath -PathType Container) {
        foreach ($relFile in Get-ChildItem -LiteralPath $backupPath -Filter '*.rel') {
            $relative = Get-Content -LiteralPath $relFile.FullName -Raw
            if (-not $relative) {
                continue
            }
            $bak = [System.IO.Path]::ChangeExtension($relFile.FullName, '.bak')
            if (-not (Test-Path -LiteralPath $bak)) {
                continue
            }
            $target = Join-Path $projectRoot $relative
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
            Copy-Item -LiteralPath $bak -Destination $target -Force
        }
        Remove-Item -LiteralPath $backupPath -Recurse -Force
    } elseif (Test-Path -LiteralPath $backupPath) {
        Copy-Item -LiteralPath $backupPath -Destination $versionPath -Force
        Remove-Item -LiteralPath $backupPath -Force
    }
}

function Bump-SemverHundredth {
    param([string]$Version)

    $match = [regex]::Match($Version, '^(?<major>\d+)\.(?<minor>\d{2})$')
    if (-not $match.Success) {
        return $null
    }
    $major = [int]$match.Groups['major'].Value
    $minor = [int]$match.Groups['minor'].Value
    $hundredths = ($major * 100) + $minor + 1
    return ('{0}.{1:00}' -f ([math]::Floor($hundredths / 100)), ($hundredths % 100))
}

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
    $dirty = @(Invoke-Git diff --name-only HEAD)
    $changed += $dirty
    return @{
        Files = @($changed | Where-Object { $_ } | Select-Object -Unique)
        DirtyFiles = @($dirty | Where-Object { $_ } | Select-Object -Unique)
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

function Get-ChangedPluginIds {
    param([string[]]$Files)

    $ids = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    $ignoredNames = @('manifest.json')
    foreach ($raw in $Files) {
        $file = ([string]$raw).Replace('\', '/')
        $match = [regex]::Match($file, '^modules/(integrations|plugins)/(?<id>[^/]+)/(?<rest>.+)$')
        if (-not $match.Success) {
            continue
        }
        $rest = $match.Groups['rest'].Value
        $leaf = Split-Path -Leaf $rest
        if ($ignoredNames -contains $leaf) {
            continue
        }
        if ($rest -eq 'plugin.py' -or $rest.StartsWith('assets/', [System.StringComparison]::OrdinalIgnoreCase) -or $rest.StartsWith('web/', [System.StringComparison]::OrdinalIgnoreCase) -or $rest -match '\.(py|json|html|css|js|md|txt|png|jpg|jpeg|webp|ico|ttf)$') {
            [void]$ids.Add($match.Groups['id'].Value)
        }
    }
    return @($ids)
}

function Set-PluginVersion {
    param(
        [string]$PluginId,
        [string]$NewVersion
    )

    $folders = @(
        [System.IO.Path]::Combine($projectRoot, 'modules', 'integrations', $PluginId),
        [System.IO.Path]::Combine($projectRoot, 'modules', 'plugins', $PluginId)
    )
    $folder = $folders | Where-Object { Test-Path -LiteralPath (Join-Path $_ 'manifest.json') } | Select-Object -First 1
    if (-not $folder) {
        return
    }

    $manifestPath = Join-Path $folder 'manifest.json'
    $manifestSource = Get-Content -LiteralPath $manifestPath -Raw
    $manifestUpdated = [regex]::Replace($manifestSource, '("version"\s*:\s*")([^"]+)(")', '${1}' + $NewVersion + '${3}', 1)
    if ($manifestUpdated -ne $manifestSource) {
        Backup-VersionFile -Path $manifestPath
        Set-Content -LiteralPath $manifestPath -Value $manifestUpdated -Encoding utf8 -NoNewline
    }

}

function Bump-ChangedPluginVersions {
    param([string[]]$Files)

    foreach ($pluginId in (Get-ChangedPluginIds -Files $Files)) {
        $manifestPath = $null
        foreach ($root in @('modules\integrations', 'modules\plugins')) {
            $candidate = [System.IO.Path]::Combine($projectRoot, $root, $pluginId, 'manifest.json')
            if (Test-Path -LiteralPath $candidate) {
                $manifestPath = $candidate
                break
            }
        }
        if (-not $manifestPath) {
            continue
        }
        $manifest = Get-Content -LiteralPath $manifestPath -Raw
        $match = [regex]::Match($manifest, '"version"\s*:\s*"(?<version>\d+\.\d{2})"')
        if (-not $match.Success) {
            Write-Host "Plugin-Version bleibt: $pluginId (kein X.XX Format)" -ForegroundColor Yellow
            continue
        }
        $oldVersion = $match.Groups['version'].Value
        $newVersion = Bump-SemverHundredth -Version $oldVersion
        if (-not $newVersion) {
            continue
        }
        Set-PluginVersion -PluginId $pluginId -NewVersion $newVersion
        Write-Host ("Plugin-Version {0}: {1} -> {2}" -f $pluginId, $oldVersion, $newVersion) -ForegroundColor Green
    }
}

if ($Restore) {
    Restore-VersionBackups
    exit 0
}

if ($Finalize) {
    if (Test-Path -LiteralPath $backupPath) {
        Remove-Item -LiteralPath $backupPath -Recurse -Force
    }
    exit 0
}

# Ein abgebrochener vorheriger Build darf keine halbfertige Erhoehung hinterlassen.
if (Test-Path -LiteralPath $backupPath) {
    Restore-VersionBackups
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
Bump-ChangedPluginVersions -Files $scan.DirtyFiles
$shouldBump = Test-CoreVersionChange -Files $scan.Files -Messages $scan.Messages
if (-not $shouldBump) {
    Write-Host ("Build-Version bleibt: $oldVersion") -ForegroundColor Green
    exit 0
}

Backup-VersionFile -Path $versionPath
$replacement = 'APP_VERSION = "' + $newVersion + '" +'
$updated = [regex]::Replace($source, $pattern, $replacement, 1)
Set-Content -LiteralPath $versionPath -Value $updated -Encoding utf8 -NoNewline

Write-Host ("Build-Version: $oldVersion -> $newVersion") -ForegroundColor Green
