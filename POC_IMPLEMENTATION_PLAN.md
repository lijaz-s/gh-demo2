# Corrected POC plan: raw Actions Importer output versus enhanced output

Status: planning only. No wrapper, transformer, workflow repair, or new migration run has been implemented as part of this correction.

## 1. Confirmed scope and provenance

The user generated `output/baseline/` by personally running:

```text
gh actions-importer dry-run gitlab --namespace lijazsalim --project simple-maven-app --output-dir ./output/baseline
```

This is raw GitHub Actions Importer output. It is not output from the company's migration tool. The user has no access to that tool or its results.

The two comparison arms are therefore:

- A: the existing raw workflow at `output/baseline/lijazsalim/simple-maven-app/.github/workflows/simple-maven-app.yml`.
- B: an enhanced workflow produced by our planned wrapper from A, using the original GitLab pipeline and explicit policies as context.

The baseline remains unchanged. The enhanced result goes into a separate directory. This POC can demonstrate improvements over the supplied importer output. It cannot establish superiority over an unavailable company tool.

## 2. Objective and limits

Build a small, presentable, repeatable wrapper that repairs real migration problems in this Maven example, explains each change, and provides independent validation evidence.

The core scope is one real repository, a handful of reusable transformation rules, a CLI, focused tests, and a before/after report. Remove the previous requirements for company-tool comparison, three separate demo pipelines, Terraform reporting, invented organization settings, and an agent integration. Those are potential future extensions, not prerequisites for this POC.

The POC must preserve build intent and must not achieve success by deleting jobs, weakening tests, ignoring failures, or changing excluded branches.

## 3. Distinguish the two transformer mechanisms

A wrapper postprocessor reads already-generated workflow YAML and emits improved workflow YAML. This is the primary mechanism for the requested comparison because the input is the existing baseline.

Native Actions Importer custom transformers are Ruby DSL files passed with `--custom-transformers` during an importer run. They do not operate directly on an existing generated output folder.

For implementation, first check whether a native importer hook can implement any selected repair cleanly. Prefer a proven hook where appropriate, but do not invent hooks or add artificial runner/secret mappings merely to include Ruby files. The deliverable is useful, tested migration transformations; each rule will identify whether it runs inside the importer or afterward in the wrapper.

If a native transformer demonstration is included, rerun the same source snapshot with the same pinned importer into a third, clearly labeled directory. Preserve the current baseline, distinguish regeneration changes from our repairs, and keep the primary comparison A versus B.

## 4. Inputs and output contract

Inputs:

- Original GitLab YAML: `simple-maven-app/.gitlab-ci.yml`.
- Existing imported workflow: the file under `output/baseline/`.
- Tracked application source and Maven POM.
- Small policy file identifying allowed repairs and approved action versions.
- Existing evidence in `output/validation/`, used as historical evidence rather than presented as a new run.

Outputs:

```text
output/enhanced/<run-id>/
  workflows/simple-maven-app.yml
  changes.diff
  findings.json
  manifest.json
  validation/
  report.md
  report.html
```

The manifest records input hashes, source commit, rule/policy version, validator versions, timestamps, and execution scope. Importer version provenance for an existing baseline is recorded only when established; the currently installed version is not assumed to prove which version generated that file.

Each rule produces an ID, location, detected problem, before/after values, explanation, and validation outcome. Unknown or unsafe-to-infer changes remain explicit findings.

## 5. Planned transformations

### T1: Correct the malformed branch condition

The current baseline contains `if: !(github.ref == 'refs/heads/master')`. Correct the known malformed shape to a valid GitHub expression while preserving the master exclusion.

Because the leading exclamation mark can be parsed as a YAML tag, normalization must recognize the exact known form before ordinary YAML processing. Unknown tagged or malformed expressions must fail clearly instead of losing information.

Acceptance: actionlint rejects the baseline and accepts the correction; master remains excluded; a feature branch and an ordinary tag remain eligible under the specified workflow contract.

### T2: Apply compatible action-version policy

Detect the old cache action pin and replace it with a verified supported version appropriate for GitHub.com and the chosen execution environment. Keep a small approved-action mapping with readable release information and resolved SHAs.

Upgrade only actions required by the POC policy. Do not implement an unrestricted upgrade service or change every action merely because a newer release exists.

Acceptance: the old cache dependency is flagged; the new reference resolves; compatibility is documented; the final workflow passes actionlint and hosted execution where available.

### T3: Preserve legacy Maven in a compatible execution layout

The Maven image uses system libraries too old for checkout's Node runtime. For this recognized single-job profile, run checkout/cache on the Ubuntu host and execute the original Maven command in the original Maven Docker image.

Preserve Java 8, Maven 3.3.9, the environment variables, working directory, repository path, command arguments, and failure exit status. Pin the tested container digest. Verify host readability of container-produced build/cache files.

Scope this transformation to the explicitly recognized Maven pattern. Jobs with services, extra container options, or unfamiliar scripts receive a review finding. Do not silently turn this into a general pipeline rewrite.

