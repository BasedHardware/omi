package objectlake

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"

	"google.golang.org/api/cloudkms/v1"
	"google.golang.org/api/googleapi"
)

func (r Reader) spaceKey(ctx context.Context, wrapped string) ([]byte, error) {
	response, err := r.KMS.Projects.Locations.KeyRings.CryptoKeys.Decrypt(r.KMSKey, &cloudkms.DecryptRequest{Ciphertext: wrapped}).Context(ctx).Do()
	if err != nil {
		if ctx.Err() != nil {
			return nil, ctx.Err()
		}
		if api, ok := errors.AsType[*googleapi.Error](err); ok && api.Code == http.StatusBadRequest {
			message := strings.ToLower(api.Message)
			var body struct {
				Error struct {
					Status string `json:"status"`
				} `json:"error"`
			}
			if json.Unmarshal([]byte(api.Body), &body) == nil && body.Error.Status == "FAILED_PRECONDITION" && (strings.Contains(message, "destroyed") || strings.Contains(message, "disabled")) {
				return nil, ErrShredded
			}
		}
		return nil, ErrUnavailable
	}
	key, err := base64.StdEncoding.Strict().DecodeString(response.Plaintext)
	if err != nil || len(key) != 32 {
		clear(key)
		return nil, ErrUnavailable
	}
	return key, nil
}

func (r Reader) download(ctx context.Context, ref objectRef) (payload []byte, err error) {
	resp, err := r.Storage.Objects.Get(ref.bucket, ref.key).Context(ctx).Download()
	if err != nil {
		if ctx.Err() != nil {
			return nil, ctx.Err()
		}
		if api, ok := errors.AsType[*googleapi.Error](err); ok && api.Code == http.StatusNotFound {
			return nil, ErrAbsent
		}
		return nil, ErrUnavailable
	}
	defer func() {
		if closeErr := resp.Body.Close(); closeErr != nil && err == nil {
			payload = nil
			err = ErrUnavailable
		}
	}()
	data, err := io.ReadAll(io.LimitReader(resp.Body, ref.size+1))
	if err != nil {
		return nil, ErrUnavailable
	}
	if int64(len(data)) != ref.size {
		return nil, ErrCorrupt
	}
	return data, nil
}
