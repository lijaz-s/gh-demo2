# Actions Importer enhancement POC

This is a **post-import transformer wrapper** for the supplied `simple-maven-app` migration. It reads your existing `gh actions-importer dry-run` output, preserves it, produces improved YAML, and compares both outputs with the same checks.

It uses no AI/model calls, does not access a company migration tool, and does not push files or run workflows on GitHub. These are Python transformations of importer output, **not Ruby plugins for `--custom-transformers`**. The fixes demonstrated here involve YAML syntax and job execution structure; this POC does not claim unverified native importer hooks.

All tool files, dependencies, tests, reports, and local build copies live here:

```text
C:\Users\lijaz\Desktop\poc\poc\transformers
```

The repeated `poc\poc` is intentional: this implements the requested `./poc/transformers` relative to the existing workspace `C:\Users\lijaz\Desktop\poc`.

## 1. What it fixes

| Rule | Existing importer output | Enhanced output |
| --- | --- | --- |
| T1 | Invalid `if: !(...)` expression | Valid `${{ github.ref != 'refs/heads/master' }}` expression |
| T2 | `actions/cache@v3.3.2`; old checkout pin | Approved checkout v4.4.0 and cache v4.3.0, pinned to verified commit SHAs |
| T3 | JavaScript actions execute inside Debian 8 Maven job container | Checkout/cache run on Ubuntu; the original Maven/Java toolchain runs in a separate Docker step |
| T4 | Constant cache key `default` | OS/toolchain/POM-dependent key and a restore prefix |

Four rules generate five ledger entries because T2 updates two action references. The original Java 8/Maven 3.3.9 image is pinned by digest. The Docker process runs with the host user's UID/GID so the cache and build outputs remain accessible. `MAVEN_CONFIG=/tmp` uses an existing writable directory required by this old image's entrypoint.

Commands, Maven flags, intended master exclusion, push/manual triggers, and existing cancellation settings are preserved. Cancellation behavior, lack of PR triggers, the external GitLab package dependency, and the sample's trivial test remain visible limitations.

This is deliberately a **single-job Maven profile**, not a general CI compiler. Extra jobs, includes/rules, services, custom container options, additional steps, changed checkout directories, and unrecognized action references require review. The tool refuses them instead of silently dropping behavior.

## 2. Prerequisites and setup (PowerShell)

Required for static comparison: Windows x64, Python 3.11+ with pip/venv, internet access for first setup. Docker Desktop with Linux containers and Git are needed for local execution. GitHub CLI/authentication is only needed for optional importer reruns or hosted execution.

Open PowerShell and run:

```powershell
Set-Location C:\Users\lijaz\Desktop\poc\poc\transformers
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
```

The execution-policy override applies to that setup process only. Setup creates `.venv`, installs pinned Python dependencies, downloads actionlint 1.7.12, verifies its release SHA256 checksum, and runs the dependency check. It does not alter your pipeline or GitHub repository.

Use the virtual environment's Python directly; activation is unnecessary. On this machine, plain `python` resolves to an MSYS Python without pip, so do not substitute it for the commands below.

```powershell
& .\.venv\Scripts\python.exe -m migration_poc doctor
```

## 3. Inspect your current baseline

Defaults point to these existing workspace inputs:

```text
../../output/baseline/lijazsalim/simple-maven-app/.github/workflows/simple-maven-app.yml
../../simple-maven-app/.gitlab-ci.yml
```

Run:

```powershell
& .\.venv\Scripts\python.exe -m migration_poc inspect
$LASTEXITCODE
```

**Expected: exit 1 and `validation-failed`.** The baseline is known to have problems. This command does not modify it or run Maven.

To inspect the raw file yourself:

```powershell
Get-Content ..\..\output\baseline\lijazsalim\simple-maven-app\.github\workflows\simple-maven-app.yml
```

## 4. Generate your own improved output and report

```powershell
& .\.venv\Scripts\python.exe -m migration_poc enhance --output .\output\demo
$LASTEXITCODE
```

Expected:

```text
Baseline: validation-failed
Enhanced: static-pass
Transformations: 5
```

`output\demo` must not already exist. For a second run, use `output\demo-2`, or omit `--output` to create a timestamped directory. Evidence is never overwritten by `enhance` or `compare`.

The existing developer-verified result is in `output\verified`. Use `output\demo` for your own fresh demonstration.

Generated files:

| File | Use |
| --- | --- |
| `baseline.yml` | Exact byte copy of your raw importer output |
| `source.gitlab.yml` | Snapshot of the GitLab YAML used for this comparison |
| `enhanced.yml` | Improved standalone GitHub Actions workflow |
| `changes.diff` | Unified baseline/enhanced diff |
| `changes.json` | Per-rule change ledger and reasons |
| `findings.json` | Both validation results, including warnings and checks not run |
| `manifest.json` | Source/input hashes, policy, tool versions, execution scope |
| `report.html` | Presentation-friendly report; open directly in a browser |
| `report.md` | Text version of the report |

