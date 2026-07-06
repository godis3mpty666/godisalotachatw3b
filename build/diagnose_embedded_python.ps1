[CmdletBinding()]
param(
    [string]$AppDirectory = ''
)

$ErrorActionPreference = 'Continue'
if ([string]::IsNullOrWhiteSpace($AppDirectory)) {
    $AppDirectory = $PSScriptRoot
}
$root = (Resolve-Path -LiteralPath $AppDirectory).Path
$exe = Join-Path $root 'webbased.exe'
$internal = Join-Path $root '_internal'
$pythonDll = Join-Path $internal 'python313.dll'
$report = Join-Path $root 'startup_diagnose.txt'

Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class NativeLoaderDiagnostic {
    [DllImport("kernel32.dll", SetLastError=true, CharSet=CharSet.Unicode)]
    public static extern bool SetDllDirectory(string lpPathName);

    [DllImport("kernel32.dll", SetLastError=true, CharSet=CharSet.Unicode)]
    public static extern IntPtr LoadLibraryEx(string lpFileName, IntPtr hFile, uint dwFlags);

    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool FreeLibrary(IntPtr hModule);
}
'@

$lines = [System.Collections.Generic.List[string]]::new()
function Add-Line([string]$Text) {
    $lines.Add($Text)
    Write-Host $Text
}

Add-Line ('Zeit: ' + (Get-Date -Format o))
Add-Line ('Windows: ' + [Environment]::OSVersion.VersionString)
Add-Line ('64-Bit Windows: ' + [Environment]::Is64BitOperatingSystem)
Add-Line ('64-Bit PowerShell: ' + [Environment]::Is64BitProcess)
Add-Line ('Ordner: ' + $root)
Add-Line ('EXE vorhanden: ' + (Test-Path -LiteralPath $exe -PathType Leaf))
Add-Line ('python313.dll vorhanden: ' + (Test-Path -LiteralPath $pythonDll -PathType Leaf))

foreach ($path in @($exe, $pythonDll)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { continue }
    $item = Get-Item -LiteralPath $path
    $hash = Get-FileHash -LiteralPath $path -Algorithm SHA256
    Add-Line (('{0}: {1} Bytes; SHA256 {2}') -f $item.Name, $item.Length, $hash.Hash)
    $zone = Get-Content -LiteralPath ($path + ':Zone.Identifier') -ErrorAction SilentlyContinue
    Add-Line (($item.Name + ' Downloadmarkierung: ') + $(if ($zone) { ($zone -join '; ') } else { 'keine' }))
}

if (Test-Path -LiteralPath $exe -PathType Leaf) {
    $signature = Get-AuthenticodeSignature -LiteralPath $exe
    Add-Line ('EXE-Signaturstatus: ' + $signature.Status)
    Add-Line ('EXE-Signaturmeldung: ' + $signature.StatusMessage)
}

if (Test-Path -LiteralPath $pythonDll -PathType Leaf) {
    [void][NativeLoaderDiagnostic]::SetDllDirectory($internal)
    $module = [NativeLoaderDiagnostic]::LoadLibraryEx($pythonDll, [IntPtr]::Zero, 8)
    if ($module -eq [IntPtr]::Zero) {
        $code = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
        $message = ([ComponentModel.Win32Exception]::new($code)).Message
        Add-Line ("LOAD FAILED: Windows-Fehler $code - $message")
    } else {
        Add-Line 'LOAD OK: python313.dll und ihre direkten Abhängigkeiten konnten geladen werden.'
        [void][NativeLoaderDiagnostic]::FreeLibrary($module)
    }
}

$lines | Set-Content -LiteralPath $report -Encoding utf8
Add-Line ('Bericht: ' + $report)
