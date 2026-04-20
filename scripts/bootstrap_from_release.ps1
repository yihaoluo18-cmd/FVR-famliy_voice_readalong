# One-click bootstrap: downloads GPT_SoVITS_part*.zip, assets_release.zip, and (if present on the release)
# optional fvr_deploy_output.zip into ./output. Use -SkipDeployOutput to skip the output bundle.
param(
    [Parameter(Mandatory = $true)]
    [string]$Repo,
    [Parameter(Mandatory = $true)]
    [string]$Tag,
    [string]$TargetRoot = ".",
    [string[]]$GptPartAssets = @("GPT_SoVITS_part01.zip", "GPT_SoVITS_part02.zip", "GPT_SoVITS_part03.zip", "GPT_SoVITS_part04.zip"),
    [string]$AssetsAssetName = "assets_release.zip",
    [string]$OutputAssetName = "fvr_deploy_output.zip",
    [switch]$SkipDeployOutput,
    [switch]$SkipStart
)

$ErrorActionPreference = "Stop"

function Download-Asset {
    param(
        [string]$Url,
        [string]$OutFile
    )
    Write-Host "Downloading: $Url"

    # Avoid extremely slow progress rendering for large files
    $oldProgress = $global:ProgressPreference
    $global:ProgressPreference = "SilentlyContinue"
    try {
        $tmpOut = "$OutFile.download"
        foreach ($p in @($OutFile, $tmpOut)) {
            if (Test-Path $p) {
                Remove-Item -Force $p -ErrorAction SilentlyContinue
            }
        }

        # Prefer BITS for large GitHub assets (resume/retry friendly)
        if (Get-Command Start-BitsTransfer -ErrorAction SilentlyContinue) {
            Start-BitsTransfer -Source $Url -Destination $tmpOut -ErrorAction Stop
            Move-Item -Force $tmpOut $OutFile
            return
        }

        # Fallback to curl.exe (NOT the PowerShell curl alias)
        $curl = (Get-Command curl.exe -ErrorAction SilentlyContinue).Source
        if ($curl) {
            & $curl -fL $Url -o $tmpOut
            Move-Item -Force $tmpOut $OutFile
            return
        }

        # Last resort
        Invoke-WebRequest -Uri $Url -OutFile $tmpOut -UseBasicParsing
        Move-Item -Force $tmpOut $OutFile
    }
    finally {
        $global:ProgressPreference = $oldProgress
    }
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

$outputZip = Join-Path $tmpDir $OutputAssetName
$outputDownloaded = $false
if (-not $SkipDeployOutput) {
    try {
        Write-Host "Downloading optional release asset: $OutputAssetName"
        Download-Asset -Url "$baseUrl/$OutputAssetName" -OutFile $outputZip
        if (Test-Path $outputZip) {
            $outputDownloaded = $true
        }
    }
    catch {
        Write-Host "WARN: Optional asset $OutputAssetName is not on this release or download failed. Skipping ./output. ($($_.Exception.Message))"
    }
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

if ($outputDownloaded) {
    $outputDir = Join-Path $root "output"
    if (Test-Path $outputDir) {
        Write-Host "Removing existing directory: $outputDir"
        Remove-Item $outputDir -Recurse -Force
    }
    Write-Host "Extracting: $OutputAssetName -> ./output"
    Expand-Archive -Path $outputZip -DestinationPath $root -Force
}

Remove-Item $tmpDir -Recurse -Force

Write-Host "Bootstrap completed."
Write-Host "Generated directories:"
Write-Host " - $(Join-Path $root 'GPT_SoVITS')"
Write-Host " - $(Join-Path $root 'assets')"
if ($outputDownloaded) {
    Write-Host " - $(Join-Path $root 'output')"
}

if (-not $SkipStart) {
    $startScript = Join-Path $root "start_wx_api.sh"
    if (Test-Path $startScript) {
        Write-Host "Found start script: $startScript"
        Write-Host "Please run it with Git Bash: bash ./start_wx_api.sh"
    }
    else {
        Write-Host "start_wx_api.sh not found. Start service manually."
    }
}
