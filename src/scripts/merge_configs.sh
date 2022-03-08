#!/usr/bin/env bash

Merge() {
  if [ ! -f "${MODULES_PATH}" ] || [ ! -s "${MODULES_PATH}" ]
  then
    echo 'Nothing to merge. Halting the job.'
    circleci-agent step halt
    exit
  fi

  # shellcheck disable=SC2016
  if xargs yq -y -s 'reduce .[] as $item ({}; . * $item)' < "${MODULES_PATH}" | tee "${CONTINUE_CONFIG}"; then
      echo "Configs merged successfully at ${CONTINUE_CONFIG}"
  else
      echo "Failed to merge configs"
      exit 1
  fi
}

# Will not run if sourced for bats-core tests.
# View src/tests for more information.
ORB_TEST_ENV="bats-core"
if [ "${0#*$ORB_TEST_ENV}" == "$0" ]; then
    Merge
fi
