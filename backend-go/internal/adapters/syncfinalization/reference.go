// Package syncfinalization connects the ordinary sync worker to the Python
// policies it shares during cutover. Each call is scoped to the live Go claim.
package syncfinalization

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/platform/httpx"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// Reference calls the authenticated serving policy adapter.
type Reference struct {
	Client *httpx.Client
	Bearer func(context.Context) (string, error)
}

type request struct {
	Owner        string            `json:"owner"`
	Conversation string            `json:"conversation"`
	Job          string            `json:"job"`
	Revision     int64             `json:"revision"`
	SyncRevision int64             `json:"sync_revision"`
	QueueEpoch   int64             `json:"queue_epoch"`
	Step         string            `json:"step"`
	Operation    string            `json:"operation"`
	ActionItems  []json.RawMessage `json:"action_items,omitempty"`
}

type target struct {
	AppID string          `json:"app_id"`
	URL   string          `json:"url"`
	Owned bool            `json:"owned"`
	Body  json.RawMessage `json:"body"`
}

// Wait rejects paths outside the ordinary sync producer. Python's
// await_meeting_evidence only polls capture_end and client_finalize.
func (a Reference) Wait(_ context.Context, g queue.Guarded, claim finalization.Claim, row finalization.Conversation) (bool, error) {
	return false, validateClaim(g, claim, row)
}

// PrepareNotes fetches the serving prompt under the same snapshot binding as effects.
func (a Reference) PrepareNotes(ctx context.Context, g queue.Guarded, claim finalization.Claim, row finalization.Conversation) (finalization.NotesPlan, error) {
	var result finalization.NotesPlan
	if err := a.call(ctx, g, claim, row, "notes", &result); err != nil {
		return result, err
	}
	if !result.EpisodeChecked {
		// Older adapters return a notes plan before checking membership.
		// Keep the check until both deployments use the combined route.
		wait, err := a.waitForEpisode(ctx, g, claim, row)
		if err != nil {
			return result, err
		}
		if wait {
			return result, deferEpisodeNotes()
		}
	}
	return result, nil
}

// Apply requests the deduplicated sync effects for the claimed revision.
func (a Reference) Apply(ctx context.Context, g queue.Guarded, claim finalization.Claim, fanout finalization.Fanout, plan rules.Effects) error {
	switch plan {
	case rules.EagerEffects:
		return a.call(ctx, g, claim, fanout.Conversation, "effects", nil)
	case rules.DeferEffects:
		return a.call(ctx, g, claim, fanout.Conversation, "deferred-effects", nil)
	case rules.SuppressEffects:
		return nil
	}
	return finalization.ErrInvalid
}

var errCombinedStepUnsupported = errors.New("sync finalization: combined step unsupported")

// ApplyAndReconcile shares a receiver commit between effects and episode repair.
func (a Reference) ApplyAndReconcile(ctx context.Context, g queue.Guarded, claim finalization.Claim, fanout finalization.Fanout) (bool, error) {
	var result struct {
		Combined bool `json:"combined"`
	}
	err := a.call(ctx, g, claim, fanout.Conversation, "effects-episode", &result)
	if errors.Is(err, errCombinedStepUnsupported) {
		return false, nil
	}
	return result.Combined, err
}

// Resolve uses the serving app eligibility and redaction policies before Go
// delivers any webhook. Application secrets are excluded from the wire.
func (a Reference) Resolve(ctx context.Context, g queue.Guarded, claim finalization.Claim, row finalization.Conversation) ([]finalization.Target, error) {
	var result struct {
		Targets []target `json:"targets"`
	}
	if err := a.call(ctx, g, claim, row, "targets", &result); err != nil {
		return nil, err
	}
	targets := make([]finalization.Target, 0, len(result.Targets))
	for _, dst := range result.Targets {
		targets = append(targets, finalization.Target{
			AppID: dst.AppID, Enabled: true, Created: true, OwnedByOwner: dst.Owned, URL: dst.URL, Body: dst.Body,
		})
	}
	return targets, nil
}

// Start requests episode construction for the claimed sync revision and reports whether it must wait.
func (a Reference) Start(ctx context.Context, g queue.Guarded, claim finalization.Claim, row finalization.Conversation) (bool, error) {
	if rules.NeedsNotes(row.Status, row.PendingMinimum) && !row.SyncMinimumApplied &&
		!row.RecordingLayer && !row.NoDerivedEffects {
		// The notes endpoint checks live episode membership on the same
		// fenced read it already needs to prepare the prompt.
		return false, validateClaim(g, claim, row)
	}
	return a.waitForEpisode(ctx, g, claim, row)
}

func (a Reference) waitForEpisode(ctx context.Context, g queue.Guarded, claim finalization.Claim, row finalization.Conversation) (bool, error) {
	var result struct {
		Wait bool `json:"wait"`
	}
	err := a.call(ctx, g, claim, row, "episode-start", &result)
	return result.Wait, err
}

// Reconcile requests episode reconciliation for the claimed sync revision.
func (a Reference) Reconcile(ctx context.Context, g queue.Guarded, claim finalization.Claim, row finalization.Conversation) error {
	return a.call(ctx, g, claim, row, "episode-reconcile", nil)
}

