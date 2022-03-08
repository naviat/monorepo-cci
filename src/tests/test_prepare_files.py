from subprocess import CalledProcessError

import re

from json import load, dumps
from json.decoder import JSONDecodeError
from time import sleep

import httpretty
import pytest

from src.scripts.prepare_files import (
    main, get_mappings, get_base, convert_mapping, find_parent_commit, get_base_from_pull,
    match, check_mapping, set_params_and_modules, log_block, find_diff_files, get_commit_part
)
from src.tests.conftest import does_not_raise


@pytest.mark.parametrize(
    "mappings, expected",
    [
        ("#comments", []),
        ("", []),
        ('path:^pattern$;module;{"parameter":"value"}', [
         ["path:^pattern$", "module", '{"parameter":"value"}']]),
        ('''
        path:^pattern$;module;{"parameter":"value"}
        # comment
        ''', [["path:^pattern$", "module", '{"parameter":"value"}']]),
    ]
)
def test_get_mappings(mappings, expected):
    assert get_mappings(mappings) == expected


@pytest.mark.parametrize(
    "base_revision, circle_branch, _find_parent_commit, expected",
    [
        ("main", "", None, "main"),
        ("", "circle_branch", lambda x, y: "main", "main"),
        ("", "", lambda x, y: None, "HEAD~1"),
    ]
)
def test_get_base(monkeypatch, base_revision, circle_branch, _find_parent_commit, expected):
    monkeypatch.setenv("BASE_REVISION", base_revision)
    monkeypatch.setenv("CIRCLE_BRANCH", circle_branch)
    monkeypatch.setattr(
        "src.scripts.prepare_files.find_parent_commit", _find_parent_commit)

    assert get_base() == expected


def test_get_base_missing_gt_token(monkeypatch, capsys):
    monkeypatch.setenv("GET_BASE_FROM_GITHUB", "true")
    monkeypatch.setenv("CIRCLE_PULL_REQUEST", "foo.bar/pull/1")
    monkeypatch.setattr(
        "src.scripts.prepare_files.find_parent_commit", lambda *args: "main")

    assert get_base() == "main"
    out, _ = capsys.readouterr()

    assert "GET_BASE_FROM_GITHUB environment variable is set, but GITHUB_TOKEN is missing." in out


@httpretty.activate(allow_net_connect=False)
def test_get_base_with_pull(monkeypatch, test_data_dir):
    org, repo, pull_number = "foo", "bar", "1"
    monkeypatch.setenv("CIRCLE_PROJECT_USERNAME", org)
    monkeypatch.setenv("CIRCLE_PROJECT_REPONAME", repo)
    monkeypatch.setenv("CIRCLE_PULL_REQUEST", "foo.bar/pull/1")
    monkeypatch.setenv("GITHUB_TOKEN", "foo")
    monkeypatch.setenv("GET_BASE_FROM_GITHUB", "true")
    monkeypatch.setenv("BASE_REVISION", "")
    with open(test_data_dir / "json" / "gh_pr_resp.json") as fd:
        resp = dumps(load(fd))

    httpretty.register_uri(
        httpretty.GET,
        f"https://api.github.com/repos/{org}/{repo}/pulls/{pull_number}",
        body=resp
    )

    assert get_base() == "main"


@httpretty.activate(allow_net_connect=False)
def test_get_base_with_pull_raises(monkeypatch, capsys):
    monkeypatch.setattr(
        "src.scripts.prepare_files.find_parent_commit", lambda x, y: "main")
    org, repo, pull_number = "foo", "bar", "1"
    monkeypatch.setenv("CIRCLE_PROJECT_USERNAME", org)
    monkeypatch.setenv("CIRCLE_PROJECT_REPONAME", repo)
    monkeypatch.setenv("CIRCLE_PULL_REQUEST", "foo.bar/pull/1")
    monkeypatch.setenv("GITHUB_TOKEN", "foo")
    monkeypatch.setenv("GET_BASE_FROM_GITHUB", "true")
    monkeypatch.setenv("BASE_REVISION", "")

    httpretty.register_uri(
        httpretty.GET,
        f"https://api.github.com/repos/{org}/{repo}/pulls/{pull_number}",
        body="",
        status=500
    )

    assert get_base() == "main"

    out, _ = capsys.readouterr()

    assert "get base from github FAILED" in out


@pytest.mark.parametrize(
    "mapping, expected, expectation",
    [
        (["path:pattern", "module", '{"parameter":"value"}'], ("module", {
         "parameter": "value"}), does_not_raise()),
        (["path:pattern", "module/", '{}'], ("module/", {}), does_not_raise()),
        (["path:pattern", ".", '{}'], (".", {}), does_not_raise()),
        (["path:pattern", "", '{}'], ("", {}), does_not_raise()),
        (["path:pattern", "module/", ''],
         ("module/", {}), pytest.raises(JSONDecodeError)),
        (["path:pattern", "module/", 'invalid obj'],
         ("module/", {}), pytest.raises(JSONDecodeError)),
    ]
)
def test_convert_mapping(mapping, expected, expectation):
    with expectation:
        assert convert_mapping(mapping) == expected


