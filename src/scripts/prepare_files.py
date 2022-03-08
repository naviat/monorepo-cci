#!/usr/bin/env python3

import subprocess
import sys
import re
from json import loads, dump, dumps
from os import getenv
from typing import Any, Sequence, Tuple, Optional

import requests

DEFAULT_BASE = "HEAD~1"


def run_cmd(cmd: Sequence[str]) -> str:
    """sumary_line

    Keyword arguments:
    argument -- description
    Return: return_description
    """
    if sys.version_info < (3, 7):
        return subprocess.run(cmd, check=True, stdout=subprocess.PIPE) \
            .stdout.decode("utf-8").strip()  # pragma: no cover
    return subprocess.run(cmd, check=True, capture_output=True).stdout.decode("utf-8").strip()


def find_parent_commit(
    current_branch: str, remote: Optional[str], since: int = 1, timeframe: str = "month"
) -> str:
    """sumary_line

    Keyword arguments:
    argument -- description
    Return: return_description
    """
    max_age = int(getenv("MAX_AGE", "4"))
    no_pager = "--no-pager"

    # during tests we don't have remote
    if remote and not remote.endswith("/"):  # pragma: no cover
        remote += "/"

    if not remote:  # pragma: no cover
        remote = ""

    if max_age and since <= max_age:
        time_limit = ["--after", f"{since}.{timeframe}.ago",
                      "--before", f"{since - 1}.{timeframe}.ago"]
    elif not max_age:
        time_limit = []
    else:
        return ""

    cmd = ["git", no_pager, "rev-list", "--first-parent",
           *time_limit, f"{remote}{current_branch}"]
    commits = run_cmd(cmd).splitlines()
    print(f"{len(commits)} commits to go through. Was looking at {' '.join(time_limit)}")
    for ix, commit in enumerate(commits):
        cmd = ["git", no_pager, "branch", "--contains", commit]
        print(f"Checking {commit}")
        branches = run_cmd(cmd).splitlines()
        if len(branches) > 1:
            base_commit = commits[ix]
            log_block("base commit",
                      f"{base_commit}\npresent in: {branches} branches")
            return base_commit
    # if we went down here - a "parent" commit wasn't
    # found among commits that  happened in the last {since} months
    return find_parent_commit(current_branch, remote, since + 1, timeframe)


def find_diff_files(base: str, head: str, remote: str = None) -> str:
    """sumary_line

    Keyword arguments:
    argument -- description
    Return: return_description
    """
    if remote:
        base = f"{remote}/{base}"  # pragma: no cover  during tests we don't have remote

    diff_commits = f"{base}...{head}"
    print(f"Getting diff: {diff_commits}")
    cmd = ["git", "--no-pager", "diff", "--name-only", diff_commits]
    return run_cmd(cmd)


def check_mapping(mapping: Sequence[str], diff: str) -> bool:
    """sumary_line

    Keyword arguments:
    argument -- description
    Return: return_description
    """
    if len(mapping) != 3:
        raise ValueError(f"Invalid mapping {mapping}")

    search, _, _ = mapping
    where, pattern = search.split(":")
    regex = re.compile(pattern)
    if where == "path":
        success_msg = f"Pattern '{pattern}' matched in diff."
        return any(
            match(regex, change.strip(), success_msg)
            for change in diff.splitlines()
        )

    if where == "branch":
        branch = getenv("CIRCLE_BRANCH", "")
        success_msg = f"Pattern '{pattern}' matched current branch."
        return match(regex, branch, success_msg)

    if where == "tag":
        tag = getenv("CIRCLE_TAG", "")
        success_msg = f"Pattern '{pattern}' matched current tag."
        return match(regex, tag, success_msg)

    if where == "subject":
        subject = get_commit_part("%s")
        if regex.search(subject):
            print(f"Pattern '{pattern}' matched in last commit subject.")
            return True
        return False

    raise NotImplementedError(f"'{where}' search location is not supported")


def get_commit_part(fmt: str, num_commits_back: int = 1) -> str:
    """sumary_line

    Keyword arguments:
    argument -- description
    Return: return_description
    """
    cmd = ["git", "--no-pager", "log",
           f"--pretty={fmt}", "-n", str(num_commits_back)]
    return run_cmd(cmd)


def match(pattern: re.Pattern, haystack: str, success_msg: str) -> bool:
    """sumary_line

    Keyword arguments:
    argument -- description
    Return: return_description
    """
    if pattern.match(haystack):
        print(success_msg)
        return True
    return False


def convert_mapping(mapping: list[str]) -> Tuple[str, dict[str, Any]]:
    """sumary_line

    Keyword arguments:
    argument -- description
    Return: return_description
    """
    return mapping[1], loads(mapping[2])


