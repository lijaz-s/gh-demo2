# GitLab to GitHub Actions validation

Verdict: **Not ready to run as imported.** The importer preserved the core Maven job, but the workflow has three blocking compatibility problems and changes cache/concurrency behavior.

## Scope and evidence

- Source: `simple-maven-app/.gitlab-ci.yml`, commit `18f9da381b0ef56a12fda9d43331e83cf1b0c601`.
- Imported file: `output/baseline/lijazsalim/simple-maven-app/.github/workflows/simple-maven-app.yml`.
- GitHub target from the local origin: `LijazS/gh-demo1`, default branch `master`.
- GitHub API returned zero registered workflows and zero workflow runs. This is local validation, not a GitHub-hosted end-to-end run.
- Source files and the imported baseline were left unchanged. A clean copy of tracked source was used for the build, with an initially empty Maven repository and no injected credentials.
- `metadata.json` records source/workflow hashes, tool versions, and the tested container digest.

## Findings, in priority order

### 1. Blocker: invalid job condition (workflow line 13)

`if: !(github.ref == 'refs/heads/master')` starts with YAML's reserved `!` notation. Actionlint 1.7.12 exits 1 with an expression parsing error at this line.

Use:

```yaml
if: ${{ github.ref != 'refs/heads/master' }}
```

Changing only that line in the diagnostic copy `syntax-only.yml` makes actionlint exit 0. That copy still contains the other problems below and is not a ready-to-use replacement.

Evidence: `actionlint.log`, `actionlint-syntax-only.log`. ShellCheck and Pyflakes integration were disabled; YAML, workflow structure, and expression checks were enabled.

Reference: [GitHub conditional syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idif).

### 2. Blocker: job container cannot run checkout's Node runtime (lines 12, 19)

The exact `maven:3.3.9-jdk-8` image resolves to Debian 8, glibc 2.19, Maven 3.3.9, and Java 1.8.0_121. `actions/checkout@v4.1.0` declares `runs.using: node20`.

A checksum-verified official Node 20.19.0 Linux binary fails inside this container with missing `GLIBC_2.28`, `GLIBC_2.27`, and C++ runtime symbols. This is a direct runtime compatibility probe, not an execution of the GitHub runner's own Node binary or the checkout action.

Use a maintained Java 8 environment with a modern base OS, or run checkout/setup-java on the Ubuntu host and execute legacy Maven in a separate Docker step if exact Maven 3.3.9 parity is required. Updating the JavaScript action alone does not fix the old container libraries.

Evidence: `container-probe.log`, `node20-probe.log`.

References: [checkout v4.1.0 manifest](https://github.com/actions/checkout/blob/v4.1.0/action.yml), [Node 20 supported platforms](https://github.com/nodejs/node/blob/v20.19.0/BUILDING.md#platform-list).

### 3. Blocker: pinned cache action predates the supported cache backend (line 23)

`actions/cache@v3.3.2` uses the old cache toolkit (`^3.2.2`). GitHub's migration guidance identifies v3.4.0/v4.2.0 as compatible pinned releases and states that retired versions fail on GitHub.com. This finding comes from action metadata and official documentation; the cache service was not exercised locally.

Upgrade to a supported cache release, together with a compatible runner/container runtime. Do not interpret this as all v3 releases being unsupported.

References: [cache migration requirements](https://github.com/actions/cache#whats-new), [pinned action dependencies](https://github.com/actions/cache/blob/v3.3.2/package.json).

### 4. Medium: constant cache key does not preserve GitLab cache updates (line 26)

The Maven cache path is preserved, but `key: default` means subsequent exact cache hits are not saved again. Dependencies added later may download repeatedly. GitLab's normal pull/push cache can update the same key.

Use an OS/Java-specific key containing `hashFiles('**/pom.xml')` and a suitable restore prefix, or setup-java's Maven caching. GitHub cache branch access rules also differ from GitLab's shared default-key behavior.

Reference: [cache key and save behavior](https://github.com/actions/cache#usage).

### 5. Medium: importer adds cancellation behavior (lines 5–7)

`cancel-in-progress: true` cancels an older run on the same ref. The supplied GitLab YAML does not establish equivalent cancellation behavior; project-level GitLab settings were not checked. A group containing only `github.ref` can also collide with another workflow using the same group.

For parity, establish the intended cancellation policy. If cancellation is desired, scope the group to `${{ github.workflow }}-${{ github.ref }}`.

## What was preserved and what remains conditional

| Area | Assessment |
| --- | --- |
| Jobs | One concrete GitLab job, `verify:jdk8`, became `verify-jdk8`; hidden template inheritance was flattened correctly. |
| Build command | `mvn $MAVEN_CLI_OPTS verify` and all CLI flags preserved. |
| JVM options | Flags preserved; `CI_PROJECT_DIR` translated to `github.workspace` for the local Maven repository. |
| Toolchain | Exact Maven/Java image preserved; this creates the Actions runtime incompatibility above. |
| Master exclusion | Intended exclusion preserved, but expression syntax must be corrected. The target default branch is `master`, so its only job would be skipped even after repair. |
| Branch and tag pushes | Configured through unfiltered `push`; after the syntax fix, non-master branch and ordinary tag pushes are eligible. |
| Pull requests | No `pull_request` trigger. The source does not explicitly enable GitLab merge-request pipelines either, despite its comments. Fork PR checks are not provided by this migration. Add PR coverage only if that is intended. |
| Deployment | No deployment job exists in the source. The comments mention deployment, but the importer did not omit an implemented deploy job. |
| Scheduling/API triggers | Not validated against GitLab project settings; no schedule or repository_dispatch trigger exists in the output. |
| Timeout | Output sets 60 minutes. The source YAML has no explicit timeout; project-level timeout parity is unverified. |
| Checkout | Importer adds full history and LFS. The tracked files contain no `.gitattributes`; these settings appear unnecessary for this sample. |
| External dependency | The POM still uses GitLab's Maven package registry for `com.example.dep:simple-maven-dep:1.0`. It resolved in the clean-cache local build without injected credentials. Repository migration does not migrate that package. |
| Test quality | The only test uses `assertTrue(true)`. A green build demonstrates compilation/package assembly, but provides little application behavior coverage. |

## Executed checks

| Check | Result |
| --- | --- |
| Original imported workflow, actionlint 1.7.12 | FAIL, exit 1 |
| Diagnostic copy with only the condition corrected | PASS, exit 0 |
| Exact container availability/toolchain probe | PASS; obsolete Debian 8/glibc 2.19 confirmed |
| Node 20 binary inside exact container | FAIL, exit 1, missing system libraries |
| Clean-cache Maven verify in exact container | PASS, exit 0; 1 test, 0 failures/errors/skips; JAR produced; Maven duration 1 minute 40 seconds. See `maven-verify.log`. |
| GitHub-hosted workflow execution | NOT RUN; workflow is not installed in the target repository |

The next acceptance check after repairs is a GitHub-hosted run on a non-master test branch, including checkout and cache restore/save. A default-branch run alone would skip this job and would not prove the build works.
