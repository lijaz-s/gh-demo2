# Independent checks of the real importer outputs, plus native-hook refusal tests.
# Run using the Ruby already supplied in the importer image.
require "yaml"
require_relative "postprocess"

def assert(label, condition)
  raise "FAIL: #{label}" unless condition
  puts "PASS: #{label}"
end

def rejects(label)
  begin
    yield
  rescue RuntimeError
    puts "PASS: #{label}"
    return
  end
  raise "FAIL: #{label} was accepted"
end

baseline_path, native_path, final_path, source_path = ARGV
abort "Usage: tests.rb BASELINE NATIVE FINAL SOURCE" unless source_path
baseline_text = File.read(baseline_path).gsub("\r\n", "\n")
native_text = File.read(native_path).gsub("\r\n", "\n")
final_text = File.read(final_path).gsub("\r\n", "\n")
parse = ->(text) { YAML.safe_load(text.sub(Compatibility::BAD_CONDITION, Compatibility::GOOD_CONDITION), aliases: true) }
baseline, native, final = [baseline_text, native_text, final_text].map(&parse)
source = YAML.safe_load(File.read(source_path), aliases: true)
before = baseline.fetch("jobs").fetch("verify-jdk8")
during = native.fetch("jobs").fetch("verify-jdk8")
after = final.fetch("jobs").fetch("verify-jdk8")

assert("one job preserved", baseline["jobs"].keys == native["jobs"].keys && native["jobs"].keys == final["jobs"].keys && final["jobs"].length == 1)
assert("triggers, name and concurrency preserved", baseline.reject { |k,_| k == "jobs" } == final.reject { |k,_| k == "jobs" })
assert("environment and timeout preserved", before["env"] == after["env"] && before["timeout-minutes"] == after["timeout-minutes"])
assert("source Maven command retained", source.fetch("verify:jdk8")["script"] == ["mvn $MAVEN_CLI_OPTS verify"] && after["steps"].last["run"].rstrip.end_with?("sh -c 'mvn $MAVEN_CLI_OPTS verify'"))
expected_env = source.fetch("variables").transform_values { |v| v.gsub("$CI_PROJECT_DIR", '${{ github.workspace }}') }
assert("source Maven environment retained", expected_env == after["env"])
assert("master exclusion retained", source.fetch("verify:jdk8")["except"] == ["master"] && after["if"] == "${{ github.ref != 'refs/heads/master' }}")
assert("native runner mapping applied", during["runs-on"] == "ubuntu-24.04")
assert("native checkout retains original options", during["steps"][0]["with"] == before["steps"][0]["with"])
assert("native cache uses POM identity", during["steps"][1]["with"]["key"].include?("hashFiles('**/pom.xml')"))
assert("native script uses original image digest", during["steps"].last["run"].include?(Compatibility::IMAGE) && source["image"] == "maven:3.3.9-jdk-8")
assert("postprocessing changes only container and condition text", Compatibility.apply(native_text).first == final_text)
assert("native steps survive postprocessing unchanged", during["steps"] == after["steps"] && !after.key?("container"))
assert("no error suppression introduced", !after["steps"].any? { |s| s.key?("continue-on-error") } && !after["steps"].last["run"].include?("|| true"))

# Load the actual DSL file into a minimal registration object, not a second converter.
dsl = Object.new
def dsl.runner(*); end
def dsl.transform(identifier, &block); (@hooks ||= {})[identifier] = block; end
def dsl.hooks; @hooks; end
file = File.join(__dir__, "transformers/maven.rb")
dsl.instance_eval(File.read(file), file)
rejects("unknown script refused") { dsl.hooks.fetch("script").call("echo something else") }
rejects("unknown cache shape refused") { dsl.hooks.fetch("cache").call({"paths" => ["other"]}) }
rejects("unknown checkout options refused") { dsl.hooks.fetch("checkout").call({"path" => "elsewhere"}) }
rejects("postprocessor refuses missing native script") { Compatibility.apply(native_text.sub("docker run --rm", "echo removed")) }
puts "17 checks passed. Static assertions only; no GitHub-hosted execution."
