package finalization

import (
	"context"
	"encoding/json"
	"errors"

	wire "github.com/BasedHardware/omi/backend-go/internal/conformance/stubapi"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

type progress struct {
	MemoriesDone bool            `json:"memories_done,omitempty"`
	MemoryWrites int             `json:"memory_writes,omitempty"`
	VectorDone   bool            `json:"vector_done,omitempty"`
	VectorFailed bool            `json:"vector_failed,omitempty"`
	Apps         map[string]bool `json:"apps,omitempty"` // true denotes a dropped delivery
}

func (f *flow) progress() progress {
	var p progress
	// A checkpoint that does not decode is treated as no progress: every effect is idempotent.
	if err := json.Unmarshal(f.r.Job().Checkpoint, &p); err != nil {
		p = progress{}
	}
	if p.Apps == nil {
		p.Apps = make(map[string]bool)
	}
	return p
}

func (f *flow) save(step string, p progress) error {
	raw, err := json.Marshal(p)
	if err != nil {
		return err
	}
	return f.r.Save(f.ctx, step, raw)
}

func (f *flow) fanout(input string) error {
	if f.doc.FanoutState == "completed" {
		return nil
	}
	p := f.progress()
	if !p.MemoriesDone {
		if err := f.memories(input, &p); err != nil {
			return err
		}
	}
	if !p.VectorDone {
		if err := f.vector(&p); err != nil {
			return err
		}
	}
	return f.finishFanout(p)
}

func (f *flow) memories(text string, p *progress) error {
	if err := f.r.SetStep(f.ctx, "memories"); err != nil {
		return err
	}
	defer f.r.Observe("memories")()
	j := f.r.Job()
	in := wire.Input(j, "memories", text)
	if err := f.extract(in); err != nil {
		return err
	}
	e := wire.EffectFor(j, f.meta.Revision)
	for i := p.MemoryWrites; i < len(f.doc.MemoryCache); i++ {
		id := wire.ID("memory", j.Key, in.Hash, revisionString(int64(i)))
		content := f.doc.MemoryCache[i]
		err := wire.Guard(f.ctx, f.r, func(ctx context.Context) *wire.Fault {
			return f.Wire.SaveMemory(ctx, e, id, content, f.doc.Protection)
		})
		if err != nil {
			return err
		}
		p.MemoryWrites = i + 1
		if i+1 < len(f.doc.MemoryCache) {
			if err := f.save("memories", *p); err != nil {
				return err
			}
		}
	}
	p.MemoriesDone = true
	return f.save("vector", *p)
}

func (f *flow) extract(in wire.VendorInput) error {
	if f.doc.MemoriesHash == in.Hash {
		f.Wire.Dedupe(wire.Memories, true)
		return nil
	}
	f.Wire.Dedupe(wire.Memories, false)
	var memories []string
	err := wire.Guard(f.ctx, f.r, func(ctx context.Context) (fault *wire.Fault) {
		memories, fault = f.Wire.Memories(ctx, in, f.meta.Revision, f.vendorKey)
		return
	})
	if err != nil {
		return err
	}
	protection := f.doc.Protection
	if protection == "enhanced" {
		for i, text := range memories {
			memories[i], err = f.Codec.Seal(f.r.Job().Tenant, []byte(text))
			if err != nil {
				return unreadable()
			}
		}
	}
	return f.patch(func(d wire.Document) (wire.Patch, *wire.Fault) {
		if e := f.canFanout(d); e != nil {
			return nil, e
		}
		if d.FanoutState != "claimed" || d.FanoutKey != f.meta.FanoutKey {
			return nil, conversationFence()
		}
		if d.Protection != protection {
			return nil, versionConflict()
		}
		if e := f.sameInput(d, in); e != nil {
			return nil, e
		}
		return wire.Patch{"memories_llm_input_hash": in.Hash, "jobd_memories": memories}, nil
	})
}

func (f *flow) vector(p *progress) error {
	defer f.r.Observe("vector")()
	overview := ""
	if f.doc.Structured != nil {
		overview = f.doc.Structured.Overview
	}
	e := wire.EffectFor(f.r.Job(), f.meta.Revision)
	err := wire.Guard(f.ctx, f.r, func(ctx context.Context) *wire.Fault {
		return f.Wire.Vector(ctx, e, overview)
	})
	if err != nil {
		var fault *wire.Fault
		if !errors.As(err, &fault) || fault.Result == wire.Fenced || fault.Cause == wire.CauseAccountDeleting {
			return err
		}
		p.VectorFailed = true
		if f.Warn != nil {
			f.Warn(wire.Digest(f.r.Job().Key)[:16], CauseVectorFailed)
		}
	}
	p.VectorDone = true
	return f.save("integrations", *p)
}

func (f *flow) finishFanout(p progress) error {
	if err := f.integrate(&p); err != nil {
		return err
	}
	if err := f.r.SetStep(f.ctx, "complete"); err != nil {
		return err
	}
	defer f.r.Observe("complete")()
	return f.patch(func(d wire.Document) (wire.Patch, *wire.Fault) {
		if e := f.canFanout(d); e != nil {
			return nil, e
		}
		if d.FanoutState == "completed" {
			return nil, nil
		}
		if d.FanoutState != "claimed" || d.FanoutKey != f.meta.FanoutKey {
			return nil, conversationFence()
		}
		return wire.Patch{"fanout_state": "completed", "jobd_memories": nil}, nil
	})
}

func (f *flow) integrate(p *progress) error {
	defer f.r.Observe("integrations")()
	e := wire.EffectFor(f.r.Job(), f.meta.Revision)
	for _, app := range f.account.Apps {
		// Store only opaque receipt IDs. App identifiers are sink routing data.
		id := wire.ID("app-receipt", f.r.Job().Key, app)
		if _, ok := p.Apps[id]; ok {
			f.Wire.Dedupe(wire.Integration, true)
			continue
		}
		f.Wire.Dedupe(wire.Integration, false)
		err := wire.Guard(f.ctx, f.r, func(ctx context.Context) *wire.Fault {
			return f.Wire.Webhook(ctx, e, app, f.meta.FanoutKey, f.r.FinalAttempt())
		})
		if err != nil {
			var fault *wire.Fault
			if !errors.As(err, &fault) || fault.Result != wire.Dropped {
				return err
			}
		}
		p.Apps[id] = err != nil
		if err := f.save("integrations", *p); err != nil {
			return err
		}
	}
	return nil
}

// completion is the cause a finished job records: none, or the best-effort step it lost.
func (f *flow) completion() queue.Cause {
	p := f.progress()
	for _, dropped := range p.Apps {
		if dropped {
			return wire.CauseIntegrationDropped
		}
	}
	if p.VectorFailed {
		return CauseVectorFailed
	}
	return queue.CauseNone
}

func (f *flow) success() queue.Outcome {
	if err := f.r.SetStep(f.ctx, "complete"); err != nil {
		return wire.Outcome(err)
	}
	return queue.DoneWith(f.completion())
}

func (f *flow) resolved() queue.Resolution {
	if err := f.r.SetStep(f.ctx, "complete"); err != nil {
		return wire.Resolution(err)
	}
	return queue.ResolvedWith(f.completion())
}
