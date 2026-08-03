param(
    [Parameter(Mandatory = $true)]
    [string]$Version,
    [string]$InstallRoot = (Join-Path $PSScriptRoot "..\.blender-cache")
)

$ErrorActionPreference = "Stop"
$releaseDirectory = "Blender$Version"
$html = (Invoke-WebRequest -Uri "https://download.blender.org/release/$releaseDirectory/" -UseBasicParsing).Content
$escaped = [regex]::Escape($Version)
$downloadNames = [regex]::Matches($html, "blender-$escaped\.\d+-windows-x64\.zip") |
    ForEach-Object { $_.Value } | Sort-Object -Unique
$downloadName = $downloadNames | Sort-Object {
    if ($_ -match 'blender-(\d+\.\d+\.\d+)-windows-x64\.zip') {
        [version]$Matches[1]
    }
    else {
        [version]"0.0.0"
    }
} | Select-Object -Last 1
if (-not $downloadName) { throw "No Blender build found for $Version" }
$root = New-Item -ItemType Directory -Force -Path $InstallRoot
$zip = Join-Path $root $downloadName
if (-not (Test-Path $zip)) { Invoke-WebRequest -Uri "https://download.blender.org/release/$releaseDirectory/$downloadName" -OutFile $zip }
$extract = Join-Path $root ([IO.Path]::GetFileNameWithoutExtension($downloadName))
if (-not (Test-Path $extract)) { Expand-Archive $zip -DestinationPath $root -Force }
$exe = Get-ChildItem $extract -Recurse -Filter blender.exe | Select-Object -First 1
if (-not $exe) { throw "blender.exe was not found" }
if ($env:GITHUB_PATH) { (Split-Path $exe.FullName) | Out-File $env:GITHUB_PATH -Append -Encoding utf8 }
