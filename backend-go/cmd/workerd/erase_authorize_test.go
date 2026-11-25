package main

import (
	"crypto"
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"io"
	"math/big"
	"net/http"
	"strings"
	"testing"
	"time"

	"google.golang.org/api/idtoken"
	"google.golang.org/api/option"
)

type eraseTestTransport func(*http.Request) (*http.Response, error)

func (f eraseTestTransport) RoundTrip(r *http.Request) (*http.Response, error) {
	return f(r)
}

func TestAuthorizeEraseValidatesSignedWorkloadIdentity(t *testing.T) {
	t.Parallel()
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	encode := base64.RawURLEncoding.EncodeToString
	certs, err := json.Marshal(map[string]any{"keys": []map[string]string{{
		"kid": "test-key", "kty": "RSA", "alg": "RS256",
		"n": encode(key.N.Bytes()), "e": encode(big.NewInt(int64(key.E)).Bytes()),
	}}})
	if err != nil {
		t.Fatal(err)
	}
	client := &http.Client{Transport: eraseTestTransport(func(r *http.Request) (*http.Response, error) {
		if r.URL.String() != "https://www.googleapis.com/oauth2/v3/certs" {
			t.Errorf("unexpected validation URL %s", r.URL)
		}
		return &http.Response{
			StatusCode: http.StatusOK,
			Header:     http.Header{"Cache-Control": {"max-age=300"}},
			Body:       io.NopCloser(strings.NewReader(string(certs))),
		}, nil
	})}
	validator, err := idtoken.NewValidator(t.Context(), option.WithHTTPClient(client))
	if err != nil {
		t.Fatal(err)
	}
	const audience, subject = "synthetic-erase-audience", "123456789012345678901"
	authorize := authorizeErase(validator, eraseConfig{audience: audience, subject: subject})
	for _, tc := range []struct {
		name, aud, issuer, sub string
		accepted               bool
	}{
		{"Google workload", audience, "https://accounts.google.com", subject, true},
		{"Google issuer alias", audience, "accounts.google.com", subject, true},
		{"wrong audience", "other", "https://accounts.google.com", subject, false},
		{"wrong issuer", audience, "https://example.invalid", subject, false},
		{"wrong subject", audience, "https://accounts.google.com", "123", false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			payload, err := json.Marshal(map[string]any{
				"aud": tc.aud, "iss": tc.issuer, "sub": tc.sub, "exp": time.Now().Add(time.Minute).Unix(),
			})
			if err != nil {
				t.Fatal(err)
			}
			signed := encode([]byte(`{"alg":"RS256","kid":"test-key"}`)) + "." + encode(payload)
			digest := sha256.Sum256([]byte(signed))
			sig, err := rsa.SignPKCS1v15(rand.Reader, key, crypto.SHA256, digest[:])
			if err != nil {
				t.Fatal(err)
			}
			err = authorize(t.Context(), signed+"."+encode(sig))
			if (err == nil) != tc.accepted {
				t.Fatalf("authorize result = %v, accepted want %t", err, tc.accepted)
			}
		})
	}
}
