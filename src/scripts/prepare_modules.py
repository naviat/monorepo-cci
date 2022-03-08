#!/usr/bin/env python3

from os import getenv
from typing import Sequence, Iterable, Set

from pathlib import Path


DEFAULT_MODULES_PATH = "/tmp/modules.txt"


def get_modules(input_modules: Sequence[str]) -> Set[str]:
    """
    Takes in a sequence of module names and/or paths to `config.yml` files
    and produce a set of paths to to their CircleCI configs.
    If a path to a config file is supplied - it must end in `config.yml`, otherwise
    `.circleci/config.yml` will be added to the end of the path
    i.e.
        input:  ['module1', 'module2', '.circleci/config.yml', 'path/to/custom-config.yml']
        output: [
             'module1/.circleci/config.yml',
             'module2/.circleci/config.yml',
             '.circleci/config.yml',
             'path/to/custom-config.yml',
         ]
    :param input_modules: sequence of module names and/or paths to config yaml files
    :return: a set of paths to config yaml files
    """
    modules = set()
    for module in input_modules:
        if not module:
            continue

        module = module.strip()
        if module.endswith("config.yml") or module.endswith("config.yaml"):
            modules.add(f"{module}")
            continue

        if module.endswith("/"):
            module = f"{module}.circleci/config.yml"
        else:
            module = f"{module}/.circleci/config.yml"

        modules.add(module)

    return modules


def check_configs_exist(modules: Iterable[str]) -> None:
    """
    Take in a sequence of paths to CircleCI configs in modules and check that all exist.
    :param modules:
    :return:
    """
    for path in modules:
        if not Path(path).exists():
            raise FileNotFoundError(f"Config at '{path}' does not exist")


def dump_modules(modules: Iterable[str]) -> None:
    """
    Take in a sequence of paths to CircleCI configs and write them into a file defined at env[MODULES_PATH].
    :param modules:
    :return:
    """
    with open(getenv("MODULES_PATH", DEFAULT_MODULES_PATH), 'w') as fd:
        fd.writelines([x if x.endswith("\n") else f"{x}\n" for x in modules])


def main() -> None:
    """
    Take modules from DEFAULT_MODULES and MODULES_PATH,
    check that all exist and write unique paths into an output file
    :return:
    """
    with open(getenv("MODULES_PATH", DEFAULT_MODULES_PATH)) as fd:
        modules = get_modules(fd.readlines() or [])  # pylint: disable=R1732

    if not modules:
        print("Modules file is empty")

    check_configs_exist(modules)
    dump_modules(modules)


if __name__ == "__main__":
    main()
