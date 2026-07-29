package omiintegration

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestListMemoriesAuthAndPath(t *testing.T) {
	var sawAuth, sawURL string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		sawAuth = r.Header.Get("Authorization")
		sawURL = r.URL.String()
		_ = json.NewEncoder(w).Encode(map[string]any{"memories": []any{}})
	}))
	defer server.Close()

	client := New("test-key", "app-123")
	client.BaseURL = server.URL
	raw, err := client.ListMemories(context.Background(), "user-1", nil)
	if err != nil {
		t.Fatal(err)
	}
	if string(raw) == "" {
		t.Fatal("empty body")
	}
	if sawAuth != "Bearer test-key" {
		t.Fatalf("auth=%q", sawAuth)
	}
	if !strings.Contains(sawURL, "/v2/integrations/app-123/memories") {
		t.Fatalf("url=%q", sawURL)
	}
	if !strings.Contains(sawURL, "uid=user-1") {
		t.Fatalf("url=%q", sawURL)
	}
}

func TestAPIError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(401)
		_, _ = io.WriteString(w, `{"detail":"nope"}`)
	}))
	defer server.Close()
	client := New("test-key", "app-123")
	client.BaseURL = server.URL
	_, err := client.ListMemories(context.Background(), "user-1", nil)
	if err == nil {
		t.Fatal("expected error")
	}
	apiErr, ok := err.(*APIError)
	if !ok || apiErr.StatusCode != 401 {
		t.Fatalf("err=%v", err)
	}
}
