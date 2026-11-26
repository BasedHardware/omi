package finalization

import (
	"context"
	"encoding/json"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// Outbox is the Firestore admission boundary. Admit must read the facts and
// apply decide in the same transaction that creates or reattaches the job and
// updates the conversation. Existing intents retain their original job fields.
// Refusal returns an empty intent. PostgreSQL dispatch follows the commit.
type Outbox interface {
	Admit(ctx context.Context, a queue.Admitting, req AdmissionRequest, decide func(rules.AdmissionFacts) rules.AdmissionAction) (Intent, error)
}

// Claim identifies this invocation's immutable intent and queue fencing token.
// A lifecycle write must check the token and its authoritative document state
// in the same transaction as the write.
type Claim struct {
	Intent         Intent
	Epoch          int64
	BudgetRequeues int
	LiveBYOK       bool
	Reconcile      bool
}

// Conversation is the guarded document snapshot used by ordinary finalization.
// The opaque comparison token maps to lane 2's document-bound revision at wiring.
type Conversation struct {
	Comparison         any
	Status             rules.Status
	JobID              string
	Revision           int64
	SyncRevision       int64
	Transcript         []json.RawMessage
	Batch              rules.BatchFacts
	AppPlatform        string
	Discarded          bool
	RecordingLayer     bool
	UntrustedCapture   bool
	NoDerivedEffects   bool
	LazyEffects        bool
	PendingMinimum     bool
	SyncMinimumApplied bool
	Notes              Notes
	NotesDedupe        bool
	NotesInputHash     string
	NotesOutputHash    string
	Relevance          *RelevanceDecision
	SourceProjection   *SyncSourceProjection
	StampTerminal      bool
	InlineFanout       bool
	sectionMode        sectionKindMode
	openLoopsEnabled   bool
}

// Notes holds generated content in memory and in the owning document only.
type Notes struct {
	Title, Overview string
	Sections        []NoteSection
	ActionItems     *[]map[string]any
	Minimum         *NotesMinimum
	TitleUpdate     *SyncTitleUpdate
	OpenLoops       *SyncOpenLoops
}

// Documents uses the guarded Load and compare-and-apply pattern from lane 2.
// ApplyFinalization atomically persists completion and, when supplied, generated
// notes with their hashes. It preserves owner edits and rejects stale input.
type Documents interface {
	CheckNotesRecovery(ctx context.Context, g queue.Guarded, intent Intent) error
	CheckLive(ctx context.Context, g queue.Guarded, intent Intent, syncRevision int64) error
	Load(ctx context.Context, g queue.Guarded, ref Ref) (Conversation, error)
	ApplyFinalization(ctx context.Context, g queue.Guarded, claim Claim, before Conversation, notes *Notes, inputHash string, outputHash string) error
}

// FanoutState is the transactional outcome of acquiring ordinary fanout.
type FanoutState uint8

// Outcomes of the fanout claim transaction.
const (
	FanoutStale FanoutState = iota
	FanoutAcquired
	FanoutCommitted
)

// Fanout is a current document snapshot taken by the claim transaction.
type Fanout struct {
	State        FanoutState
	Key          string
	Conversation Conversation
}

// TerminalState is the outcome of recovering durable completion or closing an
// exhausted intent. Committed fanout always wins over dead letter.
type TerminalState uint8

// Outcomes of resolving a durable finalization intent.
const (
	TerminalStale TerminalState = iota
	TerminalComplete
	TerminalDeliveryDropped
	TerminalDeadLetter
	TerminalPending
)

// Lifecycle owns the transactions that span the job and conversation documents.
// Active mutations refuse account deletion, superseded epochs and bindings.
// Begin records ownership of the mirror under the accepted queue claim after
// checking its durable intent. Repeating it for the same claim is inert.
// ReconcileCompletion checks for a committed fanout and closes its job
// idempotently. It returns pending without mutating a job that has no commit.
// DeadLetter closes the still-bound processing row and job together, preserving
// transcript and prior output. Fence closes a stale job without mutating a
// replacement conversation. Both recheck the fanout journal before closing.
type Lifecycle interface {
	// Begin returns whether the job snapshot requires prior completion reconciliation.
	Begin(ctx context.Context, g queue.Guarded, claim Claim) (bool, error)
	ClaimFanout(ctx context.Context, g queue.Guarded, claim Claim) (Fanout, error)
	CompleteFanout(ctx context.Context, g queue.Guarded, claim Claim, dropped bool) (TerminalState, error)
	ReconcileCompletion(ctx context.Context, g queue.Guarded, claim Claim) (TerminalState, error)
	Fence(ctx context.Context, g queue.Guarded, claim Claim) (TerminalState, error)
	DeadLetter(ctx context.Context, g queue.Guarded, claim Claim, cause queue.Cause, transient bool) (TerminalState, error)
}

// MeetingEvidence waits for any applicable recording evidence and reports whether
// the service must reload the document before building a processing input.
type MeetingEvidence interface {
	Wait(ctx context.Context, g queue.Guarded, claim Claim, snapshot Conversation) (bool, error)
}

// Message and CompletionRequest describe the lane 3 non-streaming gateway
// envelope. BYOK is per invocation. It is never included in the job metadata.
type Message struct {
	Role, Text string
}

// NotesPrompt renders a serving text request for an already claimed sync row.
type NotesPrompt interface {
	PrepareNotes(ctx context.Context, g queue.Guarded, claim Claim, row Conversation) (NotesPlan, error)
}

// NotesPlan is either one paid turn or an already decided minimum.
type NotesPlan struct {
	Messages         []Message             `json:"messages"`
	Minimum          *NotesMinimum         `json:"minimum"`
	Relevance        *RelevanceDecision    `json:"relevance"`
	RichSections     bool                  `json:"rich_sections"`
	SourceProjection *SyncSourceProjection `json:"source_projection"`
	StampTerminal    bool                  `json:"terminal_family_enabled"`
	OpenLoopsEnabled bool                  `json:"open_loops_enabled"`
	EpisodeChecked   bool                  `json:"episode_checked"`
	InlineFanout     bool                  `json:"inline_fanout"`
}

// SyncSourceProjection carries Python's recorded-span and content units for the notes snapshot.
type SyncSourceProjection struct {
	EmptyDiscardHome *SyncDiscardHome   `json:"empty_discard_home"`
	RecordedStart    *time.Time         `json:"recorded_start"`
	RecordedEnd      *time.Time         `json:"recorded_end"`
	ArrivalAt        *time.Time         `json:"arrival_at"`
	Clock            string             `json:"clock"`
	ContentUnits     int64              `json:"content_word_units"`
	TitleEvidence    *SyncTitleEvidence `json:"title_evidence"`
}

// SyncDiscardHome is the reference-rendered, encrypted Home card for an
// exact empty discard. It is committed with the same source revision.
type SyncDiscardHome struct {
	Display   string     `json:"home_display"`
	Version   string     `json:"home_display_version"`
	SortAt    time.Time  `json:"home_sort_at"`
	StartedAt *time.Time `json:"home_started_at"`
	Schema    int64      `json:"home_projection_schema"`
	HasTasks  bool       `json:"home_has_tasks"`
}

// SyncTitleEvidence is Python's interpretation of the prior title on the
// same source revision. Stand-ins and legacy previews have no stable title.
type SyncTitleEvidence struct {
	Prior         string  `json:"prior"`
	ValidPrior    string  `json:"valid_prior"`
	PreviousUnits float64 `json:"previous_units"`
}

// SyncTitleUpdate is the bookkeeping for the title committed with the notes.
type SyncTitleUpdate struct {
	SetBasis bool
	Basis    int64
	Reason   string
}

// RelevanceDecision carries the serving policy's completed, content-free verdict.
type RelevanceDecision struct {
	NeighborID   string         `json:"neighbor_id"`
	Arm          string         `json:"arm"`
	Jev          map[string]any `json:"jev"`
	Verdict      string         `json:"verdict"`
	DecidedBy    string         `json:"decided_by"`
	Reason       string         `json:"reason"`
	RulesVersion int64          `json:"rules_version"`
}

// The CAS stamps the revision before a short-clip retry can skip the notes provider.
const (
	SyncMinimumRevisionField     = "go_sync_minimum_revision"
	SyncMinimumDiscardedField    = "go_sync_minimum_discarded"
	EmptyDiscardFanoutEpochField = "go_empty_discard_fanout_epoch"
)

// NotesMinimum is the outcome of a deterministic serving notes decision.
type NotesMinimum struct {
	DecidedBy    string `json:"decided_by"`
	Title        string `json:"title"`
	Discarded    bool   `json:"discarded"`
	Reason       string `json:"reason"`
	RulesVersion int64  `json:"rules_version"`
}

// EmptyTranscriptDiscard reports the blank structured result of Python's empty-speech rule.
func (n NotesMinimum) EmptyTranscriptDiscard() bool {
	return n.Discarded && n.Reason == "empty_transcript" && n.Title == ""
}

// CompletionRequest describes one guarded text call.
type CompletionRequest struct {
	Step, Feature string
	JobCreatedAt  time.Time
	Messages      []Message
	AppPlatform   string
	BYOK          *BYOK
}

// BYOK contains a live provider credential.
type BYOK struct {
	Provider, Key string
}

// Gateway must durably commit one completion per g.Operation(req.Step) and
// recover its result on repeat, even when the first response was lost. Recover
// makes no paid call and returns ErrCompletionAbsent when it cannot supply a
// committed result.
type Gateway interface {
	OperationID(g queue.Guarded, step string) string
	Complete(ctx context.Context, g queue.Guarded, req CompletionRequest) (string, error)
	Recover(ctx context.Context, g queue.Guarded, step string) (string, error)
}

// Effects run only after ownership has been acquired. Implementations deduplicate
// repeated effects using the guarded operation identity or the fanout key.
type Effects interface {
	Apply(ctx context.Context, g queue.Guarded, claim Claim, fanout Fanout, plan rules.Effects) error
}

// Target matches the destination shape that lane 5 takes for its Deliver call.
type Target struct {
	AppID                      string
	Enabled, Created, Disabled bool
	OwnedByOwner               bool
	URL                        string
	Body                       []byte
	Headers                    map[string]string
}

// IntegrationEvent identifies the claimed conversation revision, in lane 5's shape.
type IntegrationEvent struct {
	ConversationID    string
	Revision          int64
	FanoutKey         string
	Locked, Discarded bool
}

// IntegrationTargets resolves the current owner settings and delivery projections.
type IntegrationTargets interface {
	Resolve(ctx context.Context, g queue.Guarded, claim Claim, snapshot Conversation) ([]Target, error)
}

// DeliveryBudget carries the active finalization attempt to integrations.
type DeliveryBudget struct {
	Attempt int
	Epoch   int64
	Final   bool
}

// Integrations sends each eligible target under the current guard using the
// revision key. On the final attempt a transient delivery is reported as dropped.
type Integrations interface {
	Deliver(ctx context.Context, g queue.Guarded, event IntegrationEvent, targets []Target, budget DeliveryBudget) (bool, error)
}
