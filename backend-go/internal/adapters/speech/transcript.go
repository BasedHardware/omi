package speech

import (
	"encoding/json"
	"errors"
	"fmt"
	"strings"
)

type vendorReply struct {
	Text       json.RawMessage    `json:"text"`
	Duration   json.RawMessage    `json:"duration_ms"`
	Utterances []*vendorUtterance `json:"utterances"`
}

type vendorUtterance struct {
	Text     string          `json:"text"`
	Start    float64         `json:"start_ms"`
	Duration float64         `json:"duration_ms"`
	Speaker  json.RawMessage `json:"speaker"`
	Language string          `json:"language"`
}

type languageVote struct {
	words    int
	duration float64
}

var errInvalidReply = errors.New("speech: invalid Modulate reply")

func parseReply(body []byte, fallback string) (Transcript, error) {
	var raw vendorReply
	if json.Unmarshal(body, &raw) != nil || raw.Utterances == nil {
		return Transcript{}, errInvalidReply
	}
	out := Transcript{Utterances: make([]Utterance, 0, len(raw.Utterances))}
	hasLong := false
	speakerFallback := false
	for _, utt := range raw.Utterances {
		if utt == nil {
			return Transcript{}, errInvalidReply
		}
		text := strings.TrimSpace(utt.Text)
		if text == "" {
			continue
		}
		var speaker int
		if json.Unmarshal(utt.Speaker, &speaker) != nil || speaker < 1 {
			speakerFallback = true
			speaker = 1
		}
		out.Utterances = append(out.Utterances, Utterance{
			Text: text, Start: utt.Start / 1000, End: (utt.Start + utt.Duration) / 1000,
			Speaker: fmt.Sprintf("SPEAKER_%02d", speaker-1),
		})
		hasLong = hasLong || len(strings.Fields(text)) >= 3
	}
	if len(out.Utterances) == 0 && !raw.validSilence() {
		return Transcript{}, errInvalidReply
	}
	for index := range out.Utterances {
		out.Utterances[index].SpeakerFallback = speakerFallback
	}
	out.Language = detectLanguage(raw.Utterances, hasLong, fallback)
	return out, nil
}

func (raw vendorReply) validSilence() bool {
	var text *string
	if json.Unmarshal(raw.Text, &text) == nil && text != nil {
		return strings.TrimSpace(*text) == ""
	}
	if len(raw.Utterances) > 0 {
		return true
	}
	// The JSON object already parsed, so the first byte identifies numeric values
	// without accepting quoted numbers or requiring conversion to float64.
	return len(raw.Duration) > 0 &&
		(raw.Duration[0] == '-' || (raw.Duration[0] >= '0' && raw.Duration[0] <= '9'))
}

func detectLanguage(utterances []*vendorUtterance, hasLong bool, fallback string) string {
	totals := make(map[string]languageVote)
	order := make([]string, 0)
	for _, utt := range utterances {
		words := len(strings.Fields(utt.Text))
		lang, _, _ := strings.Cut(strings.ToLower(utt.Language), "-")
		lang, _, _ = strings.Cut(lang, "_")
		if lang == "" || words == 0 || (hasLong && words < 3) {
			continue
		}
		vote, found := totals[lang]
		if !found {
			order = append(order, lang)
		}
		totals[lang] = languageVote{words: vote.words + words, duration: vote.duration + max(0, utt.Duration)}
	}
	best := languageVote{}
	winner := fallback
	if winner == "" {
		winner = "multi"
	}
	for _, lang := range order {
		vote := totals[lang]
		if vote.words > best.words || (vote.words == best.words && vote.duration > best.duration) {
			best, winner = vote, lang
		}
	}
	return winner
}
