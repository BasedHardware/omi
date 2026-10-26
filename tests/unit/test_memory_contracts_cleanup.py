import ast
import re
import pytest

def test_memory_contracts_dead_exports_removed():
    with open('scratch/issue_19569/memory_contracts.py', 'r', encoding='utf-8') as f:
        code = f.read()

    tree = ast.parse(code)
    
    # Check classes defined
    class_names = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    assert 'SourceBackedMemoryCandidate' not in class_names, "SourceBackedMemoryCandidate should be deleted"
    assert 'L2MemoryRoute' not in class_names, "L2MemoryRoute should be deleted"

    # Check top-level assignments
    assign_targets = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assign_targets.append(target.id)
    assert 'DURABLE_MEMORY_PATCH_FACT_SOURCE' not in assign_targets, "DURABLE_MEMORY_PATCH_FACT_SOURCE should be deleted"

    # Check __all__
    all_node = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == '__all__':
                    all_node = node
                    break
    assert all_node is not None, "__all__ must exist"
    
    exported_names = [elt.value for elt in all_node.value.elts if isinstance(elt, ast.Constant)]
    assert 'SourceBackedMemoryCandidate' not in exported_names
    assert 'L2MemoryRoute' not in exported_names
    assert 'DURABLE_MEMORY_PATCH_FACT_SOURCE' not in exported_names
    assert 'DurableMemoryPatch' in exported_names
    assert 'L1MemoryArchiveItem' in exported_names
    assert 'WorkingMemoryObservation' in exported_names


def test_working_observations_provenance_string():
    with open('scratch/issue_19569/working_observations.py', 'r', encoding='utf-8') as f:
        code = f.read()

    assert 'utils.llm.working_memory.extract_l1_memory_archive_items_from_text' not in code, \
        "Stale provenance string utils.llm.working_memory should not exist"
    assert 'utils.llm.working_observations.extract_l1_memory_archive_items_from_text' in code, \
        "Updated provenance string utils.llm.working_observations must exist"


def test_domain_model_stale_citations_cleared():
    with open('scratch/issue_19569/domain_model.md', 'r', encoding='utf-8') as f:
        doc = f.read()

    assert 'working_memory.py' not in doc, "working_memory.py citations must be replaced"
    assert 'l2_memory_routes.py' not in doc, "l2_memory_routes.py citations must be replaced"
    assert 'durable_memory_patches.py' not in doc, "durable_memory_patches.py citations must be replaced"
    assert 'working_observations.py' in doc, "canonical working_observations.py must be cited"
    assert 'canonical_consolidation.py' in doc, "canonical_consolidation.py must be cited"


if __name__ == '__main__':
    test_memory_contracts_dead_exports_removed()
    test_working_observations_provenance_string()
    test_domain_model_stale_citations_cleared()
    print("ALL HERMETIC TESTS PASSED (100% GREEN)")
