package main

import (
	"encoding/hex"
	"maps"
	"strings"
	"time"
)

const postErasureMemoReason = "both post-erasure batch privacy memo tokens are fresh UUIDv4 hex values bound to matching blocked privacy state"

type erasureOperationKey struct {
	accountEpoch    int64
	purgeGeneration int64
	startsPurge     bool
}

type erasureOperation struct {
	path     string
	semantic map[string]any
}

// Compare receipts under the same owner digest by account epoch and operation
// kind. The writer encodes begin-purge as a non-null purge_generation. Its
// other operation receipts store null. Each receipt expires after 90 days.
func erasureOperations(run, before *observation, prefix string) map[erasureOperationKey][]erasureOperation {
	const retention = 90 * 24 * time.Hour
	operations := make(map[erasureOperationKey][]erasureOperation)
	for path, raw := range run.Derived {
		id, found := strings.CutPrefix(path, prefix)
		receipt, ok := raw.(map[string]any)
		if !found || !ok || len(id) != 64 {
			continue
		}
		if _, err := hex.DecodeString(id); err != nil {
			continue
		}
		if _, existed := before.Derived[path]; existed {
			continue
		}
		epoch, epochOK := integerValue(receipt["account_epoch"])
		purge, hasKind := receipt["purge_generation"]
		generation, generationOK := integerValue(purge)
		if !epochOK || epoch <= 0 || !hasKind || (purge != nil && (!generationOK || generation <= 0)) {
			continue
		}
		stamp, ok := timestampText(receipt["expires_at"])
		expiry, err := time.Parse(time.RFC3339Nano, stamp)
		writtenAt := expiry.Add(-retention)
		if !ok || err != nil || writtenAt.Before(before.Finished) || writtenAt.After(run.Finished) {
			continue
		}
		key := erasureOperationKey{epoch, generation, purge != nil}
		semantic := maps.Clone(receipt)
		delete(semantic, "expires_at")
		operations[key] = append(operations[key], erasureOperation{path, semantic})
	}
	return operations
}

func reviewPostErasurePrivacy(diffs []difference, python, goRun, pythonBefore, goBefore *observation) {
	doc := batchPrivacyDocumentPath(python.OwnerID)
	prefix := doc + "/account_operations/"
	pyOps := erasureOperations(python, pythonBefore, prefix)
	goOps := erasureOperations(goRun, goBefore, prefix)
	pairs := make(map[string]string)
	for key, pyRows := range pyOps {
		goRows := goOps[key]
		if len(pyRows) != 1 || len(goRows) != 1 {
			continue
		}
		py, candidate := pyRows[0], goRows[0]
		_, pyHasGoID := python.Derived[candidate.path]
		_, goHasPyID := goRun.Derived[py.path]
		if !pyHasGoID && !goHasPyID && equalReplayValue(py.semantic, candidate.semantic) {
			pairs["/derived_documents/"+escapePointer(py.path)] = "missing_in_go"
			pairs["/derived_documents/"+escapePointer(candidate.path)] = "missing_in_python"
		}
	}
	memoPath := "/derived_documents/" + escapePointer(doc) + "/memo_token"
	for i := range diffs {
		diff := &diffs[i]
		if pairs[diff.Path] == diff.Kind {
			diff.Reason = "generated_identity"
		}
		if diff.Path == memoPath && diff.Kind == "different_value" &&
			postErasurePrivacyMemosMatch(python, goRun, pythonBefore, goBefore) {
			diff.Reason = postErasureMemoReason
		}
	}
}

func postErasurePrivacyMemosMatch(python, goRun, pythonBefore, goBefore *observation) bool {
	if !batchPrivacyEvidenceValid(pythonBefore, goBefore) {
		return false
	}
	for _, phase := range [][2]*observation{{python, pythonBefore}, {goRun, goBefore}} {
		run, before := phase[0], phase[1]
		fields := run.BatchPrivacy.Final.Fields
		generation, genOK := integerValue(fields["generation"])
		epoch, epochOK := integerValue(fields["account_epoch"])
		if !genOK || generation <= 0 || !epochOK || epoch <= 0 ||
			!batchPrivacySnapshotMatchesDerived(run) || !freshBatchPrivacyMemo(run) ||
			!samePrivacyField(fields, before.BatchPrivacy.Final.Fields, "memo_schema") ||
			fields["memo_token"] == before.BatchPrivacy.Final.Fields["memo_token"] ||
			fields["blocked"] != true || fields["purging"] != false ||
			run.Cost.Firestore.BatchPrivacyDocumentWrites <= before.Cost.Firestore.BatchPrivacyDocumentWrites {
			return false
		}
	}
	return privacyStateEqual(python.BatchPrivacy.Final.Fields, goRun.BatchPrivacy.Final.Fields)
}
