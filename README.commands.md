# Commands: GitHub Actions Importer and native transformers

Run these commands in PowerShell from this repository's root. Docker Desktop must be running Linux containers. Git, GitHub CLI, and the Actions Importer extension are required. Ruby is supplied by the importer container.

## Initial setup

On a new machine:

```powershell
git clone --recurse-submodules https://github.com/LijazS/gh-demo2.git
Set-Location gh-demo2
```

For an existing clone:

```powershell
git submodule update --init --recursive
```

If the extension is not installed:

```powershell
gh auth login
gh extension install github/gh-actions-importer
```

Prepare the importer image and credentials from the repository root:

```powershell
gh actions-importer update
gh actions-importer configure
gh actions-importer version
docker info
```

Configuration stores credentials locally; keep `.env.local` ignored. Updating the importer can change conversion behavior, so record the version when comparing results.

## Normal importer: no custom transformers

Use a fresh scratch directory for each manual run:

```powershell
$runStamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$baselineDirectory = ".work/manual-baseline-$runStamp"

gh actions-importer dry-run gitlab `
  --namespace lijazsalim `
  --project simple-maven-app `
  --output-dir $baselineDirectory `
  --no-telemetry

$LASTEXITCODE
$baselineWorkflow = "$baselineDirectory/lijazsalim/simple-maven-app/.github/workflows/simple-maven-app.yml"
Get-Content -LiteralPath $baselineWorkflow
```

This produces raw importer output under the specified directory. It does not publish a pull request or execute the generated GitHub workflow.

## Importer with native Ruby transformers

```powershell
$runStamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$nativeDirectory = ".work/manual-native-$runStamp"

gh actions-importer dry-run gitlab `
  --namespace lijazsalim `
  --project simple-maven-app `
  --output-dir $nativeDirectory `
  --custom-transformers transformer-wrapper/transformers/maven.rb `
  --no-telemetry

$LASTEXITCODE
$nativeWorkflow = "$nativeDirectory/lijazsalim/simple-maven-app/.github/workflows/simple-maven-app.yml"
Get-Content -LiteralPath $nativeWorkflow
```

The added `--custom-transformers` argument loads our Ruby DSL rules inside the importer. This direct command does not apply `postprocess.rb`. The native-only workflow retains the two known compatibility gaps. A zero importer exit code alone is not sufficient validation: the tested version can report a custom-hook error while returning zero.

## Apply the compatibility layer manually

Run this in the same PowerShell session after the native command above; it uses `$nativeWorkflow` and `$nativeDirectory`:

```powershell
$repositoryDirectory = (Get-Location).Path
$finalWorkflow = "$nativeDirectory/final.yml"

docker run --rm --network none `
  --mount "type=bind,source=$repositoryDirectory,target=/work" `
  --workdir /work `
  --entrypoint ruby ghcr.io/actions-importer/cli:latest `
  transformer-wrapper/postprocess.rb $nativeWorkflow $finalWorkflow

$LASTEXITCODE
Get-Content -LiteralPath $finalWorkflow
```

This validates the expected native structure, fixes the known condition, and removes the old job container. It writes a separate final file. Stop and inspect errors if a command fails; do not interpret an existing file as proof a failed command succeeded.

## Generate the published baseline and modified outputs

The wrapper automates both importer invocations, postprocessing, and provenance recording:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\transformer-wrapper\run.ps1
```

Outputs:

```text
Outputs/baseline/simple-maven-app.yml    Raw baseline
Outputs/modified/native.yml             Raw native-customized result
Outputs/modified/simple-maven-app.yml    Final result after compatibility edits
Outputs/baseline/provenance.json
Outputs/modified/provenance.json
```

To regenerate only one side:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\transformer-wrapper\run.ps1 -Mode Baseline
powershell -NoProfile -ExecutionPolicy Bypass -File .\transformer-wrapper\run.ps1 -Mode Modified
```

The selected published outputs are replaced. Regeneration marks the previous comparison stale; rerun comparison below. Both arms read the live GitLab project, so avoid changing project configuration between runs. Conversion does not invoke comparison or Maven execution.

## Separate validation and comparison

Install the optional Windows x64 validator once:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\transformer-wrapper\install-validator.ps1
```

Validate the published files and write `Outputs/modified/comparison.md`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\transformer-wrapper\compare.ps1
$LASTEXITCODE
```

This runs actionlint, Ruby assertions, and diffs. It does not execute the workflows on GitHub. For the recorded example, baseline/native lint fail on the known condition, while final lint and the 17 assertions pass. The comparison command fails if final lint or the assertions fail.

## Manual diffs

With VS Code installed:

```powershell
code --diff Outputs/baseline/simple-maven-app.yml Outputs/modified/native.yml
code --diff Outputs/modified/native.yml Outputs/modified/simple-maven-app.yml
code --diff Outputs/baseline/simple-maven-app.yml Outputs/modified/simple-maven-app.yml
```

Or use Git:

```powershell
git diff --no-index -- Outputs/baseline/simple-maven-app.yml Outputs/modified/native.yml
git diff --no-index -- Outputs/modified/native.yml Outputs/modified/simple-maven-app.yml
```

For `git diff --no-index`, exit code 1 means differences were found; it is expected here.

The separate local Maven execution recipe is in [execution.md](Outputs/modified/execution.md). For project scope and limitations, see [README.md](README.md). The generated workflow assumes the application is at the checkout root; these commands do not activate it in this research repository.
