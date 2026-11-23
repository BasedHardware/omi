package main

import (
	"crypto/sha256"
	"encoding/hex"
	"reflect"
	"strings"
)

var batchPrivacyStateFields = []string{"generation", "account_epoch", "purging", "blocked", "memo_blocked"}

const batchPrivacyMemoRuleReason = "both batch privacy memo tokens are fresh UUIDv4 hex values; schema and seeded privacy state match with one write and no reads"

func batchPrivacyDocumentPath(owner string) string {
	if owner == "" {
		return ""
	}
	key := sha256.Sum256([]byte(owner))
	return "batch_pipeline_privacy/" + hex.EncodeToString(key[:])
}

func samePrivacyField(left, right map[string]any, field string) bool {
	leftValue, leftExists := left[field]
	rightValue, rightExists := right[field]
	return leftExists == rightExists && (!leftExists || reflect.DeepEqual(leftValue, rightValue))
}

func privacyStateEqual(left, right map[string]any) bool {
	for _, field := range batchPrivacyStateFields {
		if !samePrivacyField(left, right, field) {
			return false
		}
	}
	return true
}

func privacyStateMatchesSeed(run *observation) bool {
	return run != nil && run.BatchPrivacy != nil && run.BatchPrivacy.Seed.Fields != nil &&
		run.BatchPrivacy.Final.Fields != nil && privacyStateEqual(run.BatchPrivacy.Seed.Fields, run.BatchPrivacy.Final.Fields)
}

func batchPrivacySnapshotValid(snapshot batchPrivacySnapshot) bool {
	return snapshot.Fields != nil && (snapshot.Exists || len(snapshot.Fields) == 0)
}

func batchPrivacyRelevant(run *observation) bool {
	if run == nil {
		return false
	}
	if run.BatchPrivacy != nil && (run.BatchPrivacy.Seed.Exists || run.BatchPrivacy.Final.Exists) {
		return true
	}
	if run.Cost.Firestore.BatchPrivacyDocumentReads != 0 ||
		run.Cost.Firestore.BatchPrivacyDocumentWrites != 0 || run.Cost.Firestore.BatchPrivacyDocumentDeletes != 0 {
		return true
	}
	for path := range run.Derived {
		if strings.HasPrefix(path, "batch_pipeline_privacy/") {
			return true
		}
	}
	return false
}

func batchPrivacySnapshotMatchesDerived(run *observation) bool {
	path := batchPrivacyDocumentPath(run.OwnerID)
	doc, ok := run.Derived[path].(map[string]any)
	if !ok || run.BatchPrivacy == nil || !run.BatchPrivacy.Final.Exists {
		return false
	}
	for _, field := range []string{"memo_token", "memo_schema", "generation", "account_epoch", "purging", "blocked", "memo_blocked"} {
		if !samePrivacyField(run.BatchPrivacy.Final.Fields, doc, field) {
			return false
		}
	}
	return true
}

func batchPrivacyEvidenceValid(python, goRun *observation) bool {
	if python == nil || goRun == nil || python.OwnerID == "" || python.OwnerID != goRun.OwnerID ||
		!batchPrivacyRelevant(python) || !batchPrivacyRelevant(goRun) {
		return false
	}
	for _, run := range []*observation{python, goRun} {
		if run.BatchPrivacy == nil || !batchPrivacySnapshotValid(run.BatchPrivacy.Seed) ||
			!batchPrivacySnapshotValid(run.BatchPrivacy.Final) || !run.BatchPrivacy.Final.Exists ||
			run.SeededTokenHashes == nil || !run.Cost.Measured || !privacyStateMatchesSeed(run) ||
			!batchPrivacySnapshotMatchesDerived(run) {
			return false
		}
		if run.Cost.Firestore.BatchPrivacyDocumentReads != 0 ||
			run.Cost.Firestore.BatchPrivacyDocumentWrites != 1 ||
			run.Cost.Firestore.BatchPrivacyDocumentDeletes != 0 {
			return false
		}
		token, ok := run.BatchPrivacy.Final.Fields["memo_token"].(string)
		if !ok || !uuid4Hex.MatchString(token) || seededHomeToken(run, token) {
			return false
		}
		if seedToken, exists := run.BatchPrivacy.Seed.Fields["memo_token"]; exists && seedToken == token {
			return false
		}
		if _, exists := run.BatchPrivacy.Final.Fields["memo_schema"]; !exists {
			return false
		}
	}
	py, candidate := python.BatchPrivacy, goRun.BatchPrivacy
	return py.Seed.Exists == candidate.Seed.Exists && py.Final.Exists == candidate.Final.Exists &&
		privacyStateEqual(py.Seed.Fields, candidate.Seed.Fields) &&
		privacyStateEqual(py.Final.Fields, candidate.Final.Fields) &&
		samePrivacyField(py.Final.Fields, candidate.Final.Fields, "memo_schema")
}

