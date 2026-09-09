package stt

import "testing"

func TestParakeetWSURL(t *testing.T) {
	tests := []struct {
		name       string
		apiURL     string
		sampleRate int
		want       string
	}{
		{
			name:       "trailing slash",
			apiURL:     "https://parakeet.example/",
			sampleRate: 16000,
			want:       "wss://parakeet.example/v3/stream?sample_rate=16000",
		},
		{
			name:       "http to ws",
			apiURL:     "http://parakeet.example:8080",
			sampleRate: 16000,
			want:       "ws://parakeet.example:8080/v3/stream?sample_rate=16000",
		},
		{
			name:       "preserve query and path",
			apiURL:     "https://parakeet.example/gateway?region=eu",
			sampleRate: 16000,
			want:       "wss://parakeet.example/gateway/v3/stream?region=eu&sample_rate=16000",
		},
		{
			name:       "strip trailing slash from path",
			apiURL:     "https://parakeet.example/gateway/",
			sampleRate: 16000,
			want:       "wss://parakeet.example/gateway/v3/stream?sample_rate=16000",
		},
		{
			name:       "remove fragment",
			apiURL:     "https://parakeet.example/gateway?region=eu#debug",
			sampleRate: 8000,
			want:       "wss://parakeet.example/gateway/v3/stream?region=eu&sample_rate=8000",
		},
		{
			name:       "schemeless with query containing protocol",
			apiURL:     "parakeet.example/gateway?redirect=https://other.example",
			sampleRate: 16000,
			want:       "wss://parakeet.example/gateway/v3/stream?redirect=https://other.example&sample_rate=16000",
		},
		{
			name:       "preserve percent-escaped path and query",
			apiURL:     "https://parakeet.example/gateway%2Fv1?region=eu%20zone",
			sampleRate: 16000,
			want:       "wss://parakeet.example/gateway%2Fv1/v3/stream?region=eu%20zone&sample_rate=16000",
		},
		{
			name:       "replace sample_rate and strip fragment",
			apiURL:     "https://parakeet.example/gateway?sample_rate=8000&token=abc#frag",
			sampleRate: 16000,
			want:       "wss://parakeet.example/gateway/v3/stream?sample_rate=16000&token=abc",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got := ParakeetWSURL(tc.apiURL, tc.sampleRate)
			if got != tc.want {
				t.Fatalf("ParakeetWSURL(%q, %d) = %q, want %q", tc.apiURL, tc.sampleRate, got, tc.want)
			}
		})
	}
}

func TestWhisperRequiresRunner(t *testing.T) {
	if _, err := NewWhisper(nil, nil); err == nil {
		t.Fatal("expected error")
	}
}
