param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^10\.\d{4,9}/.+$')]
    [string]$Doi
)

$ErrorActionPreference = "Stop"
$tag = "paper-v$Version"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    $python = (Get-Command python -ErrorAction Stop).Source
}

& $python (Join-Path $PSScriptRoot "finalize_submission.py") `
    --tag $tag --version $Version --doi $Doi --preflight
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& (Join-Path $PSScriptRoot "build_preprint.ps1") -Tag $tag -Version $Version -Doi $Doi
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $python (Join-Path $PSScriptRoot "finalize_submission.py") `
    --tag $tag --version $Version --doi $Doi
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $python (Join-Path $PSScriptRoot "finalize_submission.py") `
    --tag $tag --version $Version --doi $Doi --check
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
