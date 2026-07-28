from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DESKTOP_SOURCES = REPO_ROOT / "desktop" / "macos" / "Desktop" / "Sources"

IMPORT_MARKERS = ("import_kind", "sourceType: \"gmail\"", "sourceType: \"apple_notes\"", "sourceType: \"local_files\"")
IMPORTER_NAME_MARKERS = ("Import", "ReaderService", "OnboardingPagedIntroCoordinator")
ALLOWLIST = {
    DESKTOP_SOURCES / "APIClient.swift",
    DESKTOP_SOURCES / "Services" / "APIClient" / "APIClient+Memories.swift",
    DESKTOP_SOURCES / "Onboarding" / "OnboardingImportEvidenceService.swift",
}


def _importer_sources():
    candidates = []
    for path in DESKTOP_SOURCES.rglob("*.swift"):
        if path in ALLOWLIST:
            continue
        source = path.read_text(encoding="utf-8")
        if any(marker in path.name for marker in IMPORTER_NAME_MARKERS) or any(
            marker in source for marker in IMPORT_MARKERS
        ):
            candidates.append((path, source))
    return candidates


def test_desktop_importers_use_import_evidence_ingress_not_product_memory_batch():
    offenders = []
    for path, source in _importer_sources():
        for forbidden in [
            "OnboardingMemoryBatchImportService",
            "createMemoriesBatch(",
            "createMemory(",
            '"v3/memories"',
            '"v3/memories/batch"',
        ]:
            if forbidden in source:
                offenders.append(f"{path.relative_to(REPO_ROOT)} contains {forbidden}")

    assert not offenders, "Importers must write import evidence, not product memories:\n" + "\n".join(offenders)


def test_desktop_importers_pair_legacy_payloads_with_import_evidence_calls():
    offenders = []
    for path, source in _importer_sources():
        if "MemoryBatchItem(" in source and "legacyMemories:" not in source:
            offenders.append(f"{path.relative_to(REPO_ROOT)} builds legacy memories without fallback wiring")
    assert not offenders, "Legacy payloads must only exist as explicit fallback payloads:\n" + "\n".join(offenders)


def test_import_evidence_client_targets_import_endpoint():
    source = "\n".join(path.read_text(encoding="utf-8") for path in sorted(DESKTOP_SOURCES.rglob("APIClient*.swift")))
    assert 'post("v3/memory-imports/batch"' in source
    assert "func createMemoryImportBatch" in source


def test_import_evidence_service_does_not_default_source_account_hash_to_device_hash():
    source = (DESKTOP_SOURCES / "Onboarding" / "OnboardingImportEvidenceService.swift").read_text(encoding="utf-8")
    assert "sourceAccountHash: String? = nil" in source
    assert "deviceIdHash" not in source
