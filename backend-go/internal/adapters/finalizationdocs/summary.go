package finalizationdocs

import (
	"context"
	"crypto/sha256"
	"fmt"
	"math"
	"strings"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

const enrichment = "sync_reprocess_outbox"

// RepairSummary merges a due obligation without replacing its pending window
// or delivery binding. The existing enrichment scheduler owns wake delivery.
func (s Store) RepairSummary(ctx context.Context, a queue.Admitting, ref finalization.Ref, maxAge time.Duration) (rules.SummaryAction, error) {
	now := s.Clock.Now().UTC()
	var result rules.SummaryAction
	err := s.Docs.Fenced(ctx, a, ref.Owner, func(tx *docstore.Tx) error {
		var repairErr error
		result, repairErr = repairSummary(tx, ref, now, maxAge)
		return repairErr
	})
	return result, classify(err)
}

func repairSummary(tx *docstore.Tx, ref finalization.Ref, now time.Time, maxAge time.Duration) (rules.SummaryAction, error) {
	path, err := conversationRef(ref)
	if err != nil {
		return rules.SummarySkip, err
	}
	var row document
	found, err := tx.Get(path, &row)
	due := seconds(row, "summary_due_at")
	if err != nil || !found || due.IsZero() || due.After(now) || !rules.CanRepairSummary(summaryDebt(row)) {
		return rules.SummarySkip, err
	}
	user, allowed, err := privateCloudAuthority(tx, ref, row)
	if err != nil || !allowed {
		return rules.SummarySkip, err
	}
	if field[bool](field[map[string]any](user, "byok"), "active") {
		if field[string](row, "summary_blocked_reason") == "blocked_byok" {
			return rules.SummaryBlockBYOK, nil
		}
		return rules.SummaryBlockBYOK, tx.Update(path, document{"summary_blocked_reason": "blocked_byok"})
	}
	return scheduleSummary(tx, ref, row, now, due, maxAge)
}

func privateCloudAuthority(tx *docstore.Tx, ref finalization.Ref, row document) (document, bool, error) {
	userPath, err := docstore.Doc("users", ref.Owner)
	if err != nil {
		return nil, false, err
	}
	var user, privacy, marker document
	found, err := tx.Get(userPath, &user)
	if err != nil || !found || restricted(user) || user["migration_status"] != nil {
		return nil, false, err
	}
	if field[string](row, "record_lane_owner") == "batch_live_v1" &&
		(field[bool](row, "uses_custom_stt") || !field[bool](row, "private_cloud_sync_enabled") || user["private_cloud_sync_enabled"] == false) {
		return nil, false, nil
	}
	privacyPath, err := docstore.Doc("batch_pipeline_privacy", fmt.Sprintf("%x", sha256.Sum256([]byte(ref.Owner))))
	if err != nil {
		return nil, false, err
	}
	if _, readErr := tx.Get(privacyPath, &privacy); readErr != nil || field[bool](privacy, "blocked") || field[bool](privacy, "purging") {
		return nil, false, readErr
	}
	tombstone, err := docstore.Doc("users", ref.Owner, "deleted_conversations", ref.ID)
	if err != nil {
		return nil, false, err
	}
	deleted, err := tx.Get(tombstone, &marker)
	return user, !deleted, err
}

func restricted(row document) bool {
	level := field[string](row, "data_protection_level")
	return level != "" && level != "standard" && level != "enhanced"
}

func summaryDebt(row document) rules.SummaryDebt {
	structured := field[map[string]any](row, "structured")
	var bodies []string
	for _, raw := range field[[]any](structured, "sections") {
		if section, ok := raw.(map[string]any); ok {
			bodies = append(bodies, field[string](section, "body_markdown"))
		}
	}
	block := field[string](row, "summary_blocked_reason")
	provenance := field[string](row, "summary_title_provenance")
	job := field[string](row, "finalization_job_id")
	proof := field[map[string]any](row, "summary_projection_finalization")
	revision := field[int64](row, "finalization_revision")
	projectionOwns := job != "" && revision > 0 && field[string](proof, "job_id") == job &&
		field[int64](proof, "revision") == revision && field[string](row, "record_lane_owner") == "batch_live_v1" &&
		row["record_projection_revision"] != nil
	return rules.SummaryDebt{
		Complete:  field[string](row, "status") == string(rules.Completed),
		Deleted:   field[bool](row, "deleted") || field[bool](row, "is_deleted") || field[string](row, "sync_merged_into") != "",
		Discarded: field[bool](row, "discarded"), Protected: restricted(row),
		LocalOnly: field[bool](row, "deferred") || field[bool](row, "is_locked") || field[string](row, "processing_state") == "local_pending" ||
			field[bool](row, "terminal_no_derived_effects") || field[bool](row, "client_processing"),
		Manual: row["user_title"] != nil || row["user_overview"] != nil, Historical: field[string](row, "processing_tier") == "historical",
		IntentionalShort: intentionalShort(row, structured),
		HasSummary:       row["summary_completed_at"] != nil || field[bool](row, "summary_output_present") || rules.HasSummary(field[string](structured, "overview"), bodies),
		EmptyBlocked:     block == "empty_output_exhausted" || block == "empty_output_lifetime_exhausted",
		ServerMinimum:    provenance == "server_minimum",
		FinalizerOwns: field[string](row, "finalization_status") == blocked ||
			(job != "" && (!projectionOwns || strings.Contains(job, "/"))),
	}
}

func intentionalShort(row, structured document) bool {
	decision := field[map[string]any](row, "relevance_decision")
	return field[string](structured, "title_provenance") == "server_minimum" &&
		field[string](decision, "verdict") == "keep" && field[string](decision, "decided_by") == "rule" &&
		field[string](decision, "reason") == "content_below_floor"
}

func scheduleSummary(tx *docstore.Tx, ref finalization.Ref, row document, now, due time.Time, maxAge time.Duration) (rules.SummaryAction, error) {
	id := fmt.Sprintf("%x", sha256.Sum256([]byte(ref.Owner+"\x00"+ref.ID)))
	path, err := docstore.Doc(enrichment, id)
	if err != nil {
		return rules.SummarySkip, err
	}
	var old document
	found, err := tx.Get(path, &old)
	if err != nil {
		return rules.SummarySkip, err
	}
	if found && field[string](old, "uid") != "" && (field[string](old, "uid") != ref.Owner || field[string](old, "conversation_id") != ref.ID) {
		return rules.SummarySkip, finalization.ErrInvalid
	}
	// Python enrichment retains an unreadable transcript obligation as a terminal hold.
	parked := field[bool](old, "age_gate_parked") || field[string](old, "deferred_reason") == "age_gate_72h" ||
		(field[bool](old, "dormant") && field[string](old, "held_reason") == "conversation_unreadable")
	pending := earliest(seconds(row, "summary_first_pending_at"), seconds(old, "first_pending_at"), due)
	action := rules.SummaryRepair(now, due, pending, field[time.Time](row, "created_at"), seconds(old, "lease_until"), maxAge, true, false,
		field[bool](old, "summary_seen"), parked)
	if action != rules.SummaryWake && action != rules.SummaryPark {
		return action, nil
	}
	if old == nil {
		old = make(document)
	}
	if err := updateSummary(old, row, ref, id, action, now, pending, due); err != nil {
		return rules.SummarySkip, err
	}
	return action, tx.Set(path, old)
}

func updateSummary(outbox, row document, ref finalization.Ref, id string, action rules.SummaryAction, now, pending, due time.Time) error {
	revision := field[int64](row, "sync_content_revision")
	version, generation := field[int64](outbox, "version"), field[int64](outbox, "wake_generation")
	if version == math.MaxInt64 || generation == math.MaxInt64 || revision < 0 {
		return finalization.ErrInvalid
	}
	expected, revisionBound := outbox["summary_expected_revision"].(int64)
	if field[string](outbox, "task_token") == "" || !revisionBound || expected != revision || action == rules.SummaryPark {
		token, err := newUUID()
		if err != nil {
			return err
		}
		outbox["task_token"] = strings.ReplaceAll(token, "-", "")
		outbox["wake_check_after"] = int64(0)
	}
	outbox["document_id"], outbox["uid"], outbox["conversation_id"] = id, ref.Owner, ref.ID
	outbox["first_pending_at"], outbox["latest_pending_at"] = unix(pending), unix(now)
	outbox["summary_deadline_at"] = unix(earliest(seconds(outbox, "summary_deadline_at"), due))
	outbox["due_at"], outbox["task_due_at"] = unix(earliest(seconds(outbox, "due_at"), due)), unix(now)
	outbox["version"], outbox["wake_generation"], outbox["summary_expected_revision"] = version+1, generation+1, revision
	outbox["summary_repair"], outbox["dormant"], outbox["effects_only"] = true, false, false
	if field[string](outbox, "summary_blocked_reason") == "empty_output_exhausted" {
		outbox["summary_blocked_reason"], outbox["summary_empty_failures"] = nil, int64(0)
	}
	outbox["language"] = firstString(field[string](row, "language"), field[string](outbox, "language"), "en")
	outbox["summary_lane"] = firstString(field[string](row, "summary_lane"), "unknown")
	if action == rules.SummaryPark {
		outbox["age_gate_parked"], outbox["dormant"], outbox["deferred_reason"] = true, true, "age_gate_72h"
		outbox["deferred_since"], outbox["due_at"], outbox["task_due_at"], outbox["owner"], outbox["lease_until"] = unix(now), nil, nil, nil, int64(0)
	}
	return nil
}

func firstString(values ...string) string {
	for _, value := range values {
		if value != "" {
			return value
		}
	}
	return ""
}

func seconds(row document, key string) time.Time {
	var value float64
	switch raw := row[key].(type) {
	case float64:
		value = raw
	case int64:
		value = float64(raw)
	}
	if value <= 0 || value > 253402300799 || math.IsNaN(value) {
		return time.Time{}
	}
	sec, sub := math.Modf(value)
	return time.Unix(int64(sec), int64(sub*1e9)).UTC()
}

func unix(stamp time.Time) float64 {
	return float64(stamp.Unix()) + float64(stamp.Nanosecond())/1e9
}

func earliest(stamps ...time.Time) time.Time {
	var result time.Time
	for _, stamp := range stamps {
		if !stamp.IsZero() && (result.IsZero() || stamp.Before(result)) {
			result = stamp
		}
	}
	return result
}
