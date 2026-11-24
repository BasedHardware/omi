package main

import (
	"strings"
	"testing"
	"time"
)

func TestEntitlementReleaseBucketsCoverShadowTargets(t *testing.T) {
	t.Parallel()
	m := &metrics{counters: make(map[string]uint64), histograms: make(map[string]histogram)}
	m.declare(nil)
	m.EntitlementReleased(50 * time.Minute)

	var output strings.Builder
	m.write(&output)
	for _, bucket := range []string{
		`jobd_entitlement_release_seconds_bucket{le="60"} 0`,
		`jobd_entitlement_release_seconds_bucket{le="2700"} 0`,
		`jobd_entitlement_release_seconds_bucket{le="3600"} 1`,
		`jobd_entitlement_release_seconds_bucket{le="3900"} 1`,
		`jobd_entitlement_release_seconds_bucket{le="+Inf"} 1`,
	} {
		if !strings.Contains(output.String(), bucket+"\n") {
			t.Errorf("missing bucket sample %q", bucket)
		}
	}
}
