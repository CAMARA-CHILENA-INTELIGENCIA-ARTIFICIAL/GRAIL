"""Prompt registry + builtin prompt tests."""
from pathlib import Path

import pytest

from grail.prompts import BUILTIN_PROMPT_NAMES, PromptRegistry


def test_every_builtin_resolves():
    registry = PromptRegistry()
    for name in BUILTIN_PROMPT_NAMES:
        module = registry.get(name)
        assert module.NAME == name
        assert isinstance(module.REQUIRED_PARAMS, list)
        assert callable(module.build_messages)


def test_entity_relation_emits_two_messages():
    registry = PromptRegistry()
    messages = registry.build(
        "entity_relation",
        entity_types=["person", "organization"],
        input_text="Alice met Bob at Acme Corp.",
    )
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "Alice met Bob at Acme Corp." in messages[1]["content"]


def test_local_search_emits_system_user():
    registry = PromptRegistry()
    messages = registry.build(
        "local_search",
        context_data="Entities\nid,entity\n1,Alice",
        user_query="who is alice?",
        assistant_name="TestBot",
    )
    assert messages[0]["role"] == "system"
    assert messages[-1]["role"] == "user"
    assert "TestBot" in messages[0]["content"]


def test_missing_required_param_raises():
    registry = PromptRegistry()
    with pytest.raises(KeyError):
        registry.build("entity_relation", entity_types=["person"])  # missing input_text


def test_custom_directory_overrides_per_file(tmp_path: Path):
    override = tmp_path / "custom"
    override.mkdir()
    (override / "summarize_description.py").write_text(
        "NAME='summarize_description'\n"
        "REQUIRED_PARAMS=['entity_name','description_list']\n"
        "def build_messages(**params):\n"
        "    return [{'role':'system','content':'OVERRIDE'}, {'role':'user','content':params['entity_name']}]\n"
    )
    registry = PromptRegistry(custom_paths=[override])
    messages = registry.build("summarize_description", entity_name="X", description_list=["d"])
    assert messages[0]["content"] == "OVERRIDE"
    # And built-ins still resolve when not overridden.
    assert registry.get("community_report").NAME == "community_report"


def test_strict_mode_requires_full_pack(tmp_path: Path):
    override = tmp_path / "partial"
    override.mkdir()
    (override / "entity_relation.py").write_text(
        "NAME='entity_relation'\nREQUIRED_PARAMS=['entity_types','input_text']\n"
        "def build_messages(**p): return [{'role':'user','content':p['input_text']}]\n"
    )
    with pytest.raises(ValueError):
        PromptRegistry(custom_paths=[override], strict=True)