func approvedBatchPrivacyDifference(path string, python, goRun *observation) string {
	parts := pointerParts(path)
	if len(parts) != 3 || parts[0] != "derived_documents" ||
		(parts[2] != "memo_token" && parts[2] != "memo_schema") {
		return ""
	}
	expected := batchPrivacyDocumentPath(python.OwnerID)
	if expected == "" || parts[1] != expected || !batchPrivacyEvidenceValid(python, goRun) {
		return ""
	}
	return batchPrivacyMemoRuleReason
}

func validateBatchPrivacyEvidence(diffs *[]difference, side string, run *observation) {
	if !batchPrivacyRelevant(run) {
		return
	}
	path := batchPrivacyDocumentPath(run.OwnerID)
	base := "/" + side + "/batch_pipeline_privacy"
	if run.BatchPrivacy == nil || !batchPrivacySnapshotValid(run.BatchPrivacy.Seed) ||
		!batchPrivacySnapshotValid(run.BatchPrivacy.Final) {
		addDifference(diffs, base+"/evidence", "missing_evidence")
		return
	}
	if !run.BatchPrivacy.Final.Exists {
		addDifference(diffs, base+"/final", "missing_document")
	}
	if run.SeededTokenHashes == nil {
		addDifference(diffs, base+"/seeded_tokens", "missing_evidence")
	}
	for _, field := range batchPrivacyStateFields {
		if !samePrivacyField(run.BatchPrivacy.Seed.Fields, run.BatchPrivacy.Final.Fields, field) {
			addDifference(diffs, "/"+side+"/derived_documents/"+escapePointer(path)+"/"+field, "invalid_binding")
		}
	}
	token, ok := run.BatchPrivacy.Final.Fields["memo_token"].(string)
	seedToken, seedTokenExists := run.BatchPrivacy.Seed.Fields["memo_token"].(string)
	if !ok || !uuid4Hex.MatchString(token) || seededHomeToken(run, token) || (seedTokenExists && seedToken == token) {
		addDifference(diffs, "/"+side+"/derived_documents/"+escapePointer(path)+"/memo_token", "invalid_binding")
	}
	if _, exists := run.BatchPrivacy.Final.Fields["memo_schema"]; !exists {
		addDifference(diffs, "/"+side+"/derived_documents/"+escapePointer(path)+"/memo_schema", "missing_evidence")
	}
	if !batchPrivacySnapshotMatchesDerived(run) {
		addDifference(diffs, base+"/final_snapshot", "invalid_binding")
	}
	if !run.Cost.Measured || run.Cost.Firestore.BatchPrivacyDocumentReads != 0 ||
		run.Cost.Firestore.BatchPrivacyDocumentWrites != 1 || run.Cost.Firestore.BatchPrivacyDocumentDeletes != 0 {
		addDifference(diffs, "/"+side+"/firestore_operations/batch_pipeline_privacy_document", "invalid_operations")
	}
}

func validateBatchPrivacyPair(diffs *[]difference, python, goRun *observation) {
	if !batchPrivacyRelevant(python) && !batchPrivacyRelevant(goRun) {
		return
	}
	if python == nil || goRun == nil || python.BatchPrivacy == nil || goRun.BatchPrivacy == nil ||
		python.BatchPrivacy.Seed.Fields == nil || goRun.BatchPrivacy.Seed.Fields == nil ||
		python.BatchPrivacy.Final.Fields == nil || goRun.BatchPrivacy.Final.Fields == nil {
		return
	}
	path := batchPrivacyDocumentPath(python.OwnerID)
	for _, field := range batchPrivacyStateFields {
		if !samePrivacyField(python.BatchPrivacy.Seed.Fields, goRun.BatchPrivacy.Seed.Fields, field) ||
			!samePrivacyField(python.BatchPrivacy.Final.Fields, goRun.BatchPrivacy.Final.Fields, field) {
			addDifference(diffs, "/derived_documents/"+escapePointer(path)+"/"+field, "invalid_binding")
		}
	}
	if python.BatchPrivacy.Seed.Exists != goRun.BatchPrivacy.Seed.Exists ||
		python.BatchPrivacy.Final.Exists != goRun.BatchPrivacy.Final.Exists {
		addDifference(diffs, "/derived_documents/"+escapePointer(path)+"/existence", "invalid_binding")
	}
	if !samePrivacyField(python.BatchPrivacy.Final.Fields, goRun.BatchPrivacy.Final.Fields, "memo_schema") {
		addDifference(diffs, "/derived_documents/"+escapePointer(path)+"/memo_schema", "invalid_binding")
	}
}
