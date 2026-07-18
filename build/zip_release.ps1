$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$versionFile = Join-Path $root "shared\version.py"

if (-not (Test-Path -LiteralPath $versionFile)) {
    throw "shared\version.py wurde nicht gefunden."
}

$versionText = Get-Content -LiteralPath $versionFile -Raw
$baseMatch = [regex]::Match($versionText, 'APP_VERSION\s*=\s*"([^"]+)"')
if (-not $baseMatch.Success) {
    throw "APP_VERSION konnte in shared\version.py nicht erkannt werden."
}

$version = $baseMatch.Groups[1].Value
$provenanceFile = Join-Path $root "shared\build_provenance.py"
if (Test-Path -LiteralPath $provenanceFile) {
    $provenanceText = Get-Content -LiteralPath $provenanceFile -Raw
    $suffixMatch = [regex]::Match($provenanceText, 'BUILD_SUFFIX\s*=\s*"([^"]*)"')
    if ($suffixMatch.Success) {
        $version += $suffixMatch.Groups[1].Value
    }
}

$safeVersion = ($version -replace '[^\w.-]+', '_').Trim("_")
if (-not $safeVersion) {
    throw "Versionsnummer ist leer."
}

$outDir = Join-Path $root "dist"
$sourceDir = Join-Path $outDir "webbased"
if (-not (Test-Path -LiteralPath $sourceDir)) {
    throw "dist\webbased wurde nicht gefunden. Bitte zuerst build\build_exe.bat ausfuehren."
}
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$zipName = "godisalotachat-webbased-v$safeVersion.zip"
$zipPath = Join-Path $outDir $zipName
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}

$excludeDirs = @(
    "__pycache__",
    "logs",
    "data\auth",
    "data\plugins",
    "data\ui_browser_profile"
)

$allowedDataFiles = @(
    "data\.gitkeep",
    "data\__init__.py",
    "data\paths.py"
)

$excludeFiles = @(
    ".env",
    ".env.*",
    "*.key",
    "*.pem",
    "*.p12",
    "*.pfx",
    "*.crt",
    "*.cer",
    "*.log",
    "*.sqlite",
    "*.sqlite3",
    "*.db",
    "*.tmp",
    "*.bak",
    "*.pyc",
    "*.pyo",
    "*.zip",
    "diagnose_embedded_python.bat",
    "diagnose_embedded_python.ps1",
    "*credentials*.json",
    "*oauth_cache*.json",
    "*tokens*.json",
    "*state*.json",
    "ui_browser_profile.zip"
)

function Test-ExcludedPath {
    param(
        [Parameter(Mandatory = $true)][string]$RelativePath,
        [Parameter(Mandatory = $true)][bool]$IsDirectory
    )

    $rel = $RelativePath.Replace("/", "\").TrimStart("\")
    if (-not $IsDirectory -and ($allowedDataFiles | Where-Object { $rel -ieq $_ })) {
        return $false
    }
    if ($rel -ieq "data" -or $rel.StartsWith("data\", [System.StringComparison]::OrdinalIgnoreCase)) {
        return $true
    }
    if ($rel -match '(^|\\)(__pycache__|browser_profile[^\\]*|[^\\]*_profile|profile)(\\|$)') {
        return $true
    }
    foreach ($dir in $excludeDirs) {
        $cleanDir = $dir.TrimEnd("\")
        if ($rel -ieq $cleanDir -or $rel.StartsWith("$cleanDir\", [System.StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }

    if (-not $IsDirectory) {
        foreach ($pattern in $excludeFiles) {
            if ($rel -like $pattern) {
                return $true
            }
        }
    }

    return $false
}

function Get-ReleaseRelativePath {
    param([Parameter(Mandatory = $true)][string]$FullName)
    return $FullName.Substring($sourceDir.Length).TrimStart("\", "/")
}

function Write-ZipProgress {
    param(
        [Parameter(Mandatory = $true)][int]$Current,
        [Parameter(Mandatory = $true)][int]$Total,
        [Parameter(Mandatory = $true)][string]$Activity,
        [string]$CurrentFile = ""
    )

    if ($Total -le 0) {
        return
    }

    $percent = [math]::Min(100, [math]::Floor(($Current / $Total) * 100))
    $barWidth = 32
    $filled = [math]::Floor(($percent / 100) * $barWidth)
    $bar = ("#" * $filled).PadRight($barWidth, "-")
    $status = ("[{0}] {1,3}% ({2}/{3})" -f $bar, $percent, $Current, $Total)

    Write-Progress -Activity $Activity -Status $status -PercentComplete $percent -CurrentOperation $CurrentFile
    Write-Host -NoNewline ("`r{0} {1}" -f $Activity, $status)
}

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::Open($zipPath, [System.IO.Compression.ZipArchiveMode]::Create)
try {
    Write-Host "Dateien werden vorbereitet..."
    $files = Get-ChildItem -LiteralPath $sourceDir -Recurse -File -Force | Where-Object {
        $relative = Get-ReleaseRelativePath -FullName $_.FullName
        -not (Test-ExcludedPath -RelativePath $relative -IsDirectory:$false)
    } | Sort-Object FullName

    $total = @($files).Count
    if ($total -eq 0) {
        throw "Keine Dateien zum Zippen gefunden."
    }

    Write-Host ("Starte ZIP mit {0} Dateien..." -f $total)

    $index = 0
    foreach ($file in $files) {
        $index++
        $relative = (Get-ReleaseRelativePath -FullName $file.FullName).Replace("\", "/")
        Write-ZipProgress -Current $index -Total $total -Activity "ZIP wird erstellt" -CurrentFile $relative
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $file.FullName, $relative, [System.IO.Compression.CompressionLevel]::Optimal) | Out-Null
    }

    Write-Progress -Activity "ZIP wird erstellt" -Completed
    Write-Host ""
}
finally {
    $zip.Dispose()
}

$sizeMb = [math]::Round((Get-Item -LiteralPath $zipPath).Length / 1MB, 2)
Write-Host "ZIP erstellt:"
Write-Host $zipPath
Write-Host "Quelle: $sourceDir"
Write-Host "Version: $version"
Write-Host "Groesse: $sizeMb MB"
Write-Host "Ausgeschlossen: persoenliche data-Inhalte, lokale Profile, Secrets, Logs und Diagnose-Dateien."
