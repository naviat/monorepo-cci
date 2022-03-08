from contextlib import contextmanager
from pathlib import Path

import pytest


@contextmanager
def does_not_raise():
    yield


@pytest.fixture
def modules_file(tmpdir, request):
    if hasattr(request, "param") and getattr(request, "param") is not None:
        path = Path(tmpdir / "modules.txt")
        with open(path, "w") as fd:
            modules = [x if x.endswith("\n") else f"{x}\n" for x in request.param]
            fd.writelines(modules)

        return path
    return None


@pytest.fixture
def files(tmpdir, request):
    paths = []
    if hasattr(request, "param") and getattr(request, "param"):
        for p in request.param:
            path = Path(tmpdir / p)
            path.mkdir(parents=True)
            path.touch()
            paths.append(path)

        print(paths)
        return paths
    return None


@pytest.fixture
def test_git_repo(git_repo):
    commits = []
    base_path = git_repo.workspace
    file = base_path / 'changed_file'
    file.touch()
    git_repo.api.git.remote("add", "origin", ".")
    for branch, msg in zip(["main", "new_branch"], ["init", "second commit"]):
        git_repo.api.git.checkout("-b", branch)
        file.write_text(msg)
        git_repo.api.index.add(["changed_file"])
        commit1 = git_repo.api.index.commit(msg)
        commits.append(str(commit1))

    return git_repo, commits


@pytest.fixture
def test_data_dir(pytestconfig):
    return pytestconfig.rootdir / "src" / "tests" / "data"
