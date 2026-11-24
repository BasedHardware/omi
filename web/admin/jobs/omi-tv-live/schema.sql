-- One row per UTC day of metered live cost (wall-live-bq.ts). Created once by a
-- human with dataset dataEditor; the job only inserts, deletes its own days and
-- prunes rows older than 14 days.
CREATE TABLE IF NOT EXISTS `based-hardware.omi_tv.live_day` (
  day DATE NOT NULL,
  produced_at TIMESTAMP NOT NULL,
  run_at TIMESTAMP NOT NULL,
  query_end TIMESTAMP NOT NULL,
  fraction FLOAT64 NOT NULL,
  cloud_run_usd FLOAT64 NOT NULL,
  firestore_usd FLOAT64 NOT NULL,
  gcs_usd FLOAT64 NOT NULL,
  logging_usd FLOAT64 NOT NULL,
  estimated_services STRING
);
