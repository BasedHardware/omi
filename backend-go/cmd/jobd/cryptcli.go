package main

import (
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"io"
	"strings"

	"github.com/BasedHardware/omi/backend-go/internal/platform/crypt"
)

var errArgument = errors.New("invalid_request")

const maxCLIInput = 64 << 20

// cryptCLI is the conformance kit's command-line view of the codec.
//
// CLEANUP-NOTE: remove with the kit's vector commands once real adapters replace the stub.
func cryptCLI(c crypt.Codec, args []string, stdin io.Reader, stdout io.Writer) error {
	if len(args) == 0 {
		return errArgument
	}
	flags := flag.NewFlagSet(args[0], flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	uid := flags.String("uid", "", "tenant")
	// CLEANUP-NOTE: Remove the CLI nonce override after retiring the kit vectors.
	nonceText := flags.String("nonce", "", "test nonce")
	format := flags.String("format", "", "transcript format")
	if flags.Parse(args[1:]) != nil || flags.NArg() != 0 || *uid == "" {
		return errArgument
	}
	var nonce []byte
	nonceSet := false
	flags.Visit(func(f *flag.Flag) {
		if f.Name == "nonce" {
			nonceSet = true
		}
	})
	if nonceSet {
		var err error
		nonce, err = hex.DecodeString(*nonceText)
		if err != nil || len(nonce) != 12 || strings.ToLower(*nonceText) != *nonceText {
			return errArgument
		}
		switch args[0] {
		case "encrypt", "encode-transcript":
		default:
			return errArgument
		}
	}
	in, err := io.ReadAll(io.LimitReader(stdin, maxCLIInput+1))
	if err != nil || len(in) > maxCLIInput {
		return crypt.ErrUnreadable
	}
	var output []byte
	switch args[0] {
	case "encrypt":
		var sealed string
		sealed, err = c.SealWithNonce(*uid, in, nonce)
		output = []byte(sealed)
	case "decrypt":
		output, err = c.Open(*uid, string(in))
	case "decode-transcript":
		var t crypt.Transcript
		if json.Unmarshal(in, &t) != nil {
			return crypt.ErrUnreadable
		}
		var list []json.RawMessage
		list, err = c.Decode(*uid, t)
		if err == nil {
			output, err = json.Marshal(list)
		}
	case "encode-transcript":
		var t crypt.Transcript
		t, err = c.Encode(*uid, crypt.Format(*format), in, nonce)
		if err == nil {
			output, err = json.Marshal(t)
		}
	default:
		return errArgument
	}
	if err != nil {
		return crypt.ErrUnreadable
	}
	_, err = stdout.Write(output)
	return err
}