@pytest.mark.parametrize(
    "pattern, haystack, expected",
    [
        (re.compile(r"^module$"), "module", True),
        (re.compile(r"^module$"), "module1", False),
    ]
)
def test_match(pattern, haystack, expected):
    assert match(pattern, haystack, "") == expected


@pytest.mark.parametrize(
    "mapping, changed_files, branch, tag, subject, expected, expectation",
    [
        (list(range(0)), None, None, None, None, True, pytest.raises(ValueError)),
        (list(range(1)), None, None, None, None, True, pytest.raises(ValueError)),
        (list(range(2)), None, None, None, None, True, pytest.raises(ValueError)),
        (list(range(4)), None, None, None, None, True, pytest.raises(ValueError)),
        # only the first part of the mapping is used here
        (["path:^module1", None, None], "module1/file",
         None, None, None, True, does_not_raise()),
        (["path:^module1", None, None], "module2/file",
         None, None, None, False, does_not_raise()),
        (["branch:^work-branch", None, None], None,
         "work-branch", None, None, True, does_not_raise()),
        (["branch:^work-branch", None, None], None,
         "other-branch", None, None, False, does_not_raise()),
        (["tag:^release", None, None], None, None,
         "release-1", None, True, does_not_raise()),
        (["tag:^release", None, None], None, None,
         "dev-1", None, False, does_not_raise()),
        (["subject:^foo", None, None], None, None,
         None, "foo", True, does_not_raise()),
        (["subject:^bar", None, None], None, None,
         None, "foo", False, does_not_raise()),
        (["foo:^bar", None, None], None, None, None,
         None, None, pytest.raises(NotImplementedError)),
    ]
)
def test_check_mapping(monkeypatch, mapping, changed_files, branch, tag, subject, expected, expectation):
    monkeypatch.setenv("CIRCLE_BRANCH", str(branch))
    monkeypatch.setenv("CIRCLE_TAG", str(tag))
    monkeypatch.setattr(
        "src.scripts.prepare_files.get_commit_part", lambda x: subject)

    with expectation:
        assert check_mapping(mapping, changed_files) == expected


@pytest.mark.parametrize(
    "default_params, default_modules, diff, mappings, expected_params, expected_modules_file",
    [
        (
            "{}", "", "module/file1",
            [["path:^module/", "module/", '{"parameter":"value"}']],
            {"parameter": "value"}, "set_modules_single_module.txt"
        ),
        (
            '{}', '', "module/file1",
            [["path:.", "module/,module_foo/,module_bar/",
                '{"parameter":"value"}']],
            {"parameter": "value"}, "set_modules_multiple_modules_different_names.txt"
        ),
        (
            '{}', '', "module/file1",
            [["path:.", "", '{"parameter":"value"}']],
            {"parameter": "value"}, "empty.txt"
        ),
        (
            '{}', '', "module/file1",
            [["path:.", " ", '{"parameter":"value"}']],
            {"parameter": "value"}, "empty.txt"
        ),
        (
            '{}', '', "module/file1",
            [["path:.", ", ,", '{"parameter":"value"}']],
            {"parameter": "value"}, "empty.txt"
        ),
        (
            "{}", "", "module/file1",
            [["path:^module", "module/", '{"parameter":"value"}'],
                ["path:^module", "module/", '{"parameter2":true}']],
            {"parameter": "value",
                "parameter2": True}, "set_modules_two_modules_same_name.txt"
        ),
        (
            '{"parameter2":true}', "module_foo/, module_bar/", "module/file1",
            [["path:^module", "module/", '{"parameter":"value"}']],
            {"parameter": "value",
                "parameter2": True}, "set_modules_multiple_modules_different_names.txt"
        ),
        (
            '{"parameter2":true}', 'module_foo/', "module/file1",
            [["path:^module_foo", "module/", '{"parameter":"value"}']],
            {"parameter2": True}, "set_modules_single_module_foo.txt"
        ),
        (
            '{}', "", "module/file1",
            [["path:^module_foo", "module", '{"parameter":"value"}']],
            {}, "empty.txt"
        ),
    ]
)
def test_set_params(
    monkeypatch,
    tmpdir,
    test_data_dir,
    default_params,
    default_modules,
    diff,
    mappings,
    expected_params,
    expected_modules_file
):
    params_out_path = tmpdir / "pipeline-parameters.json"
    modules_out_path = tmpdir / "modules.txt"
    modules_expected_file = test_data_dir / "txt" / expected_modules_file
    monkeypatch.setenv("PARAMS_PATH", str(params_out_path))
    monkeypatch.setenv("MODULES_PATH", str(modules_out_path))
    monkeypatch.setenv("DEFAULT_PARAMS", default_params)
    monkeypatch.setenv("DEFAULT_MODULES", default_modules)

    set_params_and_modules(diff, mappings)

    with open(params_out_path) as fd:
        assert load(fd) == expected_params

    with open(modules_out_path) as out, open(modules_expected_file) as expected:
        assert sorted(out.readlines()) == sorted(expected.readlines())


