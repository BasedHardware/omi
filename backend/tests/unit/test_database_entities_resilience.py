"""Hermetic unit tests for database.entities input validation and resilience."""

from unittest.mock import MagicMock, patch
import pytest

from database.entities import (
    USER_ENTITY_ID,
    person_entity_id,
    stable_entity_id,
    resolve_entity_id,
    apply_entity_mutations,
    merge_entities,
    split_entity,
    reassign_fact_subject,
)


class TestPersonEntityId:
    def test_valid_person_id(self):
        assert person_entity_id("p123") == "person:p123"
        assert person_entity_id("  p456  ") == "person:p456"

    def test_invalid_person_id(self):
        with pytest.raises(ValueError, match="person_id must be a non-empty string"):
            person_entity_id("")
        with pytest.raises(ValueError, match="person_id must be a non-empty string"):
            person_entity_id("   ")
        with pytest.raises(ValueError, match="person_id must be a non-empty string"):
            person_entity_id(None)  # type: ignore
        with pytest.raises(ValueError, match="person_id must be a non-empty string"):
            person_entity_id(123)  # type: ignore


class TestStableEntityId:
    def test_valid_stable_id(self):
        id1 = stable_entity_id("Artificial Intelligence")
        assert id1.startswith("entity:")
        assert len(id1) == len("entity:") + 24
        # Case insensitive and trimmed
        id2 = stable_entity_id("  artificial intelligence  ")
        assert id1 == id2

    def test_invalid_label(self):
        with pytest.raises(ValueError, match="label must be a non-empty string"):
            stable_entity_id("")
        with pytest.raises(ValueError, match="label must be a non-empty string"):
            stable_entity_id("   ")
        with pytest.raises(ValueError, match="label must be a non-empty string"):
            stable_entity_id(None)  # type: ignore


class TestResolveEntityId:
    @patch("database.entities.kg_db")
    def test_invalid_uid_returns_none(self, mock_kg):
        assert resolve_entity_id("", label="test") is None
        assert resolve_entity_id("   ", label="test") is None
        assert resolve_entity_id(None, label="test") is None  # type: ignore
        mock_kg.upsert_knowledge_node.assert_not_called()

    @patch("database.entities.kg_db")
    def test_person_id_resolution(self, mock_kg):
        eid = resolve_entity_id("user1", person_id="pers1", label="Alice")
        assert eid == "person:pers1"
        mock_kg.upsert_knowledge_node.assert_called_once_with(
            "user1",
            {
                "id": "person:pers1",
                "label": "Alice",
                "node_type": "person",
                "aliases": ["Alice"],
                "memory_ids": [],
            },
        )

    @patch("database.entities.kg_db")
    def test_existing_label_resolution(self, mock_kg):
        mock_kg.find_node_by_label_or_alias.return_value = {"id": "existing-node-1"}
        eid = resolve_entity_id("user1", label="Omi Device")
        assert eid == "existing-node-1"
        mock_kg.upsert_knowledge_node.assert_not_called()

    @patch("database.entities.kg_db")
    def test_new_label_resolution(self, mock_kg):
        mock_kg.find_node_by_label_or_alias.return_value = None
        eid = resolve_entity_id("user1", label="Omi Device")
        assert eid is not None and eid.startswith("entity:")
        mock_kg.upsert_knowledge_node.assert_called_once()

    @patch("database.entities.kg_db")
    def test_missing_label_and_person_returns_none(self, mock_kg):
        assert resolve_entity_id("user1") is None
        assert resolve_entity_id("user1", label="") is None
        assert resolve_entity_id("user1", label="   ") is None
        mock_kg.upsert_knowledge_node.assert_not_called()