Acceptance: the toolchain matches the baseline; the local build passes; the hosted checkout/build runs; a deliberately failing test propagates failure.

### T4: Improve the Maven cache key

Replace `key: default` with a key incorporating runner OS, toolchain identity, and a POM hash, with a suitable restore prefix.

Acceptance: a POM change changes the cache identity; the same inputs yield the same key; a second hosted run can demonstrate restore. Report this as an intentional cache-policy improvement, not exact GitLab cache equivalence.

### Findings that will not be silently repaired

Report the importer-added cancellation policy, the lack of PR-trigger coverage, the GitLab package dependency, and limited application-test quality. Preserve behavior unless a policy explicitly changes it. Missing project-level settings remain unknown. Do not add deployments or PR jobs absent from the agreed requirements.

## 6. CLI and implementation structure

Use Python with a YAML 1.2-capable parser, the existing actionlint binary, and Docker. Use subprocess argument arrays and explicit working directories. A static HTML report requires no application server.

Proposed commands:

```text
python -m migration_poc inspect --baseline <workflow> --source <gitlab-yaml>
python -m migration_poc enhance --baseline <workflow> --source <gitlab-yaml> --output <directory>
python -m migration_poc compare --baseline <workflow> --enhanced <workflow>
```

`inspect` performs read-only analysis. `enhance` writes a separate result and change ledger. `compare` applies the same validators and expectations to both outputs. Runtime execution is explicit and separately reported, not an unexpected side effect of static comparison.

Keep the source small: CLI, transformation rules, validation, reporting, policies, and tests. No service, database, agent framework, general migration engine, or large plugin architecture is necessary.

## 7. Independent validation

Write the acceptance contract before implementing repairs. It includes one concrete Maven job, its build command/environment, master exclusion, expected Java/Maven versions, and JAR output.

Use the same checks for baseline and enhanced output:

| Check | Required evidence |
| --- | --- |
| Input preservation | Original source and baseline hashes unchanged |
| Workflow syntax | Actionlint findings before and after |
| Action compatibility | Approved action metadata and versions |
| Container compatibility | Existing failure evidence and new execution-layout verification |
| Build intent | Commands, options, and toolchain preserved |
| Local build | Clean-source execution and recorded result |
| Hosted execution | Actual run URL, commit, job/step results when executed |
| Failure propagation | A separate deliberately failing fixture remains failed |
| Cache behavior | POM-sensitive key and optional hosted restore evidence |
| Idempotence | Second transformation makes no further changes |
| Repeatability | Equivalent output for identical inputs and policy |
| Generalization | Changed source command/path survives; unrelated YAML is retained |

A green run with every job skipped is not a passing execution test. The existing master exclusion means the demonstration build must run on an eligible feature branch. Local checks are labeled local; hosted execution is not claimed until performed.

## 8. Presentation and comparison report

Produce one report with two columns: supplied importer baseline and enhanced output. Show real findings rather than predetermined scores.

For every repair, show the source/workflow location, relevant before/after snippet, rule ID, concise reason, and linked evidence. Separate automatically repaired items from warnings and unknowns.

Use statuses such as failed, passed, requires configuration, needs review, and not executed. Avoid unsupported confidence percentages. Distinguish historical evidence from newly executed checks.

Suggested 7–10 minute demonstration:

1. Show the user's exact importer command and baseline file.
2. Inspect the baseline and show actual failures.
3. Run the enhancement command.
4. Open the diff and explain the small reusable rules.
5. Show identical validation checks on the improved workflow.
6. Show actual build evidence and deliberate failure propagation.
7. Rerun transformation to demonstrate stable output.
8. Show remaining limitations and implementation size.

The supported manager-facing claim is that a small wrapper improves this importer output and makes the changes explainable and testable. A company-tool comparison is out of scope because neither access nor results are available.

## 9. Implementation sequence and estimate

| Step | Deliverable | Estimate |
| --- | --- | --- |
| 1 | Snapshot inputs, establish acceptance checks, verify available hooks | 2–3 hours |
| 2 | Implement inspection and the four scoped transformation rules | 5–7 hours |
| 3 | Focused tests, idempotence, and local execution | 3–5 hours |
| 4 | Before/after diff, Markdown/HTML report, demo script | 3–4 hours |
| 5 | Hosted execution and presentation rehearsal | 2–4 hours plus access/setup |

Allow approximately 2–3 working days for this reduced scope, subject to implementation findings. Native transformer integration is included only if an applicable hook is verified; otherwise document why the repair is a wrapper transformation.

## 10. Definition of done and present status

Done means the supplied baseline is untouched, actual problems are detected, tested transformations produce a separate improved workflow, the same checks compare both outputs, execution evidence is accurately labeled, and the manager can inspect the changes without reading implementation logs.

Present status: only this planning document has been corrected. No implementation, workflow edits, new migrations, or remote writes were performed for this clarification.
