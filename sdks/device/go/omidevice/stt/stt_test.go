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
		{
			name:       "replace percent-encoded sample rate key",
			apiURL:     "https://parakeet.example/gateway?%73ample_rate=8000&token=a%26b",
			sampleRate: 16000,
			want:       "wss://parakeet.example/gateway/v3/stream?sample_rate=16000&token=a%26b",
		},
		{
			name:       "replace encoded underscore and valueless rate",
			apiURL:     "https://parakeet.example?region=eu&sample%5Frate",
			sampleRate: 8000,
			want:       "wss://parakeet.example/v3/stream?region=eu&sample_rate=8000",
		},
		{
			name:       "collapse mixed duplicate rate keys",
			apiURL:     "https://parakeet.example?%73ample_rate=8000&token=a%2Fb&sample_rate=48000",
			sampleRate: 16000,
			want:       "wss://parakeet.example/v3/stream?sample_rate=16000&token=a%2Fb",
		},
		{
			name:       "decode keys only once",
			apiURL:     "https://parakeet.example?%2573ample_rate=8000&token=a+b",
			sampleRate: 16000,
			want:       "wss://parakeet.example/v3/stream?%2573ample_rate=8000&token=a+b&sample_rate=16000",
		},
		{
			name:       "preserve unrelated malformed escape",
			apiURL:     "https://parakeet.example?tenant%ZZ=demo&sample_rate=8000",
			sampleRate: 16000,
			want:       "wss://parakeet.example/v3/stream?tenant%ZZ=demo&sample_rate=16000",
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