def test_log_block(capsys):
    log_block("name", {"data": True})
    captured = capsys.readouterr()

    assert "name" in captured.out
    assert str({"data": True}) in captured.out


def test_find_diff_files(monkeypatch, test_git_repo):
    git_repo, _ = test_git_repo
    monkeypatch.chdir(git_repo.workspace)
    assert 'changed_file' in find_diff_files('main', 'new_branch')


@pytest.mark.parametrize(
    "max_age, since, expected",
    [
        ("4", 1, None),
        ("0", 1, None),
        ("1", 2, ""),
    ]
)
def test_find_parent_commit(monkeypatch, test_git_repo, max_age, since, expected):
    monkeypatch.setenv("MAX_AGE", max_age)
    git_repo, commits = test_git_repo
    monkeypatch.chdir(git_repo.workspace)
    if isinstance(expected, str):
        assert find_parent_commit('new_branch', '', since) == ""
    else:
        assert find_parent_commit('new_branch', '', since) == commits[0]


def test_find_parent_commit_recursion(capfd, monkeypatch, test_git_repo):
    monkeypatch.setenv("MAX_AGE", "4")
    git_repo, commits = test_git_repo
    monkeypatch.chdir(git_repo.workspace)
    sleep(2)
    parent_commit = find_parent_commit('new_branch', '', 1, "second")
    assert parent_commit == commits[0]
    out, _ = capfd.readouterr()
    assert "Was looking at --after 1.second.ago --before 0.second.ago" in out
    assert "Was looking at --after 2.second.ago --before 1.second.ago" in out


def test_get_commit_part(monkeypatch, test_git_repo):
    git_repo, _ = test_git_repo
    monkeypatch.chdir(git_repo.workspace)
    assert get_commit_part('%s') == "second commit"


def test_main(monkeypatch, tmpdir, test_git_repo):
    git_repo, _ = test_git_repo
    monkeypatch.setenv("CIRCLECI", "true")
    monkeypatch.setenv("MAPPINGS", 'path:changed_file; .; {"param": "val"}')
    monkeypatch.setenv("CIRCLE_BRANCH", "main")
    monkeypatch.setenv("CIRCLE_SHA1", "HEAD")
    out_path = tmpdir / "pipeline-parameters.json"
    monkeypatch.setenv("PARAMS_PATH", str(out_path))
    monkeypatch.setattr(
        "src.scripts.prepare_files.find_parent_commit", lambda x, y, z=1: find_parent_commit(
            x, None, z)
    )
    monkeypatch.chdir(git_repo.workspace)
    main()

    with open(out_path) as fd:
        assert load(fd) == {"param": "val"}


def test_main_outside_ci(monkeypatch):
    monkeypatch.setenv("CIRCLECI", "")
    with pytest.raises(RuntimeError):
        main()


def test_main_diff_fails(monkeypatch, tmpdir, test_git_repo):
    def _raise():
        raise CalledProcessError(128, "git")
    git_repo, _ = test_git_repo
    monkeypatch.setenv("CIRCLECI", "true")
    monkeypatch.setenv("MAPPINGS", 'path:changed_file; .; {"param": "val"}')
    monkeypatch.setenv("CIRCLE_BRANCH", "main")
    monkeypatch.setenv("CIRCLE_SHA1", "HEAD")
    out_path = tmpdir / "pipeline-parameters.json"
    monkeypatch.setenv("PARAMS_PATH", str(out_path))
    monkeypatch.setattr(
        "src.scripts.prepare_files.find_parent_commit", lambda x, y, z=1: find_parent_commit(
            x, None, z)
    )
    monkeypatch.setattr(
        "src.scripts.prepare_files.find_diff_files", lambda x, y, z=1: _raise()
    )
    monkeypatch.chdir(git_repo.workspace)

    with pytest.raises(CalledProcessError):
        main()


@httpretty.activate(allow_net_connect=False)
def test_get_base_from_pull(monkeypatch, test_data_dir):
    org, repo, pull_number = "foo", "bar", "1"
    monkeypatch.setenv("CIRCLE_PROJECT_USERNAME", org)
    monkeypatch.setenv("CIRCLE_PROJECT_REPONAME", repo)
    with open(test_data_dir / "json" / "gh_pr_resp.json") as fd:
        resp = dumps(load(fd))

    httpretty.register_uri(
        httpretty.GET,
        f"https://api.github.com/repos/{org}/{repo}/pulls/{pull_number}",
        body=resp
    )

    assert get_base_from_pull("foo.bar/pull/1", "") == "main"


def test_get_base_from_pull_invalid_url():
    with pytest.raises(ValueError):
        get_base_from_pull("foo", "bar")
