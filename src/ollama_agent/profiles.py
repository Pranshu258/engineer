"""Packaged agent profiles and reusable skill instructions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from typing import Any


class ResourceError(RuntimeError):
    """A missing or malformed packaged-resource failure."""


@dataclass(frozen=True, slots=True)
class AgentProfile:
    name: str
    description: str
    system_prompt: str
    tool_names: tuple[str, ...]
    delegated_agents: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Skill:
    name: str
    description: str
    instructions: str


def _read_resource(*parts: str) -> str:
    resource = resources.files("ollama_agent").joinpath("resources", *parts)
    try:
        return resource.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        path = "/".join(("resources", *parts))
        raise ResourceError(f"Missing packaged resource: {path}") from exc


def _manifest() -> dict[str, Any]:
    raw = _read_resource("profiles.json")
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ResourceError(
            f"Malformed packaged resource resources/profiles.json: {exc}"
        ) from exc
    if not isinstance(manifest, dict):
        raise ResourceError(
            "Malformed packaged resource resources/profiles.json: expected an object"
        )
    return manifest


def _named_entry(kind: str, name: str) -> dict[str, Any]:
    entries = _manifest().get(kind)
    if not isinstance(entries, dict):
        raise ResourceError(
            f"Malformed packaged resource resources/profiles.json: "
            f"{kind!r} must be an object"
        )
    entry = entries.get(name)
    if entry is None:
        known = ", ".join(sorted(entries))
        singular = "agent profile" if kind == "agents" else "skill"
        raise ResourceError(f"Unknown {singular} {name!r}. Known names: {known}")
    if not isinstance(entry, dict):
        raise ResourceError(
            f"Malformed packaged resource resources/profiles.json: "
            f"{kind}.{name} must be an object"
        )
    return entry


def _required_string(entry: dict[str, Any], field: str, location: str) -> str:
    value = entry.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ResourceError(f"Malformed {location}: {field!r} must be a non-empty string")
    return value


def _string_tuple(
    entry: dict[str, Any], field: str, location: str
) -> tuple[str, ...]:
    value = entry.get(field, [])
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise ResourceError(f"Malformed {location}: {field!r} must be a string array")
    return tuple(value)


def load_profile(name: str) -> AgentProfile:
    entry = _named_entry("agents", name)
    location = f"agent profile {name!r}"
    prompt_file = _required_string(entry, "prompt", location)
    prompt = _read_resource("agents", prompt_file)
    if not prompt.strip():
        raise ResourceError(f"Malformed {location}: prompt resource is empty")
    return AgentProfile(
        name=name,
        description=_required_string(entry, "description", location),
        system_prompt=prompt,
        tool_names=_string_tuple(entry, "tools", location),
        delegated_agents=_string_tuple(entry, "delegates", location),
    )


def load_skill(name: str) -> Skill:
    entry = _named_entry("skills", name)
    location = f"skill {name!r}"
    instruction_file = _required_string(entry, "instructions", location)
    instructions = _read_resource("skills", instruction_file)
    if not instructions.strip():
        raise ResourceError(f"Malformed {location}: instruction resource is empty")
    return Skill(
        name=name,
        description=_required_string(entry, "description", location),
        instructions=instructions,
    )


def profile_names() -> tuple[str, ...]:
    agents = _manifest().get("agents")
    if not isinstance(agents, dict):
        raise ResourceError(
            "Malformed packaged resource resources/profiles.json: "
            "'agents' must be an object"
        )
    return tuple(agents)


def skill_names() -> tuple[str, ...]:
    skills = _manifest().get("skills")
    if not isinstance(skills, dict):
        raise ResourceError(
            "Malformed packaged resource resources/profiles.json: "
            "'skills' must be an object"
        )
    return tuple(skills)
