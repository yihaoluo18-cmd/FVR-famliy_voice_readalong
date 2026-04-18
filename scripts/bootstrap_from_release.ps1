param(
    [Parameter(Mandatory = $true)]
    [string]$Repo,
    [Parameter(Mandatory = $true)]
    [string]$Tag,
    [string]$TargetRoot = ".",
    [string[]]$GptPartAssets = @("GPT_SoVITS_part01.zip", "GPT_SoVITS_part02.zip", "GPT_SoVITS_part03.zip", "GPT_SoVITS_part04.zip"),
    [string]$AssetsAssetName = "assets_release.zip",
    [switch]$SkipStart
)

$ErrorActionPreference = "Stop"

function Download-Asset {
    param(
        [string]$Url,
        [string]$OutFile
    )
    Write-Host "Downloading: $Url"
    Invoke-WebRequest -Uri $Url -OutFile $OutFile -UseBasicParsing
}

function Extract-Zip {
    param(
        [string]$ZipPath,
        [string]$DestinationPath
    )
    if (Test-Path $DestinationPath) {
        Write-Host "Removing existing directory: $DestinationPath"
        Remove-Item $DestinationPath -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $DestinationPath | Out-Null
    Expand-Archive -Path $ZipPath -DestinationPath $DestinationPath -Force
}

$root = (Resolve-Path $TargetRoot).Path
$tmpDir = Join-Path $root ".release_tmp"
New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null

$baseUrl = "https://github.com/$Repo/releases/download/$Tag"
$assetsZip = Join-Path $tmpDir $AssetsAssetName

Download-Asset -Url "$baseUrl/$AssetsAssetName" -OutFile $assetsZip
foreach ($partName in $GptPartAssets) {
    Download-Asset -Url "$baseUrl/$partName" -OutFile (Join-Path $tmpDir $partName)
}

foreach ($partName in $GptPartAssets) {
    $partZip = Join-Path $tmpDir $partName
    if (-not (Test-Path $partZip)) {
        throw "Missing GPT part: $partName"
    }
}

$gptDest = Join-Path $root "GPT_SoVITS"
if (Test-Path $gptDest) {
    Write-Host "Removing existing directory: $gptDest"
    Remove-Item $gptDest -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $gptDest | Out-Null

foreach ($partName in $GptPartAssets) {
    $partZip = Join-Path $tmpDir $partName
    Write-Host "Extracting part: $partName"
    Expand-Archive -Path $partZip -DestinationPath $gptDest -Force
}

Extract-Zip -ZipPath $assetsZip -DestinationPath (Join-Path $root "assets")

Remove-Item $tmpDir -Recurse -Force

Write-Host "Bootstrap completed."
Write-Host "Generated directories:"
Write-Host " - $(Join-Path $root 'GPT_SoVITS')"
Write-Host " - $(Join-Path $root 'assets')"

if (-not $SkipStart) {
    $startScript = Join-Path $root "start_wx_api.sh"
    if (Test-Path $startScript) {
        Write-Host "Found start script: $startScript"
        Write-Host "Please run it with Git Bash: bash ./start_wx_api.sh"
    } else {
        Write-Host "start_wx_api.sh not found. Start service manually."
    }
}