def set_params_and_modules(diff: str, mappings: list[list[Any]]) -> None:
    """sumary_line

    Keyword arguments:
    argument -- description
    Return: return_description
    """
    param_path = getenv("PARAMS_PATH", '/tmp/pipeline-parameters.json')
    modules_path = getenv("MODULES_PATH", '/tmp/modules.txt')
    params = loads(getenv("DEFAULT_PARAMS", '{}'))
    modules = [x.strip()
               for x in getenv("DEFAULT_MODULES", "").split(",") if x.strip()]
    mappings = [x for x in mappings if check_mapping(x, diff)]
    for mapping in map(convert_mapping, mappings):
        module, new_params = mapping
        params |= new_params
        modules.extend(module.strip().split(','))

    with open(param_path, 'w') as fd:
        dump(params, fd)

    with open(modules_path, 'w') as fd:
        fd.writelines(
            [x if x.endswith("\n") else f"{x}\n" for x in modules if x.strip()])

    log_block("set params", dumps(params, indent=4))


def log_block(name: str, data: Any, divider: str = "=", max_symbols: int = 64) -> None:
    """sumary_line

    Keyword arguments:
    argument -- description
    Return: return_description
    """
    half = (max_symbols - len(name) - 2) // 2
    print(divider * half, name, divider * half, sep=" ")
    print(data, divider * max_symbols, sep="\n")


def get_base(remote: str = None) -> str:
    """sumary_line

    Keyword arguments:
    argument -- description
    Return: return_description
    """
    base = getenv('BASE_REVISION')
    msg = f"Base revision set to {base}"
    # first try to get base from PR, it requires the least resources
    if not base and getenv("GET_BASE_FROM_GITHUB") and (pr_url := getenv("CIRCLE_PULL_REQUEST")):
        if gh_token := getenv("GITHUB_TOKEN"):
            try:
                base = get_base_from_pull(pr_url, gh_token)
                msg = f"Got base from GitHub pull request: {base}"
            except requests.HTTPError as e:
                log_block("get base from github FAILED", str(e))
        else:
            log_block(
                "get base from github",
                "GET_BASE_FROM_GITHUB environment variable is set, but GITHUB_TOKEN is missing. "
                "Cannot proceed to get the base from GitHub pull request."
            )

    if not base:
        current_branch = getenv("CIRCLE_BRANCH", "")
        if not current_branch:
            current_branch = getenv("CIRCLE_TAG", "")
            remote = "tags"
        base = find_parent_commit(current_branch, remote)
        msg = f"Got base commit: {base}"

    if not base:
        base = DEFAULT_BASE
        msg = f"No base found! Will use {base} as base."

    log_block("base_revision", msg)

    return base


def get_base_from_pull(pull_url: str, gh_token: str) -> str:
    """sumary_line

    Keyword arguments:
    argument -- description
    Return: return_description
    """
    org = getenv('CIRCLE_PROJECT_USERNAME')
    repo = getenv('CIRCLE_PROJECT_REPONAME')
    group_name = 'pull_num'
    match_pull = re.search(fr"pull/(?P<{group_name}>\d+)", pull_url)
    if match_pull is None:
        raise ValueError("Invalid pull request url")

    pull_number = match_pull[group_name]
    api_url = f"https://api.github.com/repos/{org}/{repo}/pulls/{pull_number}"
    resp = requests.get(api_url, headers={
                        "Authorization": f"token {gh_token}", "User-Agent": f"{org}"})
    resp.raise_for_status()

    return resp.json().get("base", {}).get("ref", "")


def get_mappings(mappings: str) -> list[list]:
    """sumary_line

    Keyword arguments:
    argument -- description
    Return: return_description
    """
    return [m.strip().split(';') for m in mappings.strip().splitlines() if m and not m.strip().startswith("#")]


def main() -> None:
    """sumary_line

    Keyword arguments:
    argument -- description
    Return: return_description
    """
    if not getenv("CIRCLECI"):
        raise RuntimeError("Running outside of CircleCI environment. Aborting")

    mappings = get_mappings(getenv('MAPPINGS', ''))
    remote = run_cmd(["git", "--no-pager", "remote", "show"]).splitlines()[0]
    base = get_base(remote)
    head = getenv('CIRCLE_SHA1', 'HEAD')
    subprocess.run(["git", "fetch", "--all"], check=True,
                   stdout=sys.stdout, stderr=sys.stderr)
    try:
        diff = find_diff_files(base, head)
    except subprocess.CalledProcessError as e:
        err = str(e)
        if hasattr(e, 'stderr'):  # pragma: no cover
            err = err + "\n" + str(e.stderr)
        log_block("Failed to get diff", err)

        try:
            diff = find_diff_files(base, head, remote)
        except subprocess.CalledProcessError as e:
            err = str(e)
            if hasattr(e, 'stderr'):  # pragma: no cover
                err = err + "\n" + str(e.stderr)
            log_block("Failed to get diff", err)
            print(f"Using fallback base - {DEFAULT_BASE}")
            diff = find_diff_files(DEFAULT_BASE, head)

    log_block("files changed", diff)
    set_params_and_modules(diff, mappings)


if __name__ == "__main__":
    main()