class TestApplyEntityMutations:
    def test_non_dict_entities(self):
        assert apply_entity_mutations(None, []) == {}  # type: ignore
        assert apply_entity_mutations("not-a-dict", []) == {}  # type: ignore

    def test_non_list_mutations(self):
        state = {"e1": {"id": "e1"}}
        assert apply_entity_mutations(state, None) == state  # type: ignore

    def test_merge_entities_normal(self):
        initial = {
            "e1": {"id": "e1", "label": "Entity 1", "aliases": ["E1"]},
            "e2": {"id": "e2", "label": "Entity 2", "aliases": ["E2"]},
        }
        mutations = [
            {"type": "merge_entities", "entity_a": "e1", "entity_b": "e2"}
        ]
        result = apply_entity_mutations(initial, mutations)
        assert "e2" not in result
        assert "e1" in result
        assert result["e1"]["merged_entity_ids"] == ["e2"]
        assert set(result["e1"]["aliases"]) == {"E1", "E2", "Entity 2"}

    def test_self_merge_guarded(self):
        """Self-merge must NOT delete the entity."""
        initial = {
            "e1": {"id": "e1", "label": "Entity 1", "aliases": ["E1"]},
        }
        mutations = [
            {"type": "merge_entities", "entity_a": "e1", "entity_b": "e1"}
        ]
        result = apply_entity_mutations(initial, mutations)
        assert "e1" in result
        assert result["e1"]["aliases"] == ["E1"]

    def test_split_entity_normal(self):
        initial = {
            "parent": {"id": "parent", "label": "Parent"},
        }
        mutations = [
            {
                "type": "split_entity",
                "entity_id": "parent",
                "into": [
                    {"id": "child1", "label": "Child 1"},
                    {"id": "child2", "label": "Child 2"},
                ],
            }
        ]
        result = apply_entity_mutations(initial, mutations)
        assert "parent" not in result
        assert "child1" in result and "child2" in result

    def test_split_entity_empty_into_guarded(self):
        """Split with empty target must NOT delete the parent entity."""
        initial = {
            "parent": {"id": "parent", "label": "Parent"},
        }
        mutations = [
            {"type": "split_entity", "entity_id": "parent", "into": []}
        ]
        result = apply_entity_mutations(initial, mutations)
        assert "parent" in result


class TestMergeEntitiesFunction:
    @patch("database.entities.memory_ledger")
    @patch("database.entities.kg_db")
    def test_invalid_uids_or_ids(self, mock_kg, mock_ledger):
        with pytest.raises(ValueError, match="uid must be a non-empty string"):
            merge_entities("", "e1", "e2")
        with pytest.raises(ValueError, match="entity_a must be a non-empty string"):
            merge_entities("user1", "", "e2")
        with pytest.raises(ValueError, match="entity_b must be a non-empty string"):
            merge_entities("user1", "e1", "")

    @patch("database.entities.memory_ledger")
    @patch("database.entities.kg_db")
    def test_self_merge_raises(self, mock_kg, mock_ledger):
        with pytest.raises(ValueError, match="Cannot merge an entity into itself"):
            merge_entities("user1", "e1", "e1")

    @patch("database.entities.memory_ledger")
    @patch("database.entities.kg_db")
    def test_confidence_clamping(self, mock_kg, mock_ledger):
        mock_ledger.merge_entities.return_value = {"type": "merge_entities"}
        merge_entities("user1", "e1", "e2", confidence=2.5)
        mock_ledger.merge_entities.assert_called_with("e1", "e2", evidence=None, confidence=1.0)

        merge_entities("user1", "e1", "e2", confidence=-0.5)
        mock_ledger.merge_entities.assert_called_with("e1", "e2", evidence=None, confidence=0.0)

        merge_entities("user1", "e1", "e2", confidence=float("nan"))
        mock_ledger.merge_entities.assert_called_with("e1", "e2", evidence=None, confidence=0.5)


class TestSplitEntityFunction:
    @patch("database.entities.memory_ledger")
    @patch("database.entities.kg_db")
    def test_invalid_parameters(self, mock_kg, mock_ledger):
        with pytest.raises(ValueError, match="uid must be a non-empty string"):
            split_entity("", "e1", [{"id": "c1"}])
        with pytest.raises(ValueError, match="entity_id must be a non-empty string"):
            split_entity("user1", "", [{"id": "c1"}])
        with pytest.raises(ValueError, match="into must be a non-empty list of entity dicts"):
            split_entity("user1", "e1", [])
        with pytest.raises(ValueError, match="into must contain at least one valid entity dict with an 'id'"):
            split_entity("user1", "e1", [{"no_id": "val"}])


class TestReassignFactSubject:
    @patch("database.entities.memory_ledger")
    @patch("database.entities.kg_db")
    def test_invalid_parameters(self, mock_kg, mock_ledger):
        with pytest.raises(ValueError, match="uid must be a non-empty string"):
            reassign_fact_subject("", "fact1", "old", "new")
        with pytest.raises(ValueError, match="fact_id must be a non-empty string"):
            reassign_fact_subject("user1", "", "old", "new")
