#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""No schema regular expression ends in ``$``.

Under Python ``re`` a trailing ``$`` also matches before a final newline, so a
pattern anchored with it accepts ``"value\n"`` while this repo's reader refuses
it: the reader splits on ``.`` and ``"0\n".isdigit()`` is False. That gap was
live in this schema until both patterns were re-anchored to ``(?![\\s\\S])``,
which is the portable end anchor (valid ECMA-262, unlike ``\\Z``, which a C++
``std::regex`` reads as a literal ``Z``).

This repository OWNS this schema and chiplet-spec publishes a byte copy, so the
policing belongs here; the mirror is gated on bytes. The walk is derived from a
glob, never a hand-list, so a new schema or a new pattern is covered the moment
it is committed.

Not covered: patterns in prose, and the regular expressions compiled in the
reader itself, which its own truth table pins.
"""
import json
import re
from pathlib import Path

import pytest

SCHEMAS = Path(__file__).resolve().parents[3] / "manifest" / "schema"


def _regexes(node, where):
    """Yield (location, regex) for every regex a schema document carries.

    Both ``pattern`` VALUES and ``patternProperties`` KEYS. The keys are the
    half a grep for the word "pattern" finds and then mis-handles, because the
    regex is the key rather than the value.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "pattern" and isinstance(value, str):
                yield "%s/pattern" % where, value
            if key == "patternProperties" and isinstance(value, dict):
                for prop_pattern in value:
                    yield "%s/patternProperties" % where, prop_pattern
            yield from _regexes(value, "%s/%s" % (where, key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _regexes(value, "%s[%d]" % (where, index))


def _all_regexes():
    found = []
    for schema_file in sorted(SCHEMAS.glob("*.schema.json")):
        doc = json.loads(schema_file.read_text(encoding="utf-8"))
        found.extend(_regexes(doc, schema_file.name))
    return found


def test_the_walk_reaches_patternproperties_keys():
    """Capability, proved against a fixture rather than against the corpus.

    This schema happens to carry no ``patternProperties`` today, so asserting
    that the real walk finds one would fail, and asserting nothing would let a
    walk that silently cannot reach those keys pass forever. Neither is a test.
    The fixture proves the walk can reach them the day one is added.
    """
    doc = {"properties": {"m": {"patternProperties": {"^x[0-9]+$": {"type": "string"}}}}}
    found = list(_regexes(doc, "fixture"))
    assert ("fixture/properties/m/patternProperties", "^x[0-9]+$") in found, found


def test_the_walk_actually_finds_this_schema_s_patterns():
    """A parametrized test over an EMPTY list passes without running. If the
    glob breaks or the file moves, every test below would go silently green,
    which is the failure this whole file exists to prevent."""
    regexes = _all_regexes()
    assert len(regexes) >= 2, regexes
    assert any(w.endswith("/pattern") for w, _ in regexes), regexes
    assert any("schema_version" in w for w, _ in regexes), regexes


@pytest.mark.parametrize("where,regex", _all_regexes())
def test_no_schema_regex_ends_in_dollar(where, regex):
    assert not regex.endswith("$"), (where, regex)
    assert not regex.endswith("$)"), (where, regex)


@pytest.mark.parametrize("where,regex",
                         [r for r in _all_regexes() if r[1].startswith("^")])
def test_an_end_anchored_regex_rejects_a_trailing_newline(where, regex):
    if "(?![" not in regex:
        pytest.skip("%s: not end-anchored, nothing to police" % where)
    compiled = re.compile(regex)
    sample = None
    for candidate in ("1.0", "1.0.0", "9/35", "A_B", "abc", "a", "0", "id-1"):
        if compiled.search(candidate):
            sample = candidate
            break
    assert sample is not None, (where, regex, "no sample matched; extend the list")
    assert compiled.search(sample + "\n") is None, (where, regex)
