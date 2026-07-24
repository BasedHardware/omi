package stt

import "testing"

func TestParakeetWSURL(t *testing.T) {
	got := ParakeetWSURL("https://parakeet.example/", 16000)
	want := "wss://parakeet.example/v3/stream?sample_rate=16000"
	if got != want {
		t.Fatalf("got %s want %s", got, want)
	}
}

func TestWhisperRequiresRunner(t *testing.T) {
	if _, err := NewWhisper(nil, nil); err == nil {
		t.Fatal("expected error")
	}
}
