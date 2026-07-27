param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^paper-v\d+\.\d+\.\d+$')]
    [string]$Tag,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version,

    [string]$Doi = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$buildRoot = Join-Path $projectRoot "paper\release-build"
$packageRoot = Join-Path $buildRoot "v$Version"
$htmlPath = Join-Path $packageRoot "when-aggregate-accuracy-is-not-enough-v$Version.html"
$pdfPath = Join-Path $packageRoot "when-aggregate-accuracy-is-not-enough-v$Version.pdf"
$manifestPath = Join-Path $packageRoot "release-artifact-manifest-v$Version.json"

if ($Tag -ne "paper-v$Version") {
    throw "tag/version mismatch: expected paper-v$Version"
}
New-Item -ItemType Directory -Path $packageRoot -Force | Out-Null

$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    $python = (Get-Command python -ErrorAction Stop).Source
}

& $python (Join-Path $PSScriptRoot "render_preprint.py") --tag $Tag --output $htmlPath
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$chromeCandidates = @(
    "C:\Program Files\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
)
$chrome = $chromeCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $chrome) {
    throw "Chrome or Edge is required to render the PDF"
}

$htmlUri = ([Uri]$htmlPath).AbsoluteUri
if (Test-Path -LiteralPath $pdfPath) {
    Remove-Item -LiteralPath $pdfPath -Force
}
& $chrome --headless --disable-gpu --hide-scrollbars --no-pdf-header-footer "--print-to-pdf=$pdfPath" $htmlUri
$deadline = (Get-Date).AddSeconds(30)
do {
    if (Test-Path -LiteralPath $pdfPath) {
        $pdfLength = (Get-Item -LiteralPath $pdfPath).Length
        if ($pdfLength -gt 10000) { break }
    }
    Start-Sleep -Milliseconds 250
} while ((Get-Date) -lt $deadline)
if (-not (Test-Path -LiteralPath $pdfPath) -or (Get-Item -LiteralPath $pdfPath).Length -le 10000) {
    throw "browser PDF rendering failed"
}

& $python (Join-Path $PSScriptRoot "harden_pdf.py") --tag $Tag --pdf $pdfPath
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$commit = (git -C $projectRoot rev-list -n 1 $Tag).Trim()
$files = foreach ($path in $htmlPath, $pdfPath) {
    $item = Get-Item -LiteralPath $path
    [ordered]@{
        name = $item.Name
        bytes = $item.Length
        sha256 = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
$manifest = [ordered]@{
    artifact_version = "1.0.0"
    paper_version = $Version
    source_tag = $Tag
    source_commit = $commit
    reserved_doi = $Doi
    evidence_boundary = "validation_only_causal_design_not_conducted"
    pdf_metadata_time = "normalized_to_source_commit"
    files = @($files)
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding utf8

Write-Output $htmlPath
Write-Output $pdfPath
Write-Output $manifestPath
