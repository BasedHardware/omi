package queue

import (
	"testing"

	"github.com/BasedHardware/omi/backend-go/internal/platform/clock"
	"github.com/BasedHardware/omi/backend-go/internal/platform/pgtest"
)

func TestEntitlementMigrationFromPopulated003(t *testing.T) {
	t.Parallel()
	ctx := t.Context()
	s, err := Open(ctx, pgtest.New(t), testConfig(), testKinds(), nil, clock.System{})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(s.Close)
	files, err := embedded()
	if err != nil {
		t.Fatal(err)
	}
	if len(files) < 4 || files[2].name != "003_erase_tenant.sql" || files[3].name != "004_entitlement.sql" {
		t.Fatal("expected 003 to 004 upgrade")
	}
	if setupErr := s.migrate(ctx, files[:3]); setupErr != nil {
		t.Fatal(setupErr)
	}
	// A 003 Hold uses check_after on the tenant and a waiting job with a timer.
	_, err = s.pool.Exec(ctx, `INSERT INTO queue_tenants(uid,check_after) VALUES ('owner','2099-01-01');
 INSERT INTO queue_lanes(uid,kind,order_key) VALUES ('owner','demo','lane');
 INSERT INTO queue_jobs(job_key,uid,kind,format,subject,meta,order_at,order_sub_us,order_sort,
                        state,step,run_at,order_key,ready_at,outcome)
 SELECT k,'owner','demo',1,k,'{}','2026-01-01',0,k,state,'start','2026-01-01',lane,due::timestamptz,result
 FROM (VALUES
 ('held','waiting',NULL,'2099-01-01',NULL),
 ('ordered','ready','lane','2026-01-01',NULL),
 ('completed','completed',NULL,NULL,'success')) AS seed(k,state,lane,due,result)`)
	if err != nil {
		t.Fatal(err)
	}
	// Compare all preexisting fields, including the owner's timer and lane membership.
	const snapshot = `SELECT jsonb_build_object('owner',
 (SELECT to_jsonb(t)-'entitlement_generation'-'entitlement_check_at' FROM queue_tenants t),
 'lanes',(SELECT jsonb_agg(l) FROM queue_lanes l),
 'jobs',(SELECT jsonb_agg(to_jsonb(j)-'custody_deadline'-'held_order_key'-'audio_seconds'-'owed_since'
 -'timed_deadline'-'timed_generation' ORDER BY job_key) FROM queue_jobs j))::text`
	var before, after string
	if err = s.pool.QueryRow(ctx, snapshot).Scan(&before); err != nil {
		t.Fatal(err)
	}
	if err = s.migrate(ctx, files[:4]); err != nil {
		t.Fatal(err)
	}
	if err = s.pool.QueryRow(ctx, snapshot).Scan(&after); err != nil || after != before {
		t.Fatalf("004 changed existing queue data: %v", err)
	}
	if err = s.Migrate(ctx); err != nil {
		t.Fatal(err)
	}
	if err = s.Ready(ctx); err != nil {
		t.Fatal(err)
	}
}
