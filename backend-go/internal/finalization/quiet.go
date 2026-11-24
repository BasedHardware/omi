package finalization

import (
	"context"
	"crypto/sha256"
	"fmt"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// QuietID is shared with the Python listen producer.
func QuietID(ref Ref) string {
	return fmt.Sprintf("quiet-%x", sha256.Sum256([]byte(ref.Owner+"\x00"+ref.ID)))
}

// QuietCheck identifies a durable wake and its scheduled time.
type QuietCheck struct {
	Ref        Ref
	Generation int64
	Due        time.Time
}

// QuietWake is the transaction result and, where applicable, its
// already-durable successor. Cutoff is the absolute admission fence.
type QuietWake struct {
	Check  QuietCheck
	Action rules.QuietAction
	Cutoff time.Time
}

// QuietStore serializes recording wake changes with the authoritative rows.
type QuietStore interface {
	ArmQuiet(ctx context.Context, a queue.Admitting, ref Ref, timeout float64, requiresBYOK bool) (QuietCheck, error)
	WakeQuiet(ctx context.Context, a queue.Admitting, check QuietCheck) (QuietWake, error)
	ResolveQuietLimit(ctx context.Context, a queue.Admitting, wake QuietWake, cause error) (rules.QuietAction, bool, error)
}

// ArmQuiet records an idempotent check for an authenticated disconnect.
func (s *Service) ArmQuiet(ctx context.Context, ref Ref, timeout float64, requiresBYOK bool) (QuietCheck, error) {
	var check QuietCheck
	err := s.Queue.Tenant(ctx, ref.Owner, func(sc *queue.Scope) error {
		var armErr error
		check, armErr = s.Quiet.ArmQuiet(ctx, sc.Admitting(), ref, timeout, requiresBYOK)
		return armErr
	})
	return check, err
}

// WakeQuiet evaluates a check and tries admission only after persisting the
// successor. A failed admission leaves the successor available for replay.
func (s *Service) WakeQuiet(ctx context.Context, check QuietCheck, dispatchAvailable bool) (QuietWake, Intent, error) {
	if !dispatchAvailable {
		return QuietWake{}, Intent{}, ErrDispatchUnavailable
	}
	var wake QuietWake
	err := s.Queue.Tenant(ctx, check.Ref.Owner, func(sc *queue.Scope) error {
		var wakeErr error
		wake, wakeErr = s.Quiet.WakeQuiet(ctx, sc.Admitting(), check)
		return wakeErr
	})
	if err != nil || wake.Action != rules.QuietReady {
		return wake, Intent{}, err
	}
	intent, err := s.Admit(ctx, AdmissionRequest{
		Ref: check.Ref, Trigger: rules.ServerRecovery, RequiresDispatch: true, DispatchAvailable: true,
		RequireExpiredLease: true, RecoveryCutoff: wake.Cutoff, QuietGeneration: wake.Check.Generation,
	})
	if err == nil || intent.JobID != "" {
		return wake, intent, err
	}
	return s.resolveQuietFailure(ctx, wake, err)
}

func (s *Service) resolveQuietFailure(ctx context.Context, wake QuietWake, cause error) (QuietWake, Intent, error) {
	var action rules.QuietAction
	var matched bool
	err := s.Queue.Tenant(ctx, wake.Check.Ref.Owner, func(sc *queue.Scope) error {
		var handleErr error
		action, matched, handleErr = s.Quiet.ResolveQuietLimit(ctx, sc.Admitting(), wake, cause)
		return handleErr
	})
	if err != nil {
		return wake, Intent{}, err
	}
	if !matched {
		return wake, Intent{}, cause
	}
	wake.Action = action
	return wake, Intent{}, nil
}
