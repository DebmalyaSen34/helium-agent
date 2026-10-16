import os

from dotenv_lite.parser import parse


def load(path: str, override: bool = False) -> dict[str, str]:
    with open(path, encoding="utf-8") as handle:
        values = parse(handle.read())
    for key, value in values.items():
        if override or key not in os.environ:
            os.environ[key] = value
    return values
