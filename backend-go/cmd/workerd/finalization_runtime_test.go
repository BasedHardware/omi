package main

import (
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
)

func TestWorkerdLeavesFinalizationUnclaimedWithoutServingPorts(t *testing.T) {
	t.Parallel()
	kinds := workerdKinds()
	if len(kinds) != 1 || kinds[0].Name != finalization.Kind || len(workerdHandlers(&finalization.Service{})) != 0 {
		t.Fatal("workerd did not separate declaration from a complete handler")
	}
	cfg, err := readConfig(envLookup(fixtureEnv()), false)
	if err != nil || cfg.summaryRepair {
		t.Fatalf("default summary setting: %v %v", cfg.summaryRepair, err)
	}
	env := fixtureEnv()
	env["WORKER_SUMMARY_REPAIR_ENABLED"], env["ENRICHMENT_MAX_AGE_HOURS"] = "true", "1.5"
	cfg, err = readConfig(envLookup(env), false)
	if err != nil || !cfg.summaryRepair || cfg.summaryMaxAge != 90*time.Minute {
		t.Fatalf("opt-in summary setting: %v %v %v", cfg.summaryRepair, cfg.summaryMaxAge, err)
	}
}

func TestWorkerdValidatesArchiveAndRetractionComposition(t *testing.T) {
	t.Parallel()
	env := fixtureEnv()
	env["BUCKET_AUDIO_DERIVED"] = "regional-fixture"
	if _, err := readConfig(envLookup(env), false); err == nil {
		t.Fatal("derived archive accepted a missing private bucket")
	}
	env["BUCKET_PRIVATE_CLOUD_SYNC"] = "private-fixture"
	env["WORKER_MERGE_RETRACTION_ORIGIN"] = "https://backend.fixture.test"
	if _, err := readConfig(envLookup(env), false); err == nil {
		t.Fatal("retraction accepted a missing OIDC audience")
	}
	env["LISTEN_FINALIZATION_TASKS_HANDLER_URL"] = "https://backend.fixture.test/v1/conversation-finalization-jobs/run"
	cfg, err := readConfig(envLookup(env), false)
	if err != nil || cfg.privateArchive != "private-fixture" || cfg.derivedArchive != "regional-fixture" ||
		cfg.retractionAudience != env["LISTEN_FINALIZATION_TASKS_HANDLER_URL"] {
		t.Fatalf("adapter config: %v", err)
	}
	env["WORKER_MERGE_RETRACTION_ORIGIN"] = "http://backend.fixture.test"
	if _, insecureErr := readConfig(envLookup(env), false); insecureErr == nil {
		t.Fatal("retraction accepted a plaintext origin")
	}
}

func TestQuietRecoveryRequiresCompleteRuntime(t *testing.T) {
	t.Parallel()
	env := fixtureEnv()
	env["WORKER_QUIET_RECOVERY_ENABLED"] = "invalid"
	if _, err := readConfig(envLookup(env), false); err == nil {
		t.Fatal("quiet recovery accepted invalid boolean")
	}
	env["WORKER_QUIET_RECOVERY_ENABLED"] = "true"
	if _, err := readConfig(envLookup(env), false); err == nil {
		t.Fatal("quiet recovery accepted a missing private bucket")
	}
	env["BUCKET_PRIVATE_CLOUD_SYNC"] = "private-fixture"
	cfg, err := readConfig(envLookup(env), false)
	if err != nil || !cfg.quietRecovery {
		t.Fatalf("quiet recovery opt-in: %v %v", cfg.quietRecovery, err)
	}
	runtime := finalizationRuntime{family: &finalization.Service{}}
	if err := runtime.registerQuietRecovery(false, true, clock.System{}); err != nil || runtime.quiet != nil {
		t.Fatalf("disabled quiet recovery: %v", err)
	}
	if err := runtime.registerQuietRecovery(cfg.quietRecovery, true, clock.System{}); err == nil || runtime.quiet != nil {
		t.Fatal("quiet recovery accepted an incomplete handler")
	}
}

func TestNotesDedupeMatchesPythonKillSwitch(t *testing.T) {
	t.Parallel()
	for _, tc := range []struct {
		value *string
		want  bool
	}{
		{nil, true},
		{new(""), true},
		{new("true"), true},
		{new("on"), true},
		{new("yes"), true},
		{new("1"), true},
		{new("unknown"), true},
		{new(" 0 "), false},
		{new(" FALSE "), false},
		{new("Off"), false},
		{new(" no "), false},
	} {
		env := fixtureEnv()
		if tc.value != nil {
			env["CONVERSATION_LLM_INPUT_DEDUPE_ENABLED"] = *tc.value
		}
		cfg, err := readConfig(envLookup(env), false)
		if err != nil || cfg.notesDedupe != tc.want {
			t.Errorf("notes dedupe for %q = %t, want %t: %v", env["CONVERSATION_LLM_INPUT_DEDUPE_ENABLED"], cfg.notesDedupe, tc.want, err)
		}
	}
}
