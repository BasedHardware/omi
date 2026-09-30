import copy
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest

from database.entities import (
    USER_ENTITY_ID,
    _apply_merge,
    _apply_split,
    apply_entity_mutations,
    merge_entities,
    person_entity_id,
    reassign_fact_subject,
    resolve_entity_id,
    split_entity,
    stable_entity_id,
)
from models.memories import SubjectAttribution


class TestEntityConstantsAndIdentifiers:
    def test_user_entity_id(self):
        assert USER_ENTITY_ID == 'user'

    def test_person_entity_id(self):
        assert person_entity_id("p123") == "person:p123"

    def test_stable_entity_id(self):
        eid1 = stable_entity_id("Alice", "person")
        eid2 = stable_entity_id("alice", "person")
        assert eid1 == eid2
        assert eid1.startswith("entity:")


class TestResolveEntityId:
    def test_empty_uid_returns_none(self):
        assert resolve_entity_id("", label="test") is None
        assert resolve_entity_id("   ", label="test") is None
        assert resolve_entity_id(None, label="test") is None

    @patch("database.entities.kg_db")
    def test_person_id_upsert(self, mock_kg):
        eid = resolve_entity_id("user1", person_id="123", label="Alice")
        assert eid == "person:123"
        mock_kg.upsert_knowledge_node.assert_called_once()

    @patch("database.entities.kg_db")
    def test_label_not_provided(self, mock_kg):
        assert resolve_entity_id("user1") is None
        mock_kg.upsert_knowledge_node.assert_not_called()

    @patch("database.entities.kg_db")
    def test_label_existing_found(self, mock_kg):
        mock_kg.find_node_by_label_or_alias.return_value = {"id": "entity:existing"}
        assert resolve_entity_id("user1", label="Bob") == "entity:existing"
        mock_kg.upsert_knowledge_node.assert_not_called()

    @patch("database.entities.kg_db")
    def test_label_new_created(self, mock_kg):
        mock_kg.find_node_by_label_or_alias.return_value = None
        eid = resolve_entity_id("user1", label="NewConcept", entity_type="concept")
        assert eid.startswith("entity:")
        mock_kg.upsert_knowledge_node.assert_called_once()


class TestApplyEntityMutations:
    def test_normal_merge(self):
        state = {
            "e1": {"id": "e1", "label": "Alice", "aliases": ["Ali"]},
            "e2": {"id": "e2", "label": "Alicia", "aliases": ["A"]},
        }
        res = apply_entity_mutations(state, [{"type": "merge_entities", "entity_a": "e1", "entity_b": "e2"}])
        assert "e2" not in res
        assert "e1" in res
        assert "Alicia" in res["e1"]["aliases"]
        assert "e2" in res["e1"]["merged_entity_ids"]

    def test_self_merge_protection(self):
        # Prevent data-loss when entity_a == entity_b
        state = {
            "e1": {"id": "e1", "label": "Alice", "aliases": ["Ali"]},
        }
        res = apply_entity_mutations(state, [{"type": "merge_entities", "entity_a": "e1", "entity_b": "e1"}])
        assert "e1" in res
        assert res["e1"]["label"] == "Alice"

    def test_merge_missing_entities_noop(self):
        state = {"e1": {"id": "e1", "label": "Alice"}}
        res = apply_entity_mutations(state, [{"type": "merge_entities", "entity_a": "e1", "entity_b": "e999"}])
        assert "e1" in res
        assert len(res) == 1

    def test_normal_split(self):
        state = {"e1": {"id": "e1", "label": "Combined"}}
        into = [{"id": "s1", "label": "Part1"}, {"id": "s2", "label": "Part2"}]
        res = apply_entity_mutations(state, [{"type": "split_entity", "entity_id": "e1", "into": into}])
        assert "e1" not in res
        assert "s1" in res and "s2" in res


