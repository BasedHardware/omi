-- Human applies once, after confirming the US location alongside omi_finops.
CREATE SCHEMA IF NOT EXISTS `based-hardware.omi_tv` OPTIONS(location='US', description='Omi TV keyed person-day features; admin returns counts only');
CREATE TABLE IF NOT EXISTS `based-hardware.omi_tv.person_day` (
  day DATE NOT NULL, definition STRING NOT NULL, key_id STRING NOT NULL,
  actor STRING NOT NULL, row_key STRING NOT NULL, kind STRING NOT NULL, p STRING NOT NULL,
  anchor TIMESTAMP, first_at TIMESTAMP NOT NULL, latest TIMESTAMP NOT NULL,
  activity_day DATE NOT NULL, age_day INT64 NOT NULL, saved BOOL NOT NULL,
  family STRING NOT NULL, phone BOOL NOT NULL, mac BOOL NOT NULL, n INT64 NOT NULL
) PARTITION BY day CLUSTER BY kind, actor OPTIONS(require_partition_filter=true);
CREATE TABLE IF NOT EXISTS `based-hardware.omi_tv.coverage` (
  day DATE NOT NULL, definition STRING NOT NULL, key_id STRING NOT NULL,
  refreshed_at TIMESTAMP NOT NULL, loaded_at TIMESTAMP NOT NULL, feature_rows INT64 NOT NULL,
  pages INT64 NOT NULL
) PARTITION BY day OPTIONS(require_partition_filter=true);
