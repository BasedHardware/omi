package stt

import (
	"bytes"
	"errors"
	"testing"
)

func TestWhisperRetriesFailedAudio(t *testing.T) {
	for name, size := range map[string]int{"partial_batch_stop": 32, "full_batch_append": 16000 * 2 * 5} {
		t.Run(name, func(t *testing.T) {
			pcm := bytes.Repeat([]byte{1, 2}, size/2)
			failure := errors.New("temporary runner failure")
			calls := 0
			var transcripts []string
			transcriber, err := NewWhisper(func(chunk []byte) (string, error) {
				calls++
				if !bytes.Equal(chunk, pcm) {
					t.Fatalf("retry lost audio: got %d bytes, want %d", len(chunk), len(pcm))
				}
				if calls <= 2 {
					return "", failure
				}
				return "recovered", nil
			}, func(text string) { transcripts = append(transcripts, text) })
			if err != nil {
				t.Fatal(err)
			}
			err = transcriber.AppendPCM(pcm)
			if size < 16000*2*5 {
				if err != nil {
					t.Fatal(err)
				}
				err = transcriber.Stop()
			}
			if !errors.Is(err, failure) {
				t.Fatalf("first flush: got %v, want runner error", err)
			}
			if err = transcriber.Stop(); !errors.Is(err, failure) {
				t.Fatalf("second flush: got %v, want runner error", err)
			}
			if err = transcriber.Stop(); err != nil {
				t.Fatal(err)
			}
			if calls != 3 || len(transcripts) != 1 || transcripts[0] != "recovered" {
				t.Fatalf("calls=%d transcripts=%v", calls, transcripts)
			}
			if err = transcriber.Stop(); err != nil {
				t.Fatal(err)
			}
			if calls != 3 {
				t.Fatalf("successful audio was transcribed twice: %d calls", calls)
			}
		})
	}
}

func TestWhisperRejectsNewAudioUntilFailedFlushRecovers(t *testing.T) {
	for name, size := range map[string]int{"partial": 32, "full": 16000 * 2 * 5} {
		t.Run(name, func(t *testing.T) {
			original := bytes.Repeat([]byte{1}, size)
			next := []byte{2, 3}
			failure := errors.New("runner unavailable")
			fail := true
			var chunks [][]byte
			transcriber, err := NewWhisper(func(pcm []byte) (string, error) {
				chunks = append(chunks, append([]byte(nil), pcm...))
				if fail {
					return "", failure
				}
				return "", nil
			}, nil)
			if err != nil {
				t.Fatal(err)
			}
			err = transcriber.AppendPCM(original)
			if size < 16000*2*5 {
				if err != nil {
					t.Fatal(err)
				}
				err = transcriber.Stop()
			}
			if !errors.Is(err, failure) {
				t.Fatalf("initial flush: %v", err)
			}
			for i := 0; i < 100; i++ {
				if err := transcriber.AppendPCM(next); !errors.Is(err, ErrWhisperPendingAudio) {
					t.Fatalf("append after failed flush: got %v, want ErrWhisperPendingAudio", err)
				}
			}
			if len(chunks) != 1 {
				t.Fatalf("rejected appends invoked runner: %d calls", len(chunks))
			}
			if err := transcriber.Stop(); !errors.Is(err, failure) {
				t.Fatalf("retry: %v", err)
			}
			fail = false
			if err := transcriber.Stop(); err != nil {
				t.Fatal(err)
			}
			for _, pcm := range chunks {
				if !bytes.Equal(pcm, original) {
					t.Fatalf("retained audio changed: got %d bytes, want %d", len(pcm), size)
				}
			}
			if err := transcriber.AppendPCM(next); err != nil {
				t.Fatal(err)
			}
			if err := transcriber.Stop(); err != nil {
				t.Fatal(err)
			}
			if len(chunks) != 4 || !bytes.Equal(chunks[3], next) {
				t.Fatalf("new audio was not accepted exactly once: %v", chunks[len(chunks)-1])
			}
		})
	}
}
