package objectlake

import (
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"

	"google.golang.org/api/cloudkms/v1"
	"google.golang.org/api/option"
	"google.golang.org/api/storage/v1"

	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore/docstoretest"
)

const kmsResource = "projects/synthetic/locations/global/keyRings/test/cryptoKeys/transcript"
const conversationPath = "users/owner/conversations/conversation"

type liveOwner string

func (l liveOwner) Tenant() string { return string(l) }
func (l liveOwner) Err() error     { return nil }

func custody() map[string]any {
	return map[string]any{"space_id": "owner", "kms_key": kmsResource, "algo": "AES-256-GCM", "active_version": int64(8), "versions": []any{
		map[string]any{"version": int64(7), "state": "retired", "wrapped_at": "earlier", "wrapped": "b2xk"},
		map[string]any{"version": int64(8), "state": "active", "wrapped_at": "later", "wrapped": "bmV3"},
	}}
}
func tombstone() map[string]any {
	return map[string]any{"space_id": "owner", "state": "destroyed", "destroyed_at": "later"}
}

func setRow(t *testing.T, b docstoretest.Bench, path string, data map[string]any) {
	t.Helper()
	if _, err := b.Raw.Doc(path).Set(t.Context(), data); err != nil {
		t.Fatal(err)
	}
}

func ptr(ref objectRef) map[string]any {
	return map[string]any{"bucket": ref.bucket, "key": ref.key, "sha256": ref.digest, "bytes": ref.size, "class": "transcript", "dek_version": ref.version}
}

type readCase struct {
	name                  string
	keyRow                map[string]any
	rowField              string
	rowValue              any
	storageCode, kmsCode  int
	kmsStatus, kmsMessage string
	duringFetch           string
	want                  error
	kmsCalls, blobCalls   int32
}

func TestGuardedRead(t *testing.T) {
	cases := []readCase{
		{name: "retired version", keyRow: custody(), blobCalls: 1, kmsCalls: 1},
		{name: "absent", keyRow: custody(), storageCode: 404, want: ErrAbsent, kmsCalls: 1, blobCalls: 1},
		{name: "tombstone wins over absent", keyRow: tombstone(), storageCode: 404, want: ErrShredded},
		{name: "missing authority", storageCode: 404, want: ErrShredded},
		{name: "bad custody", keyRow: map[string]any{"state": "destroyed"}, want: ErrUnavailable},
		{name: "unavailable blob", keyRow: custody(), storageCode: 503, want: ErrUnavailable, kmsCalls: 1, blobCalls: 1},
		{name: "unavailable KMS", keyRow: custody(), kmsCode: 503, want: ErrUnavailable, kmsCalls: 1},
		{name: "disabled key", keyRow: custody(), kmsCode: 400, kmsStatus: "FAILED_PRECONDITION", kmsMessage: "key disabled", want: ErrShredded, kmsCalls: 1},
		{name: "unrelated KMS error", keyRow: custody(), kmsCode: 400, kmsStatus: "INVALID_ARGUMENT", kmsMessage: "disabled", want: ErrUnavailable, kmsCalls: 1},
		{name: "private", keyRow: custody(), rowField: "data_protection_level", rowValue: "private", want: ErrRestricted},
		{name: "visibility withdrawn", keyRow: custody(), rowField: "visibility", rowValue: "private", want: ErrRestricted},
		{name: "unknown visibility", keyRow: custody(), rowField: "visibility", rowValue: nil, want: ErrRestricted},
		{name: "locked", keyRow: custody(), rowField: "is_locked", rowValue: true, want: ErrRestricted},
		{name: "deleted", keyRow: custody(), rowField: "deleted", rowValue: true, want: docstore.ErrMissing},
		{name: "stale", keyRow: custody(), rowField: "transcript_segments", rowValue: []string{}, want: ErrChanged},
		{name: "repointed while fetching", keyRow: custody(), duringFetch: "repoint", want: ErrChanged, kmsCalls: 1, blobCalls: 1},
		{name: "shredded during missing download", keyRow: custody(), storageCode: 404, duringFetch: "shred", want: ErrShredded, kmsCalls: 1, blobCalls: 1},
		{name: "erase during fetch", keyRow: custody(), duringFetch: "erase", want: docstore.ErrOwnerDeleting, kmsCalls: 1, blobCalls: 1},
		{name: "key destroyed during fetch", keyRow: custody(), duringFetch: "shred", want: ErrShredded, kmsCalls: 1, blobCalls: 1},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) { runRead(t, tc) })
	}
}

