"""Strict JSON/JSONC parsing and source-range object edits."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


class SourceParseError(ValueError):
    pass


class DuplicateKeyError(SourceParseError):
    pass


@dataclass
class Member:
    key: str
    key_node: "Node"
    value_node: "Node"
    start: int
    end: int
    comma_start: int | None = None
    comma_end: int | None = None


@dataclass
class Node:
    kind: str
    start: int
    end: int
    value: Any
    members: list[Member] = field(default_factory=list)
    items: list["Node"] = field(default_factory=list)


class Parser:
    def __init__(self, source: str, jsonc: bool = False):
        self.source = source
        self.jsonc = jsonc
        self.length = len(source)
        self.decoder = json.JSONDecoder()

    def skip(self, index: int) -> int:
        while index < self.length:
            if self.source[index].isspace():
                index += 1
                continue
            if self.jsonc and self.source.startswith("//", index):
                end = self.source.find("\n", index + 2)
                index = self.length if end < 0 else end + 1
                continue
            if self.jsonc and self.source.startswith("/*", index):
                end = self.source.find("*/", index + 2)
                if end < 0:
                    raise SourceParseError("unterminated comment")
                index = end + 2
                continue
            break
        return index

    def parse(self) -> Node:
        index = self.skip(0)
        node, index = self.value(index)
        index = self.skip(index)
        if index != self.length:
            raise SourceParseError(f"unexpected data at offset {index}")
        return node

    def value(self, index: int) -> tuple[Node, int]:
        index = self.skip(index)
        if index >= self.length:
            raise SourceParseError("unexpected end of input")
        char = self.source[index]
        if char == "{":
            return self.object(index)
        if char == "[":
            return self.array(index)
        try:
            value, end = self.decoder.raw_decode(self.source, index)
        except json.JSONDecodeError as exc:
            raise SourceParseError(f"invalid JSON at offset {exc.pos}") from None
        kind = "string" if isinstance(value, str) else "scalar"
        return Node(kind, index, end, value), end

    def object(self, index: int) -> tuple[Node, int]:
        start = index
        index = self.skip(index + 1)
        members: list[Member] = []
        values: dict[str, Any] = {}
        if index < self.length and self.source[index] == "}":
            return Node("object", start, index + 1, values, members=members), index + 1
        while True:
            member_start = self.skip(index)
            if member_start >= self.length or self.source[member_start] != '"':
                raise SourceParseError(f"object key expected at offset {member_start}")
            key_node, index = self.value(member_start)
            if key_node.kind != "string":
                raise SourceParseError("object key must be a string")
            key = str(key_node.value)
            if key in values:
                raise DuplicateKeyError(f"duplicate object key: {key}")
            index = self.skip(index)
            if index >= self.length or self.source[index] != ":":
                raise SourceParseError(f"colon expected after object key at offset {index}")
            value_node, index = self.value(index + 1)
            values[key] = value_node.value
            member = Member(key, key_node, value_node, member_start, value_node.end)
            index = self.skip(index)
            if index < self.length and self.source[index] == ",":
                member.comma_start = index
                index += 1
                member.comma_end = index
                members.append(member)
                index = self.skip(index)
                if self.jsonc and index < self.length and self.source[index] == "}":
                    return Node("object", start, index + 1, values, members=members), index + 1
                continue
            members.append(member)
            if index < self.length and self.source[index] == "}":
                return Node("object", start, index + 1, values, members=members), index + 1
            raise SourceParseError(f"comma or closing brace expected at offset {index}")

    def array(self, index: int) -> tuple[Node, int]:
        start = index
        index = self.skip(index + 1)
        items: list[Node] = []
        if index < self.length and self.source[index] == "]":
            return Node("array", start, index + 1, [], items=items), index + 1
        while True:
            item, index = self.value(index)
            items.append(item)
            index = self.skip(index)
            if index < self.length and self.source[index] == ",":
                index = self.skip(index + 1)
                if self.jsonc and index < self.length and self.source[index] == "]":
                    return Node("array", start, index + 1, [item.value for item in items], items=items), index + 1
                continue
            if index < self.length and self.source[index] == "]":
                return Node("array", start, index + 1, [item.value for item in items], items=items), index + 1
            raise SourceParseError(f"comma or closing bracket expected at offset {index}")


def parse(source: str, *, jsonc: bool = False) -> Node:
    return Parser(source, jsonc=jsonc).parse()


def loads(source: str, *, jsonc: bool = False) -> Any:
    return parse(source, jsonc=jsonc).value


def _child(node: Node, key: str) -> Node | None:
    if node.kind != "object":
        return None
    for member in node.members:
        if member.key == key:
            return member.value_node
    return None


def find_node(root: Node, path: list[str]) -> Node | None:
    node = root
    for key in path:
        node = _child(node, key)
        if node is None:
            return None
    return node


def find_member(node: Node, key: str) -> Member | None:
    if node.kind != "object":
        return None
    return next((member for member in node.members if member.key == key), None)


def _line_indent(source: str, position: int) -> str:
    line_start = source.rfind("\n", 0, position) + 1
    prefix = source[line_start:position]
    return prefix if prefix.strip() == "" else ""


def _newline(source: str) -> str:
    return "\r\n" if "\r\n" in source else "\n"


def _pretty(value: Any, indent: str) -> str:
    raw = json.dumps(value, ensure_ascii=False, indent=2, separators=(",", ": "))
    return raw.replace("\n", "\n" + indent)


def object_add(source: str, node: Node, key: str, value: Any) -> str:
    if node.kind != "object":
        raise SourceParseError("target is not an object")
    if find_member(node, key):
        raise SourceParseError(f"object key already exists: {key}")
    newline = _newline(source)
    close_indent = _line_indent(source, node.end - 1)
    entry_indent = _line_indent(source, node.members[0].start) if node.members else close_indent + "  "
    rendered = f"{json.dumps(key, ensure_ascii=False)}: {_pretty(value, entry_indent)}"
    if not node.members:
        between = source[node.start + 1 : node.end - 1]
        if "\n" not in between and "\r" not in between:
            return source[: node.end - 1] + rendered + source[node.end - 1 :]
        return source[: node.end - 1] + newline + entry_indent + rendered + newline + close_indent + source[node.end - 1 :]
    return source[: node.end - 1] + "," + newline + entry_indent + rendered + newline + close_indent + source[node.end - 1 :]


def object_remove(source: str, node: Node, key: str) -> str:
    member = find_member(node, key)
    if member is None:
        raise SourceParseError(f"object key not found: {key}")
    count = len(node.members)
    if count == 1:
        return source[: member.start] + source[member.end :]
    if member is not node.members[-1]:
        end = member.comma_end or member.end
        return source[: member.start] + source[end:]
    previous = node.members[-2]
    comma = source.rfind(",", previous.end, member.start)
    if comma < 0:
        raise SourceParseError("cannot locate separator for object removal")
    return source[:comma] + source[member.end :]


def object_replace_value(source: str, node: Node, key: str, value: Any) -> str:
    member = find_member(node, key)
    if member is None:
        return object_add(source, node, key, value)
    indent = _line_indent(source, member.start) + "  "
    return source[: member.value_node.start] + _pretty(value, indent) + source[member.value_node.end :]


def replace_node(source: str, node: Node, value: Any) -> str:
    indent = _line_indent(source, node.start)
    return source[: node.start] + _pretty(value, indent) + source[node.end :]


def merge_dict(existing: Any, desired: Any) -> dict[str, Any]:
    if not isinstance(existing, dict) or not isinstance(desired, dict):
        raise SourceParseError("server definition must be an object")
    merged = dict(existing)
    for key, value in desired.items():
        if key.startswith("_"):
            continue
        merged[key] = value
    return merged


def apply_operation(source: str, *, jsonc: bool, mcp_path: list[str], action: str, name: str, payload: dict[str, Any]) -> str:
    root = parse(source, jsonc=jsonc)
    container = find_node(root, mcp_path)
    if container is None or container.kind != "object":
        raise SourceParseError("recognized MCP object is missing or not an object")
    existing_member = find_member(container, name)
    if action in {"upsert-server", "duplicate-server"}:
        desired_name = str(payload.get("name", name))
        desired = dict(payload)
        desired.pop("name", None)
        if existing_member and desired_name == name:
            merged = merge_dict(existing_member.value_node.value, desired)
            return replace_node(source, existing_member.value_node, merged)
        if find_member(container, desired_name):
            raise SourceParseError("server name already exists")
        return object_add(source, container, desired_name, desired)
    if existing_member is None:
        raise SourceParseError("server name not found")
    server = existing_member.value_node
    if action == "remove-server":
        return object_remove(source, container, name)
    if action in {"set-enabled", "toggle-server"}:
        desired_enabled = bool(payload.get("enabled"))
        if server.kind != "object":
            raise SourceParseError("server definition is not an object")
        if find_member(server, "disabled"):
            return object_replace_value(source, server, "disabled", not desired_enabled)
        if find_member(server, "enabled"):
            return object_replace_value(source, server, "enabled", desired_enabled)
        return object_add(source, server, "disabled", not desired_enabled)
    raise SourceParseError(f"unsupported JSON operation: {action}")
