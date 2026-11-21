-- Sticky enrollment audit (D4/R11): bucket and ramp revision are captured once.
-- Append columns: Space(*row) follows the physical SELECT * column order.
ALTER TABLE spaces ADD COLUMN ramp_bucket float8, ADD COLUMN ramp_revision bigint;
