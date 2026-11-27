package stubapi

import (
	"context"

	"github.com/BasedHardware/omi/backend-go/internal/batchunit"
	"github.com/BasedHardware/omi/backend-go/internal/platform/crypt"
	"github.com/BasedHardware/omi/backend-go/internal/platform/httpx"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

type NotesOutput struct {
	Title    string `json:"title"`
	Overview string `json:"overview"`
}

type Document struct {
	crypt.Transcript
	Version            int64        `json:"version"`
	Status             string       `json:"status"`
	Job                string       `json:"finalization_job_id"`
	Revision           int64        `json:"finalization_revision"`
	FinalizationStatus string       `json:"finalization_status"`
	Discarded          bool         `json:"discarded"`
	DiscardedByUser    bool         `json:"discarded_by_user"`
	Deleted            bool         `json:"deleted"`
	Tombstone          bool         `json:"tombstone"`
	Protection         string       `json:"data_protection_level"`
	NotesHash          string       `json:"notes_llm_input_hash"`
	NotesCache         *NotesOutput `json:"jobd_notes"`
	Structured         *NotesOutput `json:"structured"`
	MemoriesHash       string       `json:"memories_llm_input_hash"`
	MemoryCache        []string     `json:"jobd_memories"`
	FanoutState        string       `json:"fanout_state"`
	FanoutKey          string       `json:"fanout_key"`
}

type Patch map[string]any

func (c *Client) Document(ctx context.Context, uid, cid string) (d Document, f *Fault) {
	f = c.call(ctx, DocumentVendor, "GET", httpx.Path("/conversations", uid, cid), nil, &d, "")
	return
}

func (c *Client) Patch(ctx context.Context, uid, cid string, version int64, p Patch) (d Document, f *Fault) {
	body := struct {
		Version int64 `json:"expected_version"`
		Patch   Patch `json:"patch"`
	}{version, p}
	f = c.call(ctx, DocumentVendor, "PATCH", httpx.Path("/conversations", uid, cid), body, &d, "")
	return
}

func (c *Client) Notes(ctx context.Context, in VendorInput, key string) (out NotesOutput, f *Fault) {
	f = c.call(ctx, LLMVendor, "POST", "/llm/notes", in, &out, key)
	return
}

func (c *Client) Memories(ctx context.Context, in VendorInput, revision int64, key string) ([]string, *Fault) {
	body := struct {
		VendorInput
		Revision int64 `json:"revision"`
	}{in, revision}
	var out struct {
		Contents []string `json:"contents"`
	}
	f := c.call(ctx, LLMVendor, "POST", "/llm/memories", body, &out, key)
	return out.Contents, f
}

func (c *Client) Speech(ctx context.Context, in VendorInput, route batchunit.Route, byok bool) (string, *Fault) {
	var out struct {
		Result string `json:"result"`
	}
	body := struct {
		VendorInput
		Route batchunit.Route `json:"route,omitempty"`
		BYOK  bool            `json:"byok,omitempty"`
	}{in, route, byok}
	f := c.call(ctx, SpeechVendor, "POST", "/speech/unit", body, &out, "")
	return out.Result, f
}

type Effect struct {
	UID      string `json:"uid"`
	Subject  string `json:"subject_id"`
	Job      string `json:"job_id"`
	Revision int64  `json:"revision"`
}

func EffectFor(j queue.Job, revision int64) Effect {
	return Effect{j.Tenant, j.Subject, j.Key, revision}
}

func (c *Client) SaveMemory(ctx context.Context, e Effect, id, content, protection string) *Fault {
	body := struct {
		Effect
		Content    string `json:"content"`
		Protection string `json:"data_protection_level"`
	}{e, content, protection}
	return c.call(ctx, MemoryVendor, "PUT", httpx.Path("/memories", e.UID, id), body, nil, "")
}

func (c *Client) Vector(ctx context.Context, e Effect, overview string) *Fault {
	body := struct {
		Effect
		Overview string `json:"overview"`
	}{e, overview}
	return c.call(ctx, VectorVendor, "PUT", httpx.Path("/vectors", e.UID, e.Subject), body, nil, "")
}

func (c *Client) Webhook(ctx context.Context, e Effect, app, fanout string, final bool) *Fault {
	return c.do(ctx, spec{
		vendor: AppVendor, method: "POST", path: httpx.Path("/apps", app), body: e,
		idempotency: fanout, dropTransient: final,
	})
}
