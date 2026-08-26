import os
from pathlib import Path


DEFAULT_ENVIRONMENT_FILE_PATH = Path(".env")
ENVIRONMENT_ASSIGNMENT_SEPARATOR = "="
SUPPORTED_QUOTE_CHARACTERS = {"'", '"'}


def load_environment_file(
    environment_file_path: Path = DEFAULT_ENVIRONMENT_FILE_PATH,
) -> None:
    if not environment_file_path.exists():
        return

    for raw_line in environment_file_path.read_text(encoding="utf-8").splitlines():
        stripped_line = raw_line.strip()
        if not stripped_line or stripped_line.startswith("#"):
            continue
        if ENVIRONMENT_ASSIGNMENT_SEPARATOR not in stripped_line:
            continue

        variable_name, variable_value = stripped_line.split(
            ENVIRONMENT_ASSIGNMENT_SEPARATOR,
            maxsplit=1,
        )
        normalized_name = variable_name.strip()
        normalized_value = remove_matching_quotes(variable_value.strip())
        if normalized_name:
            os.environ.setdefault(normalized_name, normalized_value)


def remove_matching_quotes(value: str) -> str:
    if len(value) < 2:
        return value
    first_character = value[0]
    last_character = value[-1]
    if first_character == last_character and first_character in SUPPORTED_QUOTE_CHARACTERS:
        return value[1:-1]
    return value

