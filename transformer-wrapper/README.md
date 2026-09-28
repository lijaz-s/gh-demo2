# Native importer wrapper

The wrapper invokes GitHub Actions Importer. It does not implement a separate GitLab converter.

| File | Responsibility |
| --- | --- |
| `run.ps1` | Run baseline/customized importer commands; preserve raw native output; invoke the compatibility script; record provenance |
| `transformers/maven.rb` | Native Ruby `runner`, `checkout`, `cache`, and `script` customizations |
| `postprocess.rb` | Fix the known condition and remove the known job container after native script conversion |
| `compare.ps1` | Separately run actionlint/static assertions and produce a Markdown comparison |
| `tests.rb` | Check actual outputs against source expectations and reject unsupported hook inputs |
| `install-validator.ps1` | Install checksum-verified actionlint for Windows x64 |

Run commands from the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\transformer-wrapper\run.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\transformer-wrapper\install-validator.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\transformer-wrapper\compare.ps1
```

Only the first command performs conversion. Comparison is optional. See the root README for setup and methodology.

## Direct native invocation

To exercise the importer without any postprocessing, choose a fresh ignored output directory:

```powershell
gh actions-importer dry-run gitlab --namespace lijazsalim --project simple-maven-app --output-dir .work/manual-native --custom-transformers transformer-wrapper/transformers/maven.rb --no-telemetry
```

The resulting workflow is under `.work/manual-native/lijazsalim/simple-maven-app/.github/workflows/`. The native-only result retains the known importer compatibility gaps. `Outputs/modified/native.yml` records this same stage from the wrapper's last run.

The wrapper deliberately uses live project extraction. `--source-file-path` was also investigated, but it omits project-level metadata such as the observed timeout, checkout settings and concurrency settings. Mixing that mode with a live-extracted baseline would introduce unrelated differences.

## Scope and maintenance

The rules accept the supplied Maven verification command and cache layout. They are not intended to transform arbitrary scripts, multiple jobs, services, or deployment pipelines. Unknown hook inputs raise an error. Because the tested importer can return exit code 0 after a transformer error, the compatibility stage also checks that the expected native steps actually exist before publishing a final workflow.

The native identifiers were exercised with importer container version 1.3.22671. Provenance stores the actual version and digest for each run. Revalidate after importer updates; the wrapper does not assume item structures are a permanent public schema.

The action SHAs are reviewed configuration in `maven.rb`, not automatically selected latest versions. The Maven digest intentionally retains the original toolchain.

Runtime/tool downloads are ignored. There is no local-language package installation, database, model API, or service process. Ruby standard libraries come from the importer container.
