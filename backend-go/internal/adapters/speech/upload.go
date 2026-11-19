package speech

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"mime/multipart"
	"net/http"
	"net/textproto"
	"strconv"
	"strings"

	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// The encrypted base64 result must fit in one Firestore document (1 MiB).
const maxReplyBytes = 700 << 10
const maxErrorReplyBytes = 64 << 10

func newUpload(ctx context.Context, endpoint, key string, in Request) (*http.Request, error) {
	var framing bytes.Buffer
	form := multipart.NewWriter(&framing)
	if err := form.WriteField("speaker_diarization", strconv.FormatBool(!in.DisableDiarization)); err != nil {
		return nil, err
	}
	filename, contentType := "audio.wav", "audio/wav"
	if bytes.HasPrefix(in.Audio, []byte("fLaC")) {
		filename, contentType = "audio.flac", "audio/flac"
	}
	header := textproto.MIMEHeader{}
	header.Set("Content-Disposition", multipart.FileContentDisposition("upload_file", filename))
	header.Set("Content-Type", contentType)
	if _, err := form.CreatePart(header); err != nil {
		return nil, err
	}
	prefix := framing.Len()
	if err := form.Close(); err != nil {
		return nil, err
	}
	body := io.MultiReader(bytes.NewReader(framing.Bytes()[:prefix]), bytes.NewReader(in.Audio),
		bytes.NewReader(framing.Bytes()[prefix:]))
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, body)
	if err != nil {
		return nil, err
	}
	req.ContentLength = int64(framing.Len() + len(in.Audio))
	req.Header.Set("Content-Type", form.FormDataContentType())
	req.Header.Set("X-API-Key", key)
	return req, nil
}

func (m *Modulate) upload(
	ctx context.Context, g queue.Guarded, claim reservation, req *http.Request, in Request,
) (Transcript, error) {
	err := m.docs.Fenced(ctx, g, g.Tenant(), func(*docstore.Tx) error { return nil })
	if err != nil {
		return Transcript{}, storeFailure(err)
	}
	resp, err := m.http.Do(req)
	if err != nil {
		return Transcript{}, failure(CauseUnresolved)
	}
	body, tooLarge, readErr := readReply(resp)
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		cause := rejection(resp.StatusCode, body, in.UseOwnerKey)
		if cause == CauseProviderRateLimit && (tooLarge || readErr != nil) {
			cause = CauseUnresolved
		}
		return Transcript{}, m.reject(ctx, g, claim, cause)
	}
	if tooLarge || readErr != nil {
		return Transcript{}, failure(CauseUnresolved)
	}
	result, err := parseReply(body, in.Language)
	if err != nil {
		return Transcript{}, m.reject(ctx, g, claim, CauseInvalidReply)
	}
	payload, err := json.Marshal(savedReply{Body: body, Language: in.Language})
	if err != nil {
		return Transcript{}, failure(CauseStoreRejected)
	}
	if len(payload) > maxReplyBytes {
		return Transcript{}, failure(CauseUnresolved)
	}
	sealed, err := m.codec.Seal(g.Tenant(), payload)
	if err != nil {
		return Transcript{}, failure(CauseStoreRejected)
	}
	err = m.finish(ctx, g, claim, operationRecord{State: stateComplete, Reply: sealed})
	if err != nil {
		return Transcript{}, err
	}
	return result, nil
}

func readReply(resp *http.Response) ([]byte, bool, error) {
	limit := maxReplyBytes
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		limit = maxErrorReplyBytes
	}
	body, err := io.ReadAll(io.LimitReader(resp.Body, int64(limit)+1))
	if closeErr := resp.Body.Close(); err == nil {
		err = closeErr
	}
	return body, len(body) > limit, err
}

func rejection(status int, body []byte, ownerKey bool) queue.Cause {
	switch status {
	case http.StatusUnauthorized, http.StatusForbidden:
		if ownerKey {
			return CauseOwnerKey
		}
		return CauseManagedKey
	case http.StatusPaymentRequired, http.StatusTooManyRequests:
		if ownerKey {
			return CauseOwnerQuota
		}
		if status == http.StatusPaymentRequired || budgetRefusal(body) {
			return CauseProviderBudget
		}
		return CauseProviderRateLimit
	case http.StatusBadRequest, http.StatusRequestEntityTooLarge,
		http.StatusUnsupportedMediaType, http.StatusUnprocessableEntity:
		return CauseInput
	default:
		return CauseUnresolved
	}
}

func budgetRefusal(body []byte) bool {
	text := strings.ToLower(string(body))
	return strings.Contains(text, "monthly usage limit") || strings.Contains(text, "usage limit reached") ||
		strings.Contains(text, "quota exceeded") || strings.Contains(text, "insufficient credits")
}
