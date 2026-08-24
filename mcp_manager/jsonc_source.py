"""JSONC adapter facade."""

from .json_source import (  # noqa: F401
    DuplicateKeyError,
    SourceParseError,
    apply_operation,
    find_node,
    loads,
    parse,
)