class TestMergeEntitiesFunction:
    def test_input_validation(self):
        with pytest.raises(ValueError, match="uid must be a non-empty string"):
            merge_entities("", "e1", "e2")
        with pytest.raises(ValueError, match="entity_a must be a non-empty string"):
            merge_entities("uid1", "", "e2")
        with pytest.raises(ValueError, match="entity_b must be a non-empty string"):
            merge_entities("uid1", "e1", "")
        with pytest.raises(ValueError, match="Cannot merge an entity into itself"):
            merge_entities("uid1", "e1", "e1")

    @patch("database.entities.memory_ledger")
    @patch("database.entities.kg_db")
    def test_merge_entities_projection_writer(self, mock_kg, mock_ledger):
        mock_db = MagicMock()
        mock_kg.db = mock_db
        mock_kg.users_collection = "users"
        mock_kg.knowledge_nodes_collection = "knowledge_nodes"

        mock_user_doc = MagicMock()
        mock_nodes_coll = MagicMock()
        mock_a_doc = MagicMock()
        mock_b_doc = MagicMock()

        mock_db.collection.return_value.document.return_value = mock_user_doc
        mock_user_doc.collection.return_value = mock_nodes_coll
        mock_nodes_coll.document.side_effect = lambda eid: mock_a_doc if eid == "e1" else mock_b_doc

        merge_entities("user_123", "e1", "e2", confidence=0.8)

        mock_ledger.append_commit.assert_called_once()
        _, kwargs = mock_ledger.append_commit.call_args
        pw = kwargs["projection_writer"]
        assert pw is not None

        # Execute projection writer
        mock_tx = MagicMock()
        snap_a = MagicMock(exists=True)
        snap_a.to_dict.return_value = {"id": "e1", "label": "E1"}
        snap_b = MagicMock(exists=True)
        snap_b.to_dict.return_value = {"id": "e2", "label": "E2"}

        mock_a_doc.get.return_value = snap_a
        mock_b_doc.get.return_value = snap_b

        pw(mock_tx)

        mock_tx.set.assert_called_once()
        mock_tx.delete.assert_called_once_with(mock_b_doc)


class TestSplitEntityFunction:
    def test_input_validation(self):
        with pytest.raises(ValueError, match="uid must be a non-empty string"):
            split_entity("", "e1", [{"id": "s1"}])
        with pytest.raises(ValueError, match="entity_id must be a non-empty string"):
            split_entity("uid1", "", [{"id": "s1"}])
        with pytest.raises(ValueError, match="into must contain at least one valid entity"):
            split_entity("uid1", "e1", [])
        with pytest.raises(ValueError, match="into must contain at least one valid entity"):
            split_entity("uid1", "e1", [{"invalid": "no_id"}])

    @patch("database.entities.memory_ledger")
    @patch("database.entities.kg_db")
    def test_split_entities_execution(self, mock_kg, mock_ledger):
        mock_db = MagicMock()
        mock_kg.db = mock_db
        mock_kg.users_collection = "users"
        mock_kg.knowledge_nodes_collection = "knowledge_nodes"

        into = [{"id": "s1", "label": "Split1"}]
        split_entity("uid1", "e1", into)
        mock_ledger.append_commit.assert_called_once()


class TestReassignFactSubject:
    def test_input_validation(self):
        with pytest.raises(ValueError, match="uid must be a non-empty string"):
            reassign_fact_subject("", "f1", None, "user")
        with pytest.raises(ValueError, match="fact_id must be a non-empty string"):
            reassign_fact_subject("uid1", "", None, "user")

    @patch("database.entities.memory_ledger")
    @patch("database.entities.kg_db")
    def test_reassign_fact_subject_user(self, mock_kg, mock_ledger):
        mock_db = MagicMock()
        mock_kg.db = mock_db
        mock_kg.users_collection = "users"

        reassign_fact_subject("uid1", "f1", None, USER_ENTITY_ID)
        mock_ledger.append_commit.assert_called_once()
