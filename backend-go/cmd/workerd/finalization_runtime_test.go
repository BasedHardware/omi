package main

import (
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
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
	env["WORKER_MERGE_RETRACTION_ORIGIN"] = "https://backend.fixture.test"
	if _, err := readConfig(envLookup(env), false); err == nil {
		t.Fatal("retraction accepted a missing OIDC audience")
	}
	env["LISTEN_FINALIZATION_TASKS_HANDLER_URL"] = "https://backend.fixture.test/v1/conversation-finalization-jobs/run"
	cfg, err := readConfig(envLookup(env), false)
	if err != nil || cfg.privateArchive != "omi-private-cloud-sync" || cfg.derivedArchive != "regional-fixture" ||
		cfg.retractionAudience != env["LISTEN_FINALIZATION_TASKS_HANDLER_URL"] {
		t.Fatalf("adapter config: %v", err)
	}
	env["WORKER_MERGE_RETRACTION_ORIGIN"] = "http://backend.fixture.test"
	if _, insecureErr := readConfig(envLookup(env), false); insecureErr == nil {
		t.Fatal("retraction accepted a plaintext origin")
	}
}
