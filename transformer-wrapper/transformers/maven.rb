# Native GitHub Actions Importer DSL. Passed to --custom-transformers.
# Scoped to the supplied Maven pipeline; unfamiliar input fails explicitly.

runner :default, "ubuntu-24.04"

transform "checkout" do |item|
  expected = {"fetch-depth" => 0, "lfs" => true}
  raise "Unreviewed checkout options: extend this rule deliberately" unless item == true || item == expected
  warn "NATIVE_TRANSFORM: checkout"
  result = {uses: "actions/checkout@11d5960a326750d5838078e36cf38b85af677262"} # v4.4.0
  result[:with] = item unless item == true
  result
end

transform "cache" do |item|
  raise "Expected only the Maven repository cache" unless item == {"paths" => [".m2/repository"]}
  warn "NATIVE_TRANSFORM: cache"
  {
    uses: "actions/cache@0057852bfaa89a56745cba8c7296529d2fc39830", # v4.3.0
    with: {
      path: ".m2/repository",
      key: "${{ runner.os }}-maven-jdk8-3.3.9-${{ hashFiles('**/pom.xml') }}",
      "restore-keys": "${{ runner.os }}-maven-jdk8-3.3.9-"
    }
  }
end

transform "script" do |item|
  raise "Expected the supplied Maven verify command" unless item == "mvn $MAVEN_CLI_OPTS verify"
  warn "NATIVE_TRANSFORM: script"
  {
    name: "Verify with the original Maven and Java versions",
    shell: "bash",
    run: <<~BASH
      docker run --rm \\
        --user "$(id -u):$(id -g)" \\
        --env HOME=/tmp --env MAVEN_CONFIG=/tmp \\
        --env MAVEN_OPTS --env MAVEN_CLI_OPTS \\
        --volume "$GITHUB_WORKSPACE:$GITHUB_WORKSPACE" \\
        --workdir "$GITHUB_WORKSPACE" \\
        maven@sha256:18e8bd367c73c93e29d62571ee235e106b18bf6718aeb235c7a07840328bba71 \\
        sh -c '#{item}'
    BASH
  }
end
