param(
    [switch]$NoDraft,
    [string]$TagName = "",
    [string]$BlenderTarget = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$catalogPath = Join-Path $projectRoot "release\packages.json"
$catalog = Get-Content -Raw $catalogPath | ConvertFrom-Json
$targetPath = Join-Path $projectRoot "release\blender-target.txt"
if (-not $BlenderTarget) {
    $BlenderTarget = (Get-Content -Raw $targetPath).Trim()
}
$today = Get-Date -Format "yyyy.MM.dd"
if (-not $TagName) { $TagName = "release-$today" }

$previousTag = (& git -C $projectRoot tag --sort=-creatordate | Where-Object { $_ -ne $TagName } | Select-Object -First 1)
$changedFiles = @()
if ($previousTag) {
    $changedFiles = @(& git -C $projectRoot diff --name-only "$previousTag..HEAD")
}

$allIds = @($catalog.packages | Where-Object { $_.status -eq "stable" } | ForEach-Object { $_.id })
$changedIds = @()
if (-not $latestTag) {
    $changedIds = $allIds
}
else {
    foreach ($package in $catalog.packages | Where-Object { $_.status -eq "stable" }) {
        if ($changedFiles | Where-Object { $_ -like "$($package.source)/*" }) {
            $changedIds += $package.id
        }
    }
    if ($changedFiles | Where-Object { $_ -like "addons/*/embedded_host/*" -or $_ -like "scripts/make_zip.ps1" -or $_ -like "release/packages.json" -or $_ -like "release/blender-target.txt" }) {
        $changedIds = $allIds
    }
}

$suiteChanged = ($changedIds.Count -gt 0) -or ($changedFiles | Where-Object { $_ -eq "__init__.py" -or $_ -like "scripts/*" })
if ($changedIds.Count -eq 0 -and -not $suiteChanged) {
    Write-Host "No releasable package changes detected."
    exit 0
}

$buildArgs = @(
    "-ExecutionPolicy", "Bypass", "-File", (Join-Path $projectRoot "scripts\make_zip.ps1"),
    "-PackageIds"
) + $changedIds
if ($suiteChanged) {
    $buildArgs += @("-SuitePackageIds") + $allIds
}
else {
    $buildArgs += "-SkipSuite"
}
& powershell @buildArgs
if ($LASTEXITCODE -ne 0) { throw "ZIP build failed." }

$distDir = Join-Path $projectRoot "dist"
$releaseDir = Join-Path $distDir "release"
if (Test-Path $releaseDir) { Remove-Item $releaseDir -Recurse -Force }
New-Item -ItemType Directory -Path $releaseDir | Out-Null

$manifestPackages = @()
foreach ($package in $catalog.packages | Where-Object { $_.status -eq "stable" }) {
    $init = Get-Content -Raw (Join-Path $projectRoot "$($package.source)\__init__.py")
    $match = [regex]::Match($init, '"version"\s*:\s*\(([^)]*)\)')
    if (-not $match.Success) { throw "Version not found for $($package.id)" }
    $versionParts = @($match.Groups[1].Value -split ',' | ForEach-Object { [int]$_.Trim() } | Where-Object { $_ -ne $null })
    $version = "{0:D4}.{1:D2}.{2:D2}" -f $versionParts[0], $versionParts[1], $versionParts[2]
    $changed = $changedIds -contains $package.id
    $file = $null
    if ($changed) {
        $sourceZip = Join-Path $distDir "$($package.id).zip"
        $file = "$($package.id)-$version-blender$BlenderTarget.zip"
        Copy-Item $sourceZip (Join-Path $releaseDir $file) -Force
    }
    $manifestPackages += [ordered]@{
        id = $package.id
        version = $version
        group_id = $package.group_id
        group_label = $package.group_label
        blender_target = $BlenderTarget
        changed = $changed
        file = $file
    }
}

$suiteFile = $null
if ($suiteChanged) {
    $suiteFile = "blender_addon_suite-$today-blender$BlenderTarget.zip"
    Copy-Item (Join-Path $distDir "blender_addon_suite.zip") (Join-Path $releaseDir $suiteFile) -Force
}

$manifest = [ordered]@{
    release = $TagName
    generated_at = (Get-Date).ToString("s")
    blender_target = $BlenderTarget
    suite = [ordered]@{ changed = [bool]$suiteChanged; file = $suiteFile }
    packages = $manifestPackages
}
$manifestPath = Join-Path $releaseDir "release-manifest.json"
$manifest | ConvertTo-Json -Depth 8 | Set-Content $manifestPath -Encoding utf8

$body = @("## Changed", "")
if ($suiteChanged) { $body += "- blender_addon_suite ($today)" }
foreach ($item in $manifestPackages | Where-Object { $_.changed }) { $body += "- $($item.id) $($item.version)" }
$body += "", "## Included Downloads", "", "- GitHub Pages contains the current download index.", "", "## Compared With", "", $(if ($previousTag) { "- $previousTag" } else { "- No previous release tag found" })
$bodyPath = Join-Path $releaseDir "release-body.md"
$body | Set-Content $bodyPath -Encoding utf8

if (-not $NoDraft) {
    $gh = Get-Command gh -ErrorAction SilentlyContinue
    if (-not $gh) { throw "GitHub CLI 'gh' is required to create a Draft Release. Assets are in $releaseDir." }
    $env:GH_PROMPT_DISABLED = "true"
    $existing = (& gh release view $TagName --json isDraft --jq ".isDraft" 2>$null)
    if ($existing -eq "false") {
        Write-Host "Today's release is already published; deferring additional changes to the next day."
        exit 0
    }
    $assets = @(Get-ChildItem $releaseDir -File | ForEach-Object { $_.FullName })
    if ($existing -eq "true") {
        & gh release upload $TagName @assets --clobber
        & gh release edit $TagName --title $TagName --notes-file $bodyPath
    }
    else {
        & gh release create $TagName --draft --title $TagName --notes-file $bodyPath @assets
    }
}

Write-Host "Release assets: $releaseDir"