// ValidateActions uses the Python extraction schema and authentic transcript IDs
// before a provider-generated action can enter the stored conversation.
func (a Reference) ValidateActions(ctx context.Context, g queue.Guarded, claim finalization.Claim, row finalization.Conversation, actions []json.RawMessage) ([]map[string]any, error) {
	var result struct {
		ActionItems []map[string]any `json:"action_items"`
	}
	if err := a.send(ctx, g, claim, row, "notes-actions", actions, &result); err != nil {
		return nil, err
	}
	for _, item := range result.ActionItems {
		for _, field := range []string{"due_at", "created_at"} {
			if raw, ok := item[field].(string); ok {
				at, err := time.Parse(time.RFC3339Nano, raw)
				if err != nil {
					return nil, finalization.ErrInvalid
				}
				item[field] = at
			}
		}
	}
	return result.ActionItems, nil
}

func validateClaim(g queue.Guarded, claim finalization.Claim, row finalization.Conversation) error {
	if err := g.Err(); err != nil {
		return err
	}
	in := claim.Intent
	if in.Trigger != rules.SyncUpdate || in.RequiresBYOK || g.Tenant() != in.Ref.Owner ||
		row.JobID != in.JobID || row.Revision != in.Revision || row.SyncRevision <= 0 {
		return finalization.ErrInvalid
	}
	return nil
}

func (a Reference) call(ctx context.Context, g queue.Guarded, claim finalization.Claim, row finalization.Conversation, step string, out any) error {
	return a.send(ctx, g, claim, row, step, nil, out)
}

func (a Reference) send(ctx context.Context, g queue.Guarded, claim finalization.Claim, row finalization.Conversation, step string, actions []json.RawMessage, out any) error {
	if err := validateClaim(g, claim, row); err != nil {
		return err
	}
	in := claim.Intent
	token, err := a.Bearer(ctx)
	if err != nil || token == "" {
		return errors.New("sync finalization: reference identity unavailable")
	}
	req := request{
		Owner: in.Ref.Owner, Conversation: in.Ref.ID, Job: in.JobID, Revision: in.Revision,
		SyncRevision: row.SyncRevision, QueueEpoch: claim.Epoch, Step: step,
		Operation:   g.Operation(fmt.Sprintf("sync-reference:%s:%d", step, row.SyncRevision)),
		ActionItems: actions,
	}
	fault := a.Client.Do(ctx, httpx.Request{
		Method: http.MethodPost, Path: "/internal/finalization/sync-reference", Body: req, Out: out,
		Header: map[string]string{"Authorization": "Bearer " + token},
	})
	if fault == nil {
		return nil
	}
	// Legacy receivers reject the new enum value before invoking the handler.
	if step == "effects-episode" && fault.Status == http.StatusUnprocessableEntity {
		return errCombinedStepUnsupported
	}
	// Uncertain submissions keep their original reservation and must never be
	// started again based on a transport timeout or an expired queue lease.
	if fault.Status == http.StatusConflict && fault.Code == "operation_unsettled" {
		return queue.Classify(errors.New("sync finalization: unsettled reference operation"), queue.Yield(finalization.CauseStore, time.Minute))
	}
	if fault.Status == http.StatusConflict && fault.Code == "unsupported_row" {
		return queue.Classify(finalization.ErrInvalid, queue.Yield(finalization.CauseStore, time.Minute))
	}
	if fault.Status == http.StatusConflict && fault.Code == "source_changed" {
		return queue.Classify(finalization.ErrSourceChanged, queue.Retry(finalization.CauseChanged, 0))
	}
	if fault.Status == http.StatusConflict && fault.Code == "live_episode_notes" {
		return deferEpisodeNotes()
	}
	if fault.Status == http.StatusConflict && fault.Code == "ownership_changed" {
		return finalization.ErrStale
	}
	return errors.New("sync finalization: reference call failed")
}

func deferEpisodeNotes() error {
	return queue.Classify(errors.New("sync finalization: live episode member owns notes"), queue.Yield(finalization.CauseEpisodeNotes, time.Minute))
}

// OrdinaryCustody refuses batch operations. The serving worker admits only
// ordinary sync, whose retained audio is already held by the sync producer.
type OrdinaryCustody struct{}

// Reserve defers archive reservation to the batch producer.
func (OrdinaryCustody) Reserve(context.Context, queue.Guarded, finalization.Claim, finalization.Conversation) error {
	return errUnexpectedBatch
}

// CompleteCapture defers archive completion to the batch producer.
func (OrdinaryCustody) CompleteCapture(context.Context, queue.Guarded, finalization.Claim, finalization.Conversation) error {
	return errUnexpectedBatch
}

// DeleteEmpty defers empty archive cleanup to the batch producer.
func (OrdinaryCustody) DeleteEmpty(context.Context, queue.Guarded, finalization.Claim, finalization.Conversation) error {
	return errUnexpectedBatch
}

var errUnexpectedBatch = queue.Classify(
	errors.New("sync finalization: batch custody belongs to the batch producer"),
	queue.Yield(finalization.CauseArchiveOpen, time.Minute),
)
