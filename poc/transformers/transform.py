"""Transform the supported imported Maven workflow. No comparison or execution."""
from __future__ import annotations

import argparse
import io
import re
import shlex
import sys
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError
from ruamel.yaml.scalarstring import LiteralScalarString

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[1]
DEFAULT_BASELINE = WORKSPACE / "output/baseline/lijazsalim/simple-maven-app/.github/workflows/simple-maven-app.yml"
DEFAULT_SOURCE = WORKSPACE / "simple-maven-app/.gitlab-ci.yml"
DEFAULT_OUTPUT = ROOT / "output/enhanced.yml"
# Reviewed pins from the working POC. Configuration is kept here for a small demo.
POLICY = {
    "image": "maven:3.3.9-jdk-8",
    "image_digest": "maven@sha256:18e8bd367c73c93e29d62571ee235e106b18bf6718aeb235c7a07840328bba71",
    "cache_prefix": "maven-jdk8-3.3.9-18e8bd367c73",
    "actions": {
        "actions/checkout": {
            "version": "v4.4.0", "sha": "11d5960a326750d5838078e36cf38b85af677262",
            "accepted_inputs": ["v4.1.0", "v4.4.0", "11d5960a326750d5838078e36cf38b85af677262"],
        },
        "actions/cache": {
            "version": "v4.3.0", "sha": "0057852bfaa89a56745cba8c7296529d2fc39830",
            "accepted_inputs": ["v3.3.2", "v4.3.0", "0057852bfaa89a56745cba8c7296529d2fc39830"],
        },
    },
}
BAD_IF = re.compile(r"^(?P<indent> +)if: !\(github\.ref == 'refs/heads/(?P<branch>[A-Za-z0-9_./-]+)'\)(?P<tail>\s*(?:#.*)?)$", re.MULTILINE)


class Unsupported(ValueError):
    """The input cannot be transformed without inferring new behavior."""


def read(path):
    return Path(path).read_text(encoding="utf-8-sig")


def yaml_engine():
    y = YAML(typ="rt")
    y.preserve_quotes = True
    y.width = 1000
    y.allow_duplicate_keys = False
    return y


def load_yaml(text):
    data = yaml_engine().load(text)
    if not isinstance(data, dict):
        raise Unsupported("Expected a YAML mapping.")
    def check(value):
        tag = getattr(value, "tag", None)
        if tag is not None and str(tag) not in ("None", "tag:yaml.org,2002:map", "tag:yaml.org,2002:seq"):
            raise Unsupported(f"Unrecognized YAML tag {tag}; refusing to discard it.")
        if isinstance(value, dict):
            for k, v in value.items():
                check(k)
                check(v)
        elif isinstance(value, list):
            for item in value:
                check(item)
    check(data)
    return data


def dump_yaml(data):
    out = io.StringIO()
    yaml_engine().dump(data, out)
    return out.getvalue()


def condition(branch):
    return "${{ github.ref != 'refs/heads/" + branch + "' }}"


def normalize_condition(text):
    changes = []
    def replace(match):
        replacement = match["indent"] + "if: " + condition(match["branch"]) + match["tail"]
        changes.append({"rule": "T1", "location": f"line {text[:match.start()].count(chr(10)) + 1}",
                        "before": match[0].strip(), "after": replacement.strip(),
                        "reason": "Escape YAML's reserved ! notation without changing the branch exclusion."})
        return replacement
    return BAD_IF.sub(replace, text), changes


