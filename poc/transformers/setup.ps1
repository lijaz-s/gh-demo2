param([switch]$WithActionlint)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv .venv
    } else {
        & python -m venv .venv
    }
    if ($LASTEXITCODE -ne 0) { throw 'Python venv creation failed. Install Python 3.11+ with pip/venv.' }
}
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }

if (-not $WithActionlint) {
    Write-Output 'Transformer ready. Run: .\.venv\Scripts\python.exe .\transform.py'
    Write-Output 'Optional validator: rerun setup.ps1 -WithActionlint'
    exit 0
}

$actionlintVersion = '1.7.12'
$assetName = "actionlint_${actionlintVersion}_windows_amd64.zip"
$checksumName = "actionlint_${actionlintVersion}_checksums.txt"
$releaseBase = "https://github.com/rhysd/actionlint/releases/download/v$actionlintVersion"
New-Item -ItemType Directory -Force -Path tools | Out-Null
Invoke-WebRequest -UseBasicParsing -Uri "$releaseBase/$assetName" -OutFile "tools\$assetName"
Invoke-WebRequest -UseBasicParsing -Uri "$releaseBase/$checksumName" -OutFile "tools\$checksumName"
$actual = (Get-FileHash -Algorithm SHA256 -LiteralPath "tools\$assetName").Hash.ToLower()
$expectedLine = @(Get-Content -LiteralPath "tools\$checksumName" | Where-Object { $_ -match ([regex]::Escape($assetName) + '$') })
if ($expectedLine.Count -ne 1 -or -not $expectedLine[0].StartsWith($actual)) { throw 'actionlint checksum mismatch.' }
Expand-Archive -LiteralPath "tools\$assetName" -DestinationPath tools -Force
Write-Output 'Transformer and optional actionlint ready. All files are local to this directory.'
exit 0
