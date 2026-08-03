param(
    [string[]]$PackageIds = @(),
    [string[]]$SuitePackageIds = @(),
    [switch]$IncludeAll,
    [switch]$SkipSuite
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$distDir = Join-Path $projectRoot "dist"
$buildDir = Join-Path $projectRoot "build"
$catalogPath = Join-Path $projectRoot "release\packages.json"
$catalog = Get-Content -Raw $catalogPath | ConvertFrom-Json

function Remove-Directory([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}

Remove-Directory $distDir
Remove-Directory $buildDir
New-Item -ItemType Directory -Path $distDir | Out-Null
New-Item -ItemType Directory -Path $buildDir | Out-Null

$selected = @($catalog.packages | Where-Object {
    $IncludeAll -or $PackageIds.Count -eq 0 -or $PackageIds -contains $_.id
} | Where-Object { $_.status -eq "stable" })
if (-not $selected) {
    throw "No stable packages selected."
}

$suiteSelected = $selected
if ($SuitePackageIds.Count -gt 0) {
    $suiteSelected = @($catalog.packages | Where-Object {
        $_.status -eq "stable" -and $SuitePackageIds -contains $_.id
    })
}
if (-not $SkipSuite -and -not $suiteSelected) {
    throw "No stable packages selected for the suite."
}

if (-not $SkipSuite) {
    $suiteDir = Join-Path $buildDir "blender_addon_suite"
    New-Item -ItemType Directory -Path (Join-Path $suiteDir "addons") -Force | Out-Null
    Copy-Item (Join-Path $projectRoot "__init__.py") $suiteDir
    Copy-Item (Join-Path $projectRoot "addons\__init__.py") (Join-Path $suiteDir "addons")
    foreach ($package in $suiteSelected) {
        $source = Join-Path $projectRoot $package.source
        Copy-Item $source (Join-Path $suiteDir "addons") -Recurse -Force
    }
    Compress-Archive -Path $suiteDir -DestinationPath (Join-Path $distDir "blender_addon_suite.zip") -Force
}

foreach ($package in $selected) {
    $source = Join-Path $projectRoot $package.source
    $packageDir = Join-Path $buildDir $package.id
    Copy-Item $source $packageDir -Recurse -Force
    Compress-Archive -Path $packageDir -DestinationPath (Join-Path $distDir "$($package.id).zip") -Force
}

Remove-Directory $buildDir
Get-ChildItem $distDir -Filter "*.zip" | ForEach-Object { Write-Host $_.FullName }
