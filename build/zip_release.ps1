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

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::Open($zipPath, [System.IO.Compression.ZipArchiveMode]::Create)
try {
    $files = Get-ChildItem -LiteralPath $sourceDir -Recurse -File -Force | Where-Object {
        $relative = Get-ReleaseRelativePath -FullName $_.FullName
        -not (Test-ExcludedPath -RelativePath $relative -IsDirectory:$false)
    }

    foreach ($file in $files) {
        $relative = (Get-ReleaseRelativePath -FullName $file.FullName).Replace("\", "/")
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $file.FullName, $relative, [System.IO.Compression.CompressionLevel]::Optimal) | Out-Null
    }
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
