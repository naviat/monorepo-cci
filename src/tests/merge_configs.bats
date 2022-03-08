circleci-agent() {
  return 0
}

# Runs prior to every test
setup() {
    load 'test_helper/bats-support/load'
    load 'test_helper/bats-assert/load'

    source ./src/scripts/merge_configs.sh
    export SCRIPT_DIR="$( cd -- "$( dirname -- "${BATS_TEST_FILENAME}" )" &> /dev/null && pwd )"
    export DATA_DIR="${SCRIPT_DIR}/data"
    export -f circleci-agent
    mkdir -p "${SCRIPT_DIR}/output"
}

@test '1: merge_configs with no modules specified' {
    run Merge
    assert_success
    assert_output --partial "Nothing to merge"
}

@test '2: merge_configs with modules. Non-overlapping configs' {
    export MODULES_PATH="${DATA_DIR}/txt/modules.txt"
    export CONTINUE_CONFIG="${SCRIPT_DIR}/output/test_2_continue_config_$(date +'%m-%d-%yT%H-%M-%S').yml"
    combined="$DATA_DIR/yaml/combined.yaml"
    run Merge
    assert_success
    assert_output --partial "Configs merged successfully"
    assert_equal "$(cat ${CONTINUE_CONFIG})" "$(cat ${combined})"
}

@test '3: merge_configs with modules. Configs 2 and 3 overlap' {
    export MODULES_PATH="${DATA_DIR}/txt/modules_all.txt"
    export CONTINUE_CONFIG="${SCRIPT_DIR}/output/test_3_continue_config_$(date +'%m-%d-%yT%H-%M-%S').yml"
    combined="$DATA_DIR/yaml/combined-with-duplicates.yaml"
    run Merge
    assert_success
    assert_output --partial "Configs merged successfully"
    assert_equal "$(cat ${CONTINUE_CONFIG})" "$(cat ${combined})"
}
