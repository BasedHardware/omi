package finalization

import (
	"regexp"
	"strings"
)

// These rules mirror the title portion of Python's summary_quality policy.
var (
	titlePlaceholder = regexp.MustCompile(`(?i)^(?:[-—–….*\s]+|(?:new|unknown) moment.*|untitled|none|null|in progress|processing[.…]*|transcribing[.…]*|writing notes[.…]*|conversation|talking|discussion notes|discussion \d+)$`)
	titleNarration   = regexp.MustCompile(`(?i)\b(?:(?:a |the )?(?:speaker discusses|conversation covers)|episode notes.*continue)\b`)
	titleBoundary    = regexp.MustCompile(`\n|[.!?][\t\r\f ]+[A-Z]|[。！？]`)
	titleMechanics   = regexp.MustCompile(`(?i)\b(?:missing from (?:the )?transcript(?:[.!?]|$)|` +
		`(?:not|never) (?:in|captured in|present in) (?:the )?transcript(?:[.!?]|$)|` +
		`^(?:(?:the |this |our )?transcript (?:is |was |remains )?(?:missing|unavailable|incomplete|empty)|missing transcript)[.!]?$|` +
		`^(?:this |the |our )?(?:audio|capture|recording|transcription) (?:is |was |remains )?(?:missing|unavailable|pending|incomplete)[.!]?$|` +
		`(?:audio gaps?|pipeline failures?) (?:prevent|preclude) (?:a |the )?(?:recap|summary|notes)\b|` +
		`^(?:still|awaiting|pending|finishing) (?:processing|transcription) (?:the |this |our )?(?:recording|capture|audio|transcript)[.!]?$|` +
		`(?:no|insufficient|without) (?:usable )?(?:transcript|audio|recording) (?:evidence |content )?(?:is available|to (?:summarize|recap)|for (?:a |the )?(?:summary|recap)))`)
	titleJapaneseMechanics = regexp.MustCompile(`(?:文字起こし|書き起こし|録音|音声)(?:が|は)(?:ない|無い|ありません|不足|利用でき|存在しない)[^。！？\n]{0,45}(?:要約でき|まとめられ|内容を確認でき)|` +
		`^(?:文字起こし|書き起こし|録音|音声)(?:が|は)(?:ありません|利用できません|欠落しています)[。！]?$`)
)

func validSyncTitle(value string) string {
	value = strings.TrimSpace(value)
	if titleNarration.MatchString(value) {
		return ""
	}
	start := 0
	for _, match := range titleBoundary.FindAllStringIndex(value, -1) {
		end, next := match[1], match[1]
		if strings.ContainsRune(".!?", rune(value[match[0]])) {
			end, next = match[0]+1, match[1]-1
		}
		if unavailableTitle(value[start:end]) {
			return ""
		}
		start = next
	}
	if unavailableTitle(value[start:]) {
		return ""
	}
	title := strings.Join(strings.Fields(value), " ")
	if titlePlaceholder.MatchString(title) {
		return ""
	}
	return title
}

func unavailableTitle(part string) bool {
	part = strings.TrimLeft(strings.TrimSpace(part), "-*• ")
	return titleMechanics.MatchString(part) || titleJapaneseMechanics.MatchString(part)
}

func stabilizeSyncTitle(notes *Notes, source *SyncSourceProjection) {
	evidence := source.TitleEvidence
	if evidence == nil || notes.Minimum != nil && notes.Minimum.Discarded {
		return
	}
	proposed := validSyncTitle(notes.Title)
	growth := float64(source.ContentUnits) - evidence.PreviousUnits
	material := evidence.PreviousUnits > 0 && growth >= 20 && growth >= 0.4*float64(source.ContentUnits)
	title := evidence.ValidPrior
	switch {
	case title == "" && proposed == "":
		title = "Discussion notes"
	case title == "" || material && proposed != "":
		title = proposed
	}
	reason := ""
	if title != evidence.Prior {
		switch {
		case evidence.ValidPrior != "":
			reason = "material_content_growth"
		case evidence.Prior == "":
			reason = "initial_title"
		default:
			reason = "invalid_title_repaired"
		}
	}
	notes.Title = title
	notes.TitleUpdate = &SyncTitleUpdate{
		SetBasis: (source.ContentUnits != 0 || evidence.PreviousUnits != 0) && (reason != "" || evidence.PreviousUnits <= 0),
		Basis:    source.ContentUnits,
		Reason:   reason,
	}
}
