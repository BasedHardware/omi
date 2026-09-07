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
