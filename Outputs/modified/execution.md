# Local Maven execution evidence

Date: 2026-09-27. This is a component execution check, not a GitHub-hosted workflow run.

The source was exported from application commit `18f9da381b0ef56a12fda9d43331e83cf1b0c601` into an isolated directory with an empty Maven repository. The command, image digest, Maven options and non-root execution arrangement match the native-generated build step. The local workspace was mounted as `/workspace`, rather than the path supplied by a GitHub runner.

| Observation | Result |
| --- | --- |
| Maven | 3.3.9 |
| Java | 1.8.0_121 |
| Container | `maven@sha256:18e8bd367c73c93e29d62571ee235e106b18bf6718aeb235c7a07840328bba71` |
| Command | `mvn $MAVEN_CLI_OPTS verify` |
| Exit code | 0 |
| Tests | 1 run, 0 failures, 0 errors, 0 skipped |
| Artifact | `target/simple-maven-app-1.0.jar` |
| Artifact SHA256 | `afdae0d601caa9b1e09056c210938959fb802f3d4dea6db3c75e310e78201016` |
| Final workflow SHA256 at time of check | `43e2ec1b021e5c0156b168d9f99b24bbef21a704bd60d8b2878e9b33a31b04f4` |

The [captured Maven log](maven-verify.log) contains the build result; trailing whitespace was removed for publication. The single application test is `assertTrue(true)`, so this demonstrates compilation/package assembly and dependency resolution, not meaningful application behavior coverage. Checkout, the GitHub cache service, and event scheduling were not executed in this check. JAR byte hashes can vary across rebuilds because archive timestamps are not normalized.

## Repeat the component check

From the repository root in PowerShell, use a new scratch directory:

```powershell
New-Item -ItemType Directory -Force .work/build-check | Out-Null
$archivePath = Join-Path (Get-Location).Path '.work/build-source.tar'
git -C simple-maven-app archive --format=tar --output=$archivePath HEAD
tar -xf $archivePath -C .work/build-check
$buildDirectory = (Resolve-Path .work/build-check).Path

docker run --rm --user 1001:1001 `
  --env HOME=/tmp --env MAVEN_CONFIG=/tmp `
  --env 'MAVEN_OPTS=-Dhttps.protocols=TLSv1.2 -Dmaven.repo.local=/workspace/.m2/repository -Dorg.slf4j.simpleLogger.log.org.apache.maven.cli.transfer.Slf4jMavenTransferListener=WARN -Dorg.slf4j.simpleLogger.showDateTime=true -Djava.awt.headless=true' `
  --env 'MAVEN_CLI_OPTS=--batch-mode --errors --fail-at-end --show-version -DinstallAtEnd=true -DdeployAtEnd=true' `
  --mount "type=bind,source=$buildDirectory,target=/workspace" `
  --workdir /workspace `
  maven@sha256:18e8bd367c73c93e29d62571ee235e106b18bf6718aeb235c7a07840328bba71 `
  sh -c 'mvn $MAVEN_CLI_OPTS verify'
$LASTEXITCODE
```

Use an empty scratch directory for a clean-cache run. This recipe is for Windows Docker Desktop, where the numeric user can write to the shared directory. On a Linux host, use the current user's UID/GID, as the generated workflow does.