func runRead(t *testing.T, tc readCase) {
	t.Helper()
	b := docstoretest.Open(t)
	ref, payload := vector(t, wrapped)
	pointer := ptr(ref)
	row := map[string]any{"transcript_segments": pointer, "visibility": "shared"}
	if tc.rowField != "" {
		row[tc.rowField] = tc.rowValue
	}
	setRow(t, b, conversationPath, row)
	if tc.keyRow != nil {
		setRow(t, b, "space_keys/owner", tc.keyRow)
	}
	var kmsCalls, blobCalls atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.Method {
		case http.MethodPost:
			kmsCalls.Add(1)
			var in cloudkms.DecryptRequest
			if r.URL.Path != "/v1/"+kmsResource+":decrypt" || json.NewDecoder(r.Body).Decode(&in) != nil || in.Ciphertext != "b2xk" {
				t.Error("wrong key resource or version")
			}
			w.Header().Set("Content-Type", "application/json")
			if tc.kmsCode != 0 {
				w.WriteHeader(tc.kmsCode)
				if _, err := fmt.Fprintf(w, `{"error":{"code":%d,"status":%q,"message":%q}}`, tc.kmsCode, tc.kmsStatus, tc.kmsMessage); err != nil {
					t.Error(err)
				}
				return
			}
			if err := json.NewEncoder(w).Encode(cloudkms.DecryptResponse{Plaintext: base64.StdEncoding.EncodeToString(fixtureKey())}); err != nil {
				t.Error(err)
			}
		case http.MethodGet:
			blobCalls.Add(1)
			if r.URL.Path != "/b/"+ref.bucket+"/o/"+ref.key || r.URL.Query().Get("alt") != "media" {
				t.Errorf("unexpected storage path %s", r.URL.Path)
			}

			var path string
			var update map[string]any
			switch tc.duringFetch {
			case "repoint":
				path, update = conversationPath, map[string]any{"transcript_segments": []any{}, "visibility": "public"}
			case "erase":
				path, update = docstore.MarkerCollection+"/owner", map[string]any{"wipe_status": "pending"}
			case "shred":
				path, update = "space_keys/owner", tombstone()
			}
			if path != "" {
				if _, err := b.Raw.Doc(path).Set(r.Context(), update); err != nil {
					t.Error(err)
				}
			}
			if tc.storageCode != 0 {
				w.WriteHeader(tc.storageCode)
				return
			}
			if _, err := w.Write(payload); err != nil {
				t.Error(err)
			}
		default:
			t.Error("unexpected HTTP method")
			w.WriteHeader(http.StatusBadRequest)
		}
	}))
	defer server.Close()
	reader := localReader(t, b, server.URL)
	got, err := reader.Read(t.Context(), liveOwner("owner"), "owner", "conversation", pointer)
	if !errors.Is(err, tc.want) || (got == nil) != (tc.want != nil) {
		t.Fatalf("returned segments=%t, err=%v; want %v", got != nil, err, tc.want)
	}
	if got != nil && (len(got) != 2 || string(got[0]) != `{"text":"one"}`) {
		t.Fatal("unexpected transcript")
	}
	if kmsCalls.Load() != tc.kmsCalls || blobCalls.Load() != tc.blobCalls {
		t.Errorf("KMS=%d storage=%d", kmsCalls.Load(), blobCalls.Load())
	}
}

func localReader(t *testing.T, b docstoretest.Bench, url string) Reader {
	t.Helper()
	opts := []option.ClientOption{option.WithEndpoint(url + "/"), option.WithoutAuthentication()}
	kms, err := cloudkms.NewService(t.Context(), opts...)
	if err != nil {
		t.Fatal(err)
	}
	objects, err := storage.NewService(t.Context(), opts...)
	if err != nil {
		t.Fatal(err)
	}
	return Reader{Enabled: true, Bucket: "test-bucket", KMSKey: kmsResource, Docs: b.Store, KMS: kms, Storage: objects}
}

func TestRefAndAuthorityValidation(t *testing.T) {
	ref, _ := vector(t, wrapped)
	for field, bad := range map[string]any{"bucket": "other", "key": strings.Replace(ref.key, "/owner/", "/other/", 1), "class": "voice", "sha256": emptyDigest, "bytes": float64(75), "dek_version": int64(0)} {
		p := ptr(ref)
		p[field] = bad
		if _, err := parseRef(p, ref.bucket, "owner", "conversation"); !errors.Is(err, ErrCorrupt) {
			t.Errorf("accepted wrong %s", field)
		}
	}
	if _, err := parseRef(ptr(ref), ref.bucket, "owner", "other"); !errors.Is(err, ErrCorrupt) {
		t.Fatal("accepted another conversation")
	}
	if _, err := wrappedVersion(custody(), "owner", kmsResource, 6); !errors.Is(err, ErrCorrupt) {
		t.Fatal("accepted unknown version")
	}
	if _, err := wrappedVersion(custody(), "owner", "other", 7); !errors.Is(err, ErrUnavailable) {
		t.Fatal("accepted wrong KMS resource")
	}
	if _, err := (Reader{}).Read(t.Context(), liveOwner("other"), "owner", "conversation", ptr(ref)); !errors.Is(err, docstore.ErrOwnerMismatch) {
		t.Fatal("accepted mismatched guard")
	}
	if _, err := (Reader{}).Read(t.Context(), liveOwner("owner"), "owner", "conversation", ptr(ref)); !errors.Is(err, ErrUnavailable) {
		t.Fatal("accepted disabled reader")
	}
}
