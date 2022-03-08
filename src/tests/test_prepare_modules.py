import pytest

from src.scripts.prepare_modules import get_modules, check_configs_exist, dump_modules, main
from src.tests.conftest import does_not_raise


@pytest.mark.parametrize(
    "modules, expected",
    [
        (["module1", "module2"], {"module1/.circleci/config.yml", "module2/.circleci/config.yml"}),
        (["module1/", "module2/"], {"module1/.circleci/config.yml", "module2/.circleci/config.yml"}),
        (["module1/.circleci/config.yml\n"], {"module1/.circleci/config.yml"}),
        (["module1/.circleci/config.yml"], {"module1/.circleci/config.yml"}),
        ([".circleci/common_config.yml"], {".circleci/common_config.yml"}),
        ([], set()),
        ([""], set()),
    ]
)
def test_get_modules(modules, expected):
    assert get_modules(modules) == expected


@pytest.mark.parametrize(
    "files, expected_paths, expectation",
    [
        (["one", "two"], ["one", "two"], does_not_raise()),
        (["one"], ["one", "two"], pytest.raises(FileNotFoundError)),
    ], indirect=["files"]
)
def test_check_configs_exist(tmpdir, files, expected_paths, expectation):  # pylint: disable=unused-argument
    expected_paths = [tmpdir / x for x in expected_paths]
    with expectation:
        check_configs_exist(expected_paths)


def test_dump_modules(monkeypatch, tmpdir):
    path = tmpdir / "modules.txt"
    to_dump = ["test\n", "test2\n"]
    monkeypatch.setenv("MODULES_PATH", str(path))
    dump_modules(to_dump)
    with open(path) as fd:
        assert fd.readlines() == to_dump


@pytest.mark.parametrize(
    "modules_file, expected",
    [
        (["module1", "module2"], ["module1/.circleci/config.yml\n", "module2/.circleci/config.yml\n"]),
        ([], []),
    ], indirect=["modules_file"]
)
def test_main(monkeypatch, tmpdir, modules_file, expected):
    monkeypatch.setenv("MODULES_PATH", str(modules_file))
    monkeypatch.setattr("src.scripts.prepare_modules.check_configs_exist", lambda x: True)
    main()
    with open(str(modules_file)) as fd:
        assert sorted(fd.readlines()) == sorted(expected)


def test_main_file_check(monkeypatch, tmpdir, test_data_dir):
    modules_file = tmpdir / "modules.txt"
    monkeypatch.setenv("MODULES_PATH", str(modules_file))
    check_files = [
        str(test_data_dir / 'yaml' / 'config.yaml') + "\n",
        str(test_data_dir / 'yaml' / 'custom-config.yaml') + "\n",
    ]

    with open(modules_file, 'w') as fd:
        fd.writelines(check_files)

    main()
