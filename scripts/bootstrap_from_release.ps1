# One-click bootstrap: downloads GPT_SoVITS_part*.zip, assets_release.zip, and (if present on the release)
# optional fvr_deploy_output.zip into ./output. Use -SkipDeployOutput to skip the output bundle.
#
# Asset hosts (default: GitHub Release only):
#   FVR_ASSET_BASE_URLS      Semicolon-separated base URLs (no trailing slash). If set, ONLY these are used
#                            (e.g. Hugging Face dataset resolve URL). Put multiple for failover order.
#   FVR_ASSET_EXTRA_BASE_URLS When FVR_ASSET_BASE_URLS is unset, try GitHub first, then each extra base.
#   HF_TOKEN                 Optional; for private HF repos, sent as Authorization: Bearer (curl/IWR only).
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

function Split-AssetBaseUrls([string]$Raw) {
    if (-not $Raw) { return @() }
    return @(
        $Raw -split ';' |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ }
    )
}

function Get-AuthHeadersForDownload {
    $t = $env:HF_TOKEN
    if ($t -and $t.Trim()) {
        return @{ Authorization = "Bearer $($t.Trim())" }
    }
    return $null
}

function Download-Asset {
    param(
        [string]$Url,
        [string]$OutFile
    )
    Write-Host "Downloading: $Url"

    $authHeaders = Get-AuthHeadersForDownload
    $needAuth = $null -ne $authHeaders

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

        # Prefer BITS for large assets (no custom headers)
        if (-not $needAuth -and (Get-Command Start-BitsTransfer -ErrorAction SilentlyContinue)) {
            Start-BitsTransfer -Source $Url -Destination $tmpOut -ErrorAction Stop
            Move-Item -Force $tmpOut $OutFile
            return
        }

        # curl.exe supports Authorization (HF private / gated)
        $curl = (Get-Command curl.exe -ErrorAction SilentlyContinue).Source
        if ($curl) {
            if ($needAuth) {
                $bt = $env:HF_TOKEN.Trim()
                & $curl -fL -H "Authorization: Bearer $bt" -o $tmpOut -- $Url
            }
            else {
                & $curl -fL $Url -o $tmpOut
            }
            Move-Item -Force $tmpOut $OutFile
            return
        }

        if ($needAuth) {
            Invoke-WebRequest -Uri $Url -OutFile $tmpOut -UseBasicParsing -Headers $authHeaders
        }
        else {
            Invoke-WebRequest -Uri $Url -OutFile $tmpOut -UseBasicParsing
        }
        Move-Item -Force $tmpOut $OutFile
    }
    finally {
        $global:ProgressPreference = $oldProgress
    }
}

function Download-Asset-FromBases {
    param(
        [string[]]$Bases,
        [string]$FileName,
        [string]$OutFile,
        [switch]$Optional
    )
    $lastErr = $null
    foreach ($b in $Bases) {
        $base = ($b -replace '/$', '')
        if (-not $base) { continue }
        $url = "$base/$FileName"
        try {
            Download-Asset -Url $url -OutFile $OutFile
            return $true
        }
        catch {
            $lastErr = $_
            Write-Host "WARN: $FileName failed from $base — $($_.Exception.Message)"
            foreach ($p in @($OutFile, "$OutFile.download")) {
                if (Test-Path $p) { Remove-Item -Force $p -ErrorAction SilentlyContinue }
            }
        }
    }
    if ($Optional) {
        return $false
    }
    throw "Could not download $FileName from any base. Last error: $lastErr"
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

$githubBase = "https://github.com/$Repo/releases/download/$Tag"
$assetBases = @($githubBase)
if ($env:FVR_ASSET_BASE_URLS -and $env:FVR_ASSET_BASE_URLS.Trim()) {
    $assetBases = @(Split-AssetBaseUrls $env:FVR_ASSET_BASE_URLS)
    if ($assetBases.Count -eq 0) {
        throw "FVR_ASSET_BASE_URLS is set but no non-empty base URL after parsing."
    }
    Write-Host "Using FVR_ASSET_BASE_URLS ($($assetBases.Count) base(s)) for downloads."
}
elseif ($env:FVR_ASSET_EXTRA_BASE_URLS -and $env:FVR_ASSET_EXTRA_BASE_URLS.Trim()) {
    $extras = @(Split-AssetBaseUrls $env:FVR_ASSET_EXTRA_BASE_URLS)
    $assetBases = @($githubBase) + $extras
    Write-Host "Using GitHub + $($extras.Count) fallback base(s) from FVR_ASSET_EXTRA_BASE_URLS."
}
else {
    Write-Host "Using GitHub Release: $githubBase"
}

$assetsZip = Join-Path $tmpDir $AssetsAssetName
Download-Asset-FromBases -Bases $assetBases -FileName $AssetsAssetName -OutFile $assetsZip

foreach ($partName in $GptPartAssets) {
    Download-Asset-FromBases -Bases $assetBases -FileName $partName -OutFile (Join-Path $tmpDir $partName)
}

$outputZip = Join-Path $tmpDir $OutputAssetName
$outputDownloaded = $false
if (-not $SkipDeployOutput) {
    Write-Host "Downloading optional release asset: $OutputAssetName"
    $outputDownloaded = Download-Asset-FromBases -Bases $assetBases -FileName $OutputAssetName -OutFile $outputZip -Optional
    if (-not $outputDownloaded) {
        Write-Host "WARN: Optional asset $OutputAssetName missing or failed on all bases. Skipping ./output."
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
