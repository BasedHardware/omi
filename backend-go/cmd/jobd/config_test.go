package main

import "testing"

func TestConditionHoldSwitch(t *testing.T) {
	const flag = "GO_BATCH_ENTITLEMENT_CONDITION_HOLD"
	for _, tc := range []struct {
		value string
		timed bool
	}{{"true", false}, {"false", true}} {
		t.Setenv(flag, tc.value)
		cfg, err := loadConfig()
		if err != nil || cfg.TimeOnlyEntitlementHold != tc.timed {
			t.Fatalf("%s=%s: timed=%v, err=%v", flag, tc.value, cfg.TimeOnlyEntitlementHold, err)
		}
	}
	t.Setenv(flag, "invalid")
	if _, err := loadConfig(); err == nil {
		t.Fatal("invalid switch must fail startup")
	}
}