## 5. Compare manually

Open the report:

```powershell
Start-Process .\output\demo\report.html
```

Read the diff:

```powershell
Get-Content .\output\demo\changes.diff
```

If you use VS Code:

```powershell
code --diff .\output\demo\baseline.yml .\output\demo\enhanced.yml
```

Or use Git's standalone diff:

```powershell
git diff --no-index -- .\output\demo\baseline.yml .\output\demo\enhanced.yml
```

`git diff --no-index` exits **1 when files differ**; that is expected.

Check these changes yourself:

1. The job still excludes `master`, but its expression is now valid.
2. The job-level `container` block is removed.
3. Checkout and cache now use reviewed SHA pins.
4. The cache key contains `hashFiles('**/pom.xml')` and the toolchain identity.
5. The last step runs Docker with the original Maven image digest and the original `mvn $MAVEN_CLI_OPTS verify` command.
6. Maven variables, triggers, timeout, and concurrency settings remain intact.
7. No `continue-on-error`, `|| true`, or skipped-test flags were added.

Check that your baseline is untouched:

```powershell
Get-FileHash ..\..\output\baseline\lijazsalim\simple-maven-app\.github\workflows\simple-maven-app.yml
Get-FileHash .\output\demo\baseline.yml
```

Those two SHA256 hashes should match.

## 6. Run actionlint independently on each file

```powershell
& .\tools\actionlint.exe -no-color -shellcheck= -pyflakes= .\output\demo\baseline.yml
$LASTEXITCODE
```

Expected: expression error, exit **1**.

```powershell
& .\tools\actionlint.exe -no-color -shellcheck= -pyflakes= .\output\demo\enhanced.yml
$LASTEXITCODE
```

Expected: no errors, exit **0**. ShellCheck and Pyflakes are disabled; actionlint still checks workflow structure and expressions.

You can also run the complete checker on the enhanced output:

```powershell
& .\.venv\Scripts\python.exe -m migration_poc inspect --baseline .\output\demo\enhanced.yml
```

Expected: `static-pass`, with warnings and hosted execution explicitly marked unverified. `--baseline` here means the workflow being inspected; inspection never repairs it.

## 7. Execute Maven locally, including a negative control

Ensure Docker Desktop is running with Linux containers, then:

```powershell
& .\.venv\Scripts\python.exe -m migration_poc smoke --run .\output\demo --negative-control
$LASTEXITCODE
```

The command:

1. Checks that the workflow/source/policy still match the saved comparison.
2. Copies **tracked working-tree source files** into a fresh directory under `output\demo\runtime`. It does not copy `.env.local`, your existing `target/`, or untracked files.
3. Runs the original Maven command in the pinned image with a fresh Maven cache.
4. Verifies success, Surefire results, and JAR production.
5. Creates a second source copy and changes the sample assertion to `assertTrue(false)` there only.
6. Reuses downloaded Maven dependencies, but not compiled classes/test reports, for the negative control.
7. Confirms that Maven returns a failure and a test report contains a failed assertion.
8. Confirms the original tracked files are unchanged and updates the HTML/Markdown report.

Allow a few minutes for downloads on the first run. Both stdout and stderr are stored in the reported log paths. Each build has a 10-minute timeout.

Expected top-level result: `"status": "pass"` and exit **0**. In this result, a passing **negative control** means the intentionally failing test was correctly rejected; its nested Maven exit code is nonzero.

Open or refresh the report afterward:

```powershell
Start-Process .\output\demo\report.html
Get-Content .\output\demo\runtime.json
```

**Scope:** this is an isolated Maven component test with the enhanced workflow's recognized command/image/environment. It is not a GitHub Actions emulator: checkout, GitHub cache restore/save, event scheduling, and runner permissions are not tested locally. The report never counts this as a hosted workflow run.

## 8. Test repeatability and inspect your own edits

Run the automated tests:

