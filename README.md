# GitHub Actions Importer: baseline conversion and workflow refinement

This repository investigates how native GitHub Actions Importer transformers and a small compatibility layer can improve a GitLab-to-GitHub Actions migration.

The subject is `simple-maven-app`: one Maven verification job using Maven 3.3.9 and Java 8. The repository contains actual importer output, the native customization code, and separately generated validation results. It does not establish support for arbitrary pipelines.

## Repository structure

```text
Outputs/
  baseline/
    simple-maven-app.yml     # Unmodified Actions Importer result
    provenance.json         # Importer version, configuration and output hash
  modified/
    native.yml              # Importer result with Ruby transformers; no postprocessing
    simple-maven-app.yml     # Native result plus two compatibility edits
    provenance.json
    comparison.md           # Separate validation and diffs
    execution.md            # Recorded local Maven component check
    maven-verify.log
transformer-wrapper/
  transformers/maven.rb     # Actual native importer DSL hooks
  run.ps1                  # Invokes the importer and publishes outputs
  postprocess.rb           # Two bounded compatibility edits
  compare.ps1              # Optional, separate comparison and validation
  tests.rb
  install-validator.ps1
  README.md
simple-maven-app/            # Original application, tracked as a submodule
```

Start with [the baseline](Outputs/baseline/simple-maven-app.yml), then inspect [the native transformer](transformer-wrapper/transformers/maven.rb), [native-only output](Outputs/modified/native.yml), and [the final workflow](Outputs/modified/simple-maven-app.yml). The [comparison report](Outputs/modified/comparison.md) shows both conversion stages separately.

## Research method

```text
GitLab pipeline and project settings
  -> Actions Importer, without custom transformers -> baseline
  -> Actions Importer, with native Ruby transformers -> native output
  -> two explicit compatibility edits -> modified workflow
  -> separately invoked validation/comparison
```

Both importer runs use the same project and installed importer version. They read the live GitLab project, so they are not an atomic snapshot: project configuration can change between runs. Provenance records the exact generated hashes, tool version, container digest, and a hash of the local reference GitLab YAML. That local hash is not presented as a verified hash of the remote response.

The freshly generated baseline matched the initially recorded baseline byte-for-byte: SHA256 `ecd92f0b82f143d3ab169cfd280047466eb787e2b89b0590356a7e04a461d110`.

## Native changes and remaining gaps

| Concern | Native customization | Remaining compatibility work |
| --- | --- | --- |
| Checkout | `transform "checkout"` selects a reviewed SHA and preserves checkout options | None in the step itself |
| Maven cache | `transform "cache"` selects a supported SHA and a POM/toolchain key | Hosted cache restore/save still needs runtime verification |
| Build toolchain | `transform "script"` emits Docker execution with the original Maven image digest and original command | Remove the old job-level container so Actions steps and Docker run on the host |
| Runner policy | `runner :default` selects `ubuntu-24.04` | None for this example |
| Branch condition | Importer retains the intended master exclusion but emits malformed YAML expression syntax | Escape that one known expression |

The `checkout`, `cache`, and `script` identifiers were inspected in the installed importer's GitLab step transformers and exercised through real `gh actions-importer dry-run ... --custom-transformers` invocations. These hooks are not simulated by a separate converter. Their item shapes are version-dependent; unfamiliar inputs fail explicitly.

`postprocess.rb` does not perform the conversion again. It validates its preconditions, fixes the known condition, and removes the exact legacy container block. It preserves the native steps unchanged. It is a separate script; `native.yml` makes the result without that layer inspectable.

## Reproduce on Windows

For a dedicated copy-and-run reference covering raw importer commands, native transformers, postprocessing, and comparison, see [README.commands.md](README.commands.md).

Prerequisites: Git, GitHub CLI, Docker Desktop running Linux containers, and PowerShell. Ruby is already supplied by the importer container; no local Ruby installation is required.

Clone with the application submodule:

```powershell
git clone --recurse-submodules https://github.com/LijazS/gh-demo2.git
Set-Location gh-demo2
```

If already cloned:

```powershell
git submodule update --init --recursive
```

Install/configure the importer if needed:

```powershell
gh auth login
gh extension install github/gh-actions-importer
gh actions-importer update
gh actions-importer configure
```

Run configuration from the repository root. Keep credentials in the ignored `.env.local` file; `.env.example` contains placeholders only. The scripts target GitLab project `lijazsalim/simple-maven-app`.

Generate both outputs:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\transformer-wrapper\run.ps1
```

This runs actual Actions Importer twice. The second invocation supplies `transformer-wrapper/transformers/maven.rb`. It records the native result and separately applies `postprocess.rb`. It does not run actionlint, compare files, execute Maven, or push to GitHub.

Generate only one side when needed:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\transformer-wrapper\run.ps1 -Mode Baseline
powershell -NoProfile -ExecutionPolicy Bypass -File .\transformer-wrapper\run.ps1 -Mode Modified
```

The selected output files are replaced on regeneration. Importer logs and temporary outputs stay in ignored `.work/`. Record matched runs when interpreting comparisons.

Install the optional validator and run comparison separately:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\transformer-wrapper\install-validator.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\transformer-wrapper\compare.ps1
```

Read `Outputs/modified/comparison.md` in GitHub or a Markdown viewer. For a manual comparison in VS Code:

```powershell
code --diff Outputs/baseline/simple-maven-app.yml Outputs/modified/native.yml
code --diff Outputs/modified/native.yml Outputs/modified/simple-maven-app.yml
```

Without VS Code:

```powershell
git diff --no-index -- Outputs/baseline/simple-maven-app.yml Outputs/modified/simple-maven-app.yml
```

Git returns exit code 1 when there are differences; this is expected.

## Observations and limits

Additional importer experiments: [audit results](Outputs/audit/2026-09-29/README.md) and [forecast attempt](Outputs/forecast/2026-09-29/README.md). The local-source audit succeeded; live namespace discovery failed, and no forecast estimate was available.

- The recorded baseline fails actionlint on the malformed condition.
- Native customization fixes the selected conversion policies but still leaves that syntax defect and the legacy job container. Its intermediate output is therefore not ready for execution.
- The final workflow passes actionlint and the separate source-preservation/native-hook assertions. This demonstrates useful importer extension for this pipeline, not general semantic equivalence.
- A clean-cache [local Maven component check](Outputs/modified/execution.md) passed and produced a JAR. The exact scope, source commit, workflow hash and log are recorded separately from static validation.
- The native script preserves Java 8, Maven 3.3.9, and the Maven command. The old image remains old; retaining it is a compatibility decision, not a toolchain modernization claim.
- Cancellation behavior, triggers, environment, and timeout are preserved. GitLab's project-level cancellation policy was not independently established.
- The application still depends on a GitLab-hosted Maven package. Its sole test is a trivial assertion.
- No GitHub-hosted workflow or hosted cache-service run is claimed. The workflows are stored under `Outputs`, not activated under this repository's `.github/workflows`.
- To test execution on GitHub, install the final workflow in the application repository on a non-master branch. Its relative paths assume the application is at the checkout root, not nested inside this research repository.

The evidence supports a native-extension architecture with a small, visible compatibility layer. Additional pipeline families need their own tested hooks and execution evidence before broader conclusions are warranted.

## References

- [GitHub: native custom transformers](https://docs.github.com/en/actions/reference/github-actions-importer/custom-transformers)
- [GitHub: GitLab migration](https://docs.github.com/en/actions/tutorials/migrate-to-github-actions/automated-migrations/gitlab-migration)
- [Cache action migration requirements](https://github.com/actions/cache#whats-new)
