# Two bounded compatibility edits after native conversion. No general YAML rewrite.
require "yaml"

module Compatibility
  BAD_CONDITION = "    if: !(github.ref == 'refs/heads/master')"
  GOOD_CONDITION = "    if: ${{ github.ref != 'refs/heads/master' }}"
  CONTAINER = "    container:\n      image: maven:3.3.9-jdk-8\n"
  IMAGE = "maven@sha256:18e8bd367c73c93e29d62571ee235e106b18bf6718aeb235c7a07840328bba71"

  def self.apply(input)
    text = input.gsub("\r\n", "\n")
    raise "Expected the known branch condition exactly once" unless text.lines.count { |line| line.chomp == BAD_CONDITION } == 1
    fixed = text.sub(BAD_CONDITION, GOOD_CONDITION)
    # Parse only to guard the edits. Do not serialize: Psych treats YAML 1.1 'on' as boolean.
    document = YAML.safe_load(fixed, aliases: true)
    jobs = document.fetch("jobs")
    raise "Only the verify-jdk8 job is supported" unless jobs.keys == ["verify-jdk8"]
    job = jobs.fetch("verify-jdk8")
    raise "Unreviewed container options" unless job["container"] == {"image" => "maven:3.3.9-jdk-8"}
    raise "Services need a separate migration design" if job.key?("services")
    steps = job.fetch("steps")
    raise "Expected the three native-transformed steps" unless steps.length == 3
    raise "Native checkout hook missing" unless steps[0]["uses"] == "actions/checkout@11d5960a326750d5838078e36cf38b85af677262"
    raise "Native cache hook missing" unless steps[1]["uses"] == "actions/cache@0057852bfaa89a56745cba8c7296529d2fc39830"
    script = steps[2].fetch("run")
    raise "Native Maven Docker step missing" unless script.start_with?("docker run --rm") && script.include?(IMAGE) && script.rstrip.end_with?("sh -c 'mvn $MAVEN_CLI_OPTS verify'")
    raise "Unexpected container indentation/shape" unless fixed.scan(CONTAINER).length == 1
    [fixed.sub(CONTAINER, ""), ["Escape the job condition", "Remove the legacy job container; Maven already runs in Docker via the native script hook"]]
  end
end

if $PROGRAM_NAME == __FILE__
  abort "Usage: postprocess.rb INPUT OUTPUT" unless ARGV.length == 2
  abort "Input and output must differ" if File.expand_path(ARGV[0]) == File.expand_path(ARGV[1])
  result, changes = Compatibility.apply(File.read(ARGV[0]))
  File.write(ARGV[1], result)
  puts changes.map { |change| "POSTPROCESS: #{change}" }
end