```powershell
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Apply the transformations again to already-enhanced YAML:

```powershell
& .\.venv\Scripts\python.exe -m migration_poc enhance --baseline .\output\demo\enhanced.yml --output .\output\idempotence
```

Expected: **0 transformations**, same workflow content. Compare hashes:

```powershell
Get-FileHash .\output\demo\enhanced.yml
Get-FileHash .\output\idempotence\enhanced.yml
```

To compare an edited candidate without having the wrapper repair it:

```powershell
Copy-Item .\output\demo\enhanced.yml .\output\candidate.yml
# Edit output\candidate.yml yourself.
& .\.venv\Scripts\python.exe -m migration_poc compare --enhanced .\output\candidate.yml --output .\output\manual-comparison
Start-Process .\output\manual-comparison\report.html
```

The same baseline and source defaults apply. Unexpected commands or settings are flagged; a syntax-only pass cannot override a source-contract failure. `compare` validates the supplied candidate as-is and does not apply transformations.

## 9. Optional: run the enhanced workflow on GitHub yourself

These are **manual publishing commands**, not actions performed by the wrapper or by this implementation. They add only the generated workflow to a new branch of your existing repository. Review the YAML first. Do not commit `output/`, `.venv`, or `.env.local`.

From this tool directory:

```powershell
$repositoryPath = (Resolve-Path ..\..\simple-maven-app).Path
git -C $repositoryPath status --short
git -C $repositoryPath switch -c poc/importer-enhanced
New-Item -ItemType Directory -Force -Path (Join-Path $repositoryPath '.github\workflows') | Out-Null
Copy-Item -LiteralPath .\output\demo\enhanced.yml -Destination (Join-Path $repositoryPath '.github\workflows\simple-maven-app.yml')
git -C $repositoryPath add -- .github/workflows/simple-maven-app.yml
git -C $repositoryPath diff --cached
git -C $repositoryPath commit -m 'Add enhanced Maven workflow for importer POC'
git -C $repositoryPath push -u origin poc/importer-enhanced
```

If the branch already exists, choose a fresh name. If you have unrelated tracked changes, review those before switching branches. The existing untracked `target/` must not be staged.

Inspect the run:

```powershell
gh run list --repo LijazS/gh-demo1 --branch poc/importer-enhanced --limit 5
```

Copy the numeric run ID shown, then substitute it below:

```powershell
gh run watch <RUN_ID> --repo LijazS/gh-demo1 --exit-status
gh run view <RUN_ID> --repo LijazS/gh-demo1 --log
```

Use an eligible feature branch. The only job is intentionally skipped on `master`; a skipped job does not prove execution success. A branch-only `workflow_dispatch` may not appear until a workflow is installed on the default branch, so use the push trigger for this demonstration.

For a second hosted cache check, rerun the successful run:

```powershell
gh run rerun <RUN_ID> --repo LijazS/gh-demo1
gh run watch <RUN_ID> --repo LijazS/gh-demo1 --exit-status
```

Inspect the cache-step logs for a restore hit. The local report does not automatically import these hosted results; retain the run URL as separate evidence.

## 10. Optional: use fresh importer output later

The wrapper does not require another importer run. To deliberately generate a fresh baseline without overwriting the existing one, run from the workspace root where your importer configuration exists:

```powershell
Set-Location C:\Users\lijaz\Desktop\poc
gh actions-importer dry-run gitlab --namespace lijazsalim --project simple-maven-app --output-dir .\poc\transformers\output\fresh-baseline
Set-Location .\poc\transformers
& .\.venv\Scripts\python.exe -m migration_poc enhance --baseline .\output\fresh-baseline\lijazsalim\simple-maven-app\.github\workflows\simple-maven-app.yml --output .\output\fresh-comparison
```

A different importer version may emit a different shape. The POC will flag unsupported differences rather than assume they are safe. Record that importer version separately; it does not establish the generator version of your historical baseline.

## 11. Troubleshooting and exit codes

| Symptom | Meaning / next step |
| --- | --- |
| Inspect returns 1 on baseline | Expected validation failure |
| Enhanced result says `validation-incomplete` | Install actionlint with setup; don't claim a full static pass |
| Output already exists | Choose a new `--output` directory |
| Unsupported profile / extra steps | This input needs a reviewed rule extension; source is not rewritten |
| Docker connection failure | Start Docker Desktop with Linux containers |
| Maven download failure | Check network/GitLab registry access; inspect the runtime log |
| Runtime manifest mismatch | Generate a fresh comparison after changing source YAML, policy, or enhanced workflow |
| Plain Python lacks pip | Use `py -3` for setup and `.venv\Scripts\python.exe` thereafter |

CLI exit codes: **0** requested checks passed; **1** validation/build incomplete or failed; **2** input/tool/unsupported-profile error. Remaining review warnings do not turn a static pass into full migration approval.

## 12. Files to inspect when extending the POC

- `migration_poc/core.py`: explicit profile checks and T1–T4 transformations.
- `policies/maven.json`: reviewed action SHAs and original container digest.
- `migration_poc/validation.py`: identical before/after static checks.
- `migration_poc/runtime.py`: isolated local execution and negative control.
- `migration_poc/reporting.py`: escaped HTML, Markdown, JSON, and diff.
- `tests/test_transformations.py`: refusal, repeatability, fidelity, and actionlint tests.

When extending a rule, add a representative input and independent expected behavior first. Test refusal of nearby unsupported cases as well as successful conversion. No results here establish superiority over an unavailable company migration tool.
