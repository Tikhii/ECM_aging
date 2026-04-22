"""
test_error_codes_registry.py
============================
Structural and referential integrity tests for docs/error_codes_registry.json.

Checks:
    1. Registry validates against docs/error_codes.schema.json
    2. Every code key scope prefix matches its entry's `scope` field
    3. Every code key level letter matches its entry's `level` field
    4. Numeric suffixes are unique within each (scope, level) group
    5. Every cross_refs path (non-TODO, non-prose) points to an existing file
    6. Every status=active entry has a non-empty remediation list

The offline runbook and script raise-sites consume this registry; these tests
gate the registry itself before downstream consumers inherit any defect (R6).
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

import jsonschema
import pytest


ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "docs" / "error_codes_registry.json"
SCHEMA_PATH = ROOT / "docs" / "error_codes.schema.json"

# Known file-path prefixes. A cross_refs string whose first whitespace-delimited
# token starts with one of these is treated as a path claim and must exist.
PATH_PREFIXES = ("docs/", "libquiv_aging/", "scripts/", "tests/", "examples/")
ROOT_LEVEL_FILES = {
    "QUICKSTART.md",
    "README.md",
    "environment.yml",
    "pyproject.toml",
    "requirements.txt",
}

CODE_KEY_RE = re.compile(r"^(?P<scope>[A-Z0-9]+)-(?P<level>[EWI])(?P<num>[0-9]{3})$")


@pytest.fixture(scope="module")
def registry() -> dict:
    with open(REGISTRY_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def schema() -> dict:
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def test_registry_validates_against_schema(registry, schema):
    jsonschema.validate(instance=registry, schema=schema)


def test_code_key_prefix_matches_scope(registry):
    failures: list[str] = []
    for code_id, body in registry["codes"].items():
        m = CODE_KEY_RE.match(code_id)
        assert m, f"malformed code key {code_id!r}"
        if m.group("scope") != body["scope"]:
            failures.append(
                f"{code_id}: key prefix {m.group('scope')!r} != scope field {body['scope']!r}"
            )
    assert not failures, "scope/key mismatch:\n" + "\n".join(failures)


def test_code_key_level_matches_level_field(registry):
    failures: list[str] = []
    for code_id, body in registry["codes"].items():
        m = CODE_KEY_RE.match(code_id)
        if m.group("level") != body["level"]:
            failures.append(
                f"{code_id}: key level letter {m.group('level')!r} != level field {body['level']!r}"
            )
    assert not failures, "level/key mismatch:\n" + "\n".join(failures)


def test_no_duplicate_numbers_within_scope_level(registry):
    buckets: dict[tuple[str, str], list[str]] = defaultdict(list)
    for code_id in registry["codes"].keys():
        m = CODE_KEY_RE.match(code_id)
        buckets[(m.group("scope"), m.group("level"))].append(m.group("num"))
    dupes = {k: v for k, v in buckets.items() if len(set(v)) != len(v)}
    assert not dupes, f"duplicate numeric suffixes detected: {dupes}"


def _candidate_path(ref: str) -> Path | None:
    """Extract a filesystem path claim from a cross_refs entry, or return None.

    Entries starting with 'TODO' are placeholders pending a follow-up
    documentation pass and are skipped from existence checks.
    """
    stripped = ref.strip()
    if stripped.upper().startswith("TODO"):
        return None
    token = stripped.split()[0].split("::")[0].rstrip(",.;")
    if token.startswith(PATH_PREFIXES):
        return ROOT / token
    if token in ROOT_LEVEL_FILES:
        return ROOT / token
    return None


def test_cross_refs_path_level_existence(registry):
    missing: list[str] = []
    for code_id, body in registry["codes"].items():
        for ref in body["cross_refs"]:
            p = _candidate_path(ref)
            if p is None:
                continue
            if not p.exists():
                missing.append(f"{code_id}: {ref!r} -> {p}")
    assert not missing, "cross_refs pointing to missing files:\n" + "\n".join(missing)


def test_active_entries_have_remediation(registry):
    bad: list[str] = []
    for code_id, body in registry["codes"].items():
        if body["status"] == "active" and len(body.get("remediation", [])) == 0:
            bad.append(code_id)
    assert not bad, "active entries without remediation: " + ", ".join(bad)


def test_deprecated_entries_have_deprecation_note(registry):
    """Schema allows deprecated_note to be absent; business rule requires it."""
    bad: list[str] = []
    for code_id, body in registry["codes"].items():
        if body["status"] == "deprecated" and not body.get("deprecated_note", "").strip():
            bad.append(code_id)
    assert not bad, "deprecated entries without deprecated_note: " + ", ".join(bad)