def source_contract(text, policy):
    source = load_yaml(text)
    globals_ = {"variables", "image", "cache", "stages"}
    jobs = [(k, v) for k, v in source.items() if k not in globals_ and not str(k).startswith(".")]
    if len(jobs) != 1 or not isinstance(jobs[0][1], dict):
        raise Unsupported("This POC supports one concrete GitLab Maven job; includes, rules and additional jobs need review.")
    name, job = jobs[0]
    if set(job) - {"stage", "script", "except"}:
        raise Unsupported("Unsupported GitLab job settings: " + ", ".join(sorted(set(job) - {"stage", "script", "except"})))
    if source.get("image") != policy["image"] or source.get("cache") != {"paths": [".m2/repository"]}:
        raise Unsupported("Source image/cache does not match the tested Maven profile.")
    commands = job.get("script", [])
    if not isinstance(commands, list) or len(commands) != 1 or not isinstance(commands[0], str) or not commands[0].startswith("mvn $MAVEN_CLI_OPTS ") or "\n" in commands[0] or "${{" in commands[0]:
        raise Unsupported("Expected one single-line Maven command using MAVEN_CLI_OPTS.")
    excluded = job.get("except", [])
    if not isinstance(excluded, list) or len(excluded) != 1 or not isinstance(excluded[0], str) or not re.fullmatch(r"[A-Za-z0-9_./-]+", excluded[0]):
        raise Unsupported("Expected one literal excluded branch.")
    env = source.get("variables", {})
    if not isinstance(env, dict) or set(env) != {"MAVEN_OPTS", "MAVEN_CLI_OPTS"} or not all(isinstance(v, str) for v in env.values()):
        raise Unsupported("Only MAVEN_OPTS and MAVEN_CLI_OPTS are supported by this execution profile.")
    if "-Dmaven.repo.local=$CI_PROJECT_DIR/.m2/repository" not in env["MAVEN_OPTS"]:
        raise Unsupported("Expected workspace-local Maven repository.")
    return {"source_job": name, "command": commands[0], "excluded_branch": excluded[0],
            "image": source["image"], "env": {k: v.replace("$CI_PROJECT_DIR", "${{ github.workspace }}") for k, v in env.items()}}


def docker_script(contract, policy):
    # Run as the host uid so both build outputs and the Maven cache remain readable/writable.
    # This is a shell variable, never an expression containing event-controlled text.
    return '\n'.join([
        "docker run --rm \\",
        '  --user "$(id -u):$(id -g)" \\',
        '  --env HOME=/tmp --env MAVEN_CONFIG=/tmp \\',
        '  --env MAVEN_OPTS --env MAVEN_CLI_OPTS \\',
        '  --volume "$GITHUB_WORKSPACE:$GITHUB_WORKSPACE" \\',
        '  --workdir "$GITHUB_WORKSPACE" \\',
        "  " + policy["image_digest"] + " \\",
        "  sh -c " + shlex.quote(contract["command"]),
    ]) + "\n"


def cache_key(policy):
    return "${{ runner.os }}-" + policy["cache_prefix"] + "-${{ hashFiles('**/pom.xml') }}"


def profile(workflow, contract, policy):
    if set(workflow) - {"name", "on", "concurrency", "jobs", "permissions"}:
        raise Unsupported("Unknown top-level workflow behavior requires review.")
    if workflow.get("on") != {"push": None, "workflow_dispatch": None}:
        raise Unsupported("Expected unfiltered push and workflow_dispatch triggers; refusing to infer event semantics.")
    jobs = workflow.get("jobs", {})
    if not isinstance(jobs, dict) or len(jobs) != 1:
        raise Unsupported("Expected exactly one Actions job.")
    job_id, job = next(iter(jobs.items()))
    if not isinstance(job, dict):
        raise Unsupported("Expected a job mapping.")
    if set(job) - {"runs-on", "container", "if", "timeout-minutes", "env", "steps", "name"}:
        raise Unsupported("Job services, defaults, matrices, permissions or additional settings require review.")
    if job.get("runs-on") != "ubuntu-latest":
        raise Unsupported("Execution profile requires ubuntu-latest with Docker available.")
    if job.get("env") != contract["env"] or job.get("if") != condition(contract["excluded_branch"]):
        raise Unsupported("Workflow environment/branch condition differs from the source contract.")
    steps = job.get("steps", [])
    if not isinstance(steps, list) or len(steps) != 3 or not all(isinstance(s, dict) for s in steps):
        raise Unsupported("Expected checkout, cache, and one Maven step in that order.")
    for step, expected in zip(steps[:2], ("actions/checkout", "actions/cache")):
        if set(step) - {"uses", "with", "name"}:
            raise Unsupported("Extra action step behavior requires review.")
        action, sep, version = str(step.get("uses", "")).partition("@")
        if not sep or action != expected or version not in policy["actions"][action]["accepted_inputs"]:
            raise Unsupported(f"Unreviewed action/version: {step.get('uses')}")
    if steps[0].get("with") != {"fetch-depth": 0, "lfs": True}:
        raise Unsupported("Unrecognized checkout options; a checkout path or ref change requires review.")
    cache = steps[1].get("with", {})
    if not isinstance(cache, dict) or cache.get("path") != ".m2/repository" or set(cache) - {"path", "key", "restore-keys"}:
        raise Unsupported("Unrecognized cache options.")
    expected_prefix = "${{ runner.os }}-" + policy["cache_prefix"] + "-\n"
    if cache.get("key") not in ("default", cache_key(policy)) or cache.get("restore-keys") not in (None, expected_prefix):
        raise Unsupported("Custom cache policy requires review.")
    run = steps[2]
    if "container" in job:
        if job["container"] != {"image": policy["image"]} or set(run) - {"run", "name"} or run.get("run") != contract["command"]:
            raise Unsupported("Unrecognized container/script settings; refusing automatic relocation.")
        wrapped = False
    else:
        if set(run) - {"run", "name", "shell"} or run.get("shell") != "bash" or run.get("run") != docker_script(contract, policy):
            raise Unsupported("Host execution must match this tool's exact Docker recipe.")
        wrapped = True
    return job_id, job, wrapped


