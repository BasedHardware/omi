# Configurable vendor overflow priorities

Vendor overflow defaults to FRESH only. `BATCH_VENDOR_OVERFLOW_PRIORITIES=fresh,recent` additionally
allows RECENT English admissions to choose the vendor table when the RECENT GPU backlog is saturated.
The samplers keep independent cache, refresh, in-flight and hysteresis state; failures retain GPU routing.
The two saturation gauges now identify one of three bounded priorities.

[Environment contract](../../listen_pusher_pipeline.mdx#batch-vendor-overflow-priorities).
The overflow kill switch, routing cohort, GPU floor and FRESH-only legacy capacity fallback still apply.
No production overlay is changed. Expansion is a separate spend decision owned by the parent task.
Regression coverage: `backend/tests/unit/test_batch_vendor_overflow.py`; flag registrations are checked
by the flag-budget, feature-registry and deployment-setting contract suites.
