# Optional Windows x64 actionlint installation.
$ErrorActionPreference = 'Stop'
$version = '1.7.12'
$destination = Join-Path $PSScriptRoot 'tools'
New-Item -ItemType Directory -Force -Path $destination | Out-Null
$archive = "actionlint_${version}_windows_amd64.zip"
$base = "https://github.com/rhysd/actionlint/releases/download/v$version"
Invoke-WebRequest -UseBasicParsing "$base/$archive" -OutFile (Join-Path $destination $archive)
Invoke-WebRequest -UseBasicParsing "$base/actionlint_${version}_checksums.txt" -OutFile (Join-Path $destination 'checksums.txt')
$hash = (Get-FileHash (Join-Path $destination $archive)).Hash.ToLower()
$expected = @(Get-Content (Join-Path $destination 'checksums.txt') | Where-Object { $_ -match ([regex]::Escape($archive) + '$') })
if ($expected.Count -ne 1 -or -not $expected[0].StartsWith($hash)) { throw 'Download checksum mismatch.' }
Expand-Archive -LiteralPath (Join-Path $destination $archive) -DestinationPath $destination -Force
Write-Output 'Installed actionlint. Run transformer-wrapper/compare.ps1 separately.'