def enhance(baseline_text, source_text, policy=POLICY):
    normalized, changes = normalize_condition(baseline_text)
    data = load_yaml(normalized)
    contract = source_contract(source_text, policy)
    job_id, job, wrapped = profile(data, contract, policy)
    def record(rule, location, before, after, reason):
        changes.append({"rule": rule, "location": f"jobs.{job_id}.{location}", "before": before, "after": after, "reason": reason})
    for index, step in enumerate(job["steps"][:2]):
        action = step["uses"].split("@")[0]
        entry = policy["actions"][action]
        replacement = action + "@" + entry["sha"]
        if step["uses"] != replacement:
            record("T2", f"steps[{index}].uses", str(step["uses"]), replacement,
                   f"Approved immutable {action} {entry['version']}; JavaScript runs on the host.")
            step["uses"] = replacement
            step.yaml_add_eol_comment(entry["version"], "uses")
    if not wrapped:
        before = {"container": dict(job["container"]), "run": str(job["steps"][2]["run"])}
        del job["container"]
        step = job["steps"][2]
        step["name"] = step.get("name", "Verify using the original Maven and Java versions")
        step["shell"] = "bash"
        step["run"] = LiteralScalarString(docker_script(contract, policy))
        record("T3", "container / steps[2]", before, {"run": str(step["run"])},
               "Move Actions runtime to Ubuntu; retain the exact Maven image digest and propagate the Docker/Maven exit code.")
    cache = job["steps"][1]["with"]
    desired = {"path": ".m2/repository", "key": cache_key(policy),
               "restore-keys": "${{ runner.os }}-" + policy["cache_prefix"] + "-\n"}
    if dict(cache) != desired:
        before = dict(cache)
        cache.update(desired)
        cache["restore-keys"] = LiteralScalarString(cache["restore-keys"])
        record("T4", "steps[1].with", before, desired,
               "Use a toolchain/POM-specific cache identity; deliberate cache-policy improvement.")
    # Return original bytes-as-text when already transformed, including formatting.
    result = dump_yaml(data) if changes else baseline_text
    profile(load_yaml(result), contract, policy)
    return result, changes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_BASELINE, help="Imported workflow (defaults to your existing baseline)")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="Original GitLab YAML for transformation preconditions")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Enhanced YAML; repeated runs replace this output")
    args = parser.parse_args(argv)
    try:
        output = args.output.resolve()
        protected = {p.resolve() for p in (args.input, args.source, DEFAULT_BASELINE, DEFAULT_SOURCE)}
        if output in protected:
            raise Unsupported("Output must be separate from the input and source files.")
        if not output.is_relative_to((ROOT / "output").resolve()):
            raise Unsupported("Write generated YAML under this tool's output/ directory.")
        result, changes = enhance(read(args.input), read(args.source))
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as stream:
            stream.write(result)
        print(f"Wrote: {output}")
        print(f"Applied {len(changes)} change(s).")
        for change in changes:
            print(f"  {change['rule']}: {change['reason']}")
        return 0
    except (Unsupported, OSError, YAMLError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
