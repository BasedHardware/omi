package main

import "time"

type beforeErasure struct {
	Document                       any                  `json:"conversation"`
	Derived                        map[string]any       `json:"derived_documents"`
	BatchPrivacy                   batchPrivacySnapshot `json:"batch_pipeline_privacy"`
	Cost                           replayCost           `json:"cost"`
	UpdatedAtChanged               bool                 `json:"updated_at_changed"`
	PreservedFields                map[string][]string  `json:"preserved_fields"`
	EpisodeAttachMemoValid         bool                 `json:"episode_attach_memo_valid"`
	EpisodeAttachMemoExpected      bool                 `json:"episode_attach_memo_expected"`
	EpisodeAttachMemoFailureReason string               `json:"episode_attach_memo_failure_reason"`
	Finished                       time.Time            `json:"finished_at"`
}

// Select the finalization snapshots only for a proved, paired erasure.
func finalizationBeforeErasure(diffs *[]difference, python, goRun *observation) (*observation, *observation) {
	if python.BeforeErasure == nil && goRun.BeforeErasure == nil &&
		python.Effects["erasure"] == nil && goRun.Effects["erasure"] == nil {
		return python, goRun
	}
	const fixture = "erase-removes-owner-and-jobs"
	if python.ConversationID != fixture || goRun.ConversationID != fixture ||
		python.OwnerID != "replay-"+fixture || goRun.OwnerID != python.OwnerID ||
		!completedErasure(python) || !completedErasure(goRun) || !provedJobdDeparture(goRun) ||
		!equalReplayValue(goRun.Effects["erasure"], goRun.GoEvidence["erasure"]) {
		addDifference(diffs, "/effects/erasure", "invalid_binding")
		return python, goRun
	}
	return beforeErasureView(diffs, "python", python), beforeErasureView(diffs, "go", goRun)
}

func completedErasure(run *observation) bool {
	erasure := run.Effects["erasure"]
	return run.Status == "completed" && run.Document == nil &&
		objectField(erasure, "user_document_absent") == true && objectField(erasure, "conversation_absent") == true
}

func beforeErasureView(diffs *[]difference, side string, run *observation) *observation {
	pre := run.BeforeErasure
	if pre == nil || pre.Derived == nil || run.BatchPrivacy == nil ||
		!pre.Finished.After(run.Started) || pre.Finished.After(run.Finished) {
		addDifference(diffs, "/"+side+"/before_erasure", "invalid_binding")
		return run
	}
	if doc, ok := pre.Document.(map[string]any); !ok || len(doc) == 0 {
		addDifference(diffs, "/"+side+"/before_erasure/conversation", "invalid_binding")
		return run
	}
	view := *run
	view.Document = pre.Document
	view.Derived = pre.Derived
	view.BatchPrivacy = &batchPrivacyEvidence{Seed: run.BatchPrivacy.Seed, Final: pre.BatchPrivacy}
	view.Cost = pre.Cost
	view.UpdatedAtChanged = pre.UpdatedAtChanged
	view.PreservedFields = pre.PreservedFields
	view.EpisodeAttachMemoValid = pre.EpisodeAttachMemoValid
	view.EpisodeAttachMemoExpected = pre.EpisodeAttachMemoExpected
	view.EpisodeAttachMemoFailureReason = pre.EpisodeAttachMemoFailureReason
	view.Finished = pre.Finished
	return &view
}
