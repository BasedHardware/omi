package docstore

import "strings"

// MarkerCollection holds one document per account with a deletion in progress, keyed by
// owner id. It is the same marker the Python backend writes and reads
// (backend/database/account_deletion_marker.py), so both runtimes refuse the same accounts.
const MarkerCollection = "account_deletions"

// markerStatusField is the marker's state field.
const markerStatusField = "wipe_status"

// Blocks decides whether a deletion marker forbids writing the owner's data. It is the Go
// twin of account_deletion_blocks_access in backend/database/account_deletion_policy.py and
// must change together with it.
//
// No marker allows the write. A marker forbids it unless its status explicitly restores
// access. A marker whose status is missing, empty or not a string forbids it: a malformed
// marker is never read as "no deletion".
func Blocks(exists bool, status any) bool {
	if !exists {
		return false
	}
	text, ok := status.(string)
	if !ok {
		return true
	}
	switch strings.TrimSpace(text) {
	case "cancelled", "billing_failed":
		return false
	default:
		return true
	}
}
