# Run from any directory. Ruby is supplied by the importer image.
param([ValidateSet('Both','Baseline','Modified')][string]$Mode = 'Both')
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $repoRoot
try {
    foreach ($tool in @('gh','docker')) {
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "Install $tool first." }
    }
    $image = 'ghcr.io/actions-importer/cli:latest'
    $runId = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
    $scratch = ".work/importer-$runId"
    New-Item -ItemType Directory -Force -Path $scratch,Outputs\baseline,Outputs\modified | Out-Null
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    $digest = & docker image inspect $image --format '{{index .RepoDigests 0}}'
    if ($LASTEXITCODE -ne 0) { throw 'Importer image missing. Run gh actions-importer update.' }
    $version = (& gh actions-importer version | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Install/configure the Actions Importer extension first.' }
    foreach ($arm in @('baseline','modified')) {
        if ($Mode -ne 'Both' -and $Mode.ToLower() -ne $arm) { continue }
        $importerArguments = @('actions-importer','dry-run','gitlab','--namespace','lijazsalim','--project','simple-maven-app','--output-dir',"$scratch/$arm",'--no-telemetry')
        if ($arm -eq 'modified') { $importerArguments += @('--custom-transformers','transformer-wrapper/transformers/maven.rb') }
        Write-Output "Running Actions Importer: $arm"
        & gh @importerArguments *> "$scratch/$arm-console.log"
        if ($LASTEXITCODE -ne 0) { throw "Importer failed. Inspect $scratch/$arm-console.log locally." }
        $generated = "$scratch/$arm/lijazsalim/simple-maven-app/.github/workflows/simple-maven-app.yml"
        if (-not (Test-Path -LiteralPath $generated)) { throw 'Importer did not produce the expected workflow.' }
        $metadata = [ordered]@{
            generated_utc = [DateTime]::UtcNow.ToString('o')
            importer_version = $version
            importer_image = $digest.Trim()
            source_project = 'https://gitlab.com/lijazsalim/simple-maven-app'
            source_mode = 'Live GitLab project, including project settings; not a local YAML-only conversion'
            native_transformers = ($arm -eq 'modified')
            raw_output_sha256 = (Get-FileHash -LiteralPath $generated).Hash.ToLower()
            local_reference_source_sha256 = (Get-FileHash -LiteralPath simple-maven-app/.gitlab-ci.yml).Hash.ToLower()
            hosted_execution = 'not-run'
        }
        if ($arm -eq 'baseline') {
            Copy-Item -LiteralPath $generated -Destination Outputs/baseline/simple-maven-app.yml -Force
        } else {
            # Importer can exit 0 after a custom-hook error. Guard the actual output before publication.
            & docker run --rm --network none --mount "type=bind,source=$repoRoot,target=/work" -w /work --entrypoint ruby $image transformer-wrapper/postprocess.rb $generated "$scratch/final.yml"
            if ($LASTEXITCODE -ne 0) { throw 'Native output did not satisfy compatibility preconditions. Existing modified outputs were not replaced.' }
            Copy-Item -LiteralPath $generated -Destination Outputs/modified/native.yml -Force
            Copy-Item -LiteralPath "$scratch/final.yml" -Destination Outputs/modified/simple-maven-app.yml -Force
            $metadata['transformer_sha256'] = (Get-FileHash transformer-wrapper/transformers/maven.rb).Hash.ToLower()
            $metadata['postprocessor_sha256'] = (Get-FileHash transformer-wrapper/postprocess.rb).Hash.ToLower()
            $metadata['final_sha256'] = (Get-FileHash Outputs/modified/simple-maven-app.yml).Hash.ToLower()
            $metadata['postprocessing'] = @('Escape the known job condition','Remove the old job container after native Docker-step conversion')
        }
        # Regenerating either side invalidates the previously recorded comparison.
        if (Test-Path Outputs/modified/comparison.md) {
            [IO.File]::WriteAllText((Join-Path $repoRoot 'Outputs/modified/comparison.md'), 'Outputs regenerated. Run transformer-wrapper/compare.ps1 to refresh validation.', $utf8)
        }
        [IO.File]::WriteAllText((Join-Path $repoRoot "Outputs/$arm/provenance.json"), ($metadata | ConvertTo-Json -Depth 5), $utf8)
        Write-Output "Published Outputs/$arm (no validation or comparison run)."
    }
} finally { Pop-Location }
