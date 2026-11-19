package queue

import (
	"context"
	"crypto/sha256"
	"embed"
	"encoding/hex"
	"errors"
	"fmt"

	"github.com/jackc/pgx/v5"

	"github.com/BasedHardware/omi/backend-go/internal/platform/pg"
)

//go:embed migrations/*.sql
var migrations embed.FS

const migrationLock = 6617271580795099302

// ErrSchema means the database's schema is not the one this binary was built for.
var ErrSchema = errors.New("queue: schema mismatch")

type migration struct {
	name     string
	checksum string
	sql      string
}

func embedded() ([]migration, error) {
	files, err := migrations.ReadDir("migrations")
	if err != nil {
		return nil, fmt.Errorf("read migrations: %w", err)
	}
	out := make([]migration, 0, len(files))
	for _, file := range files {
		sql, err := migrations.ReadFile("migrations/" + file.Name())
		if err != nil {
			return nil, fmt.Errorf("read %s: %w", file.Name(), err)
		}
		sum := sha256.Sum256(sql)
		out = append(out, migration{name: file.Name(), checksum: hex.EncodeToString(sum[:]), sql: string(sql)})
	}
	return out, nil
}

// Migrate applies the embedded SQL files that are not yet recorded, under one lock, in one
// transaction, and records each with its checksum. It is safe to run from several replicas
// at once. It refuses a database where an applied file differs from the embedded one: an
// applied migration is never edited, a change is a new file.
func (s *Store) Migrate(ctx context.Context) error {
	files, err := embedded()
	if err != nil {
		return err
	}
	return pg.InTx(ctx, s.pool, func(tx pgx.Tx) error {
		if _, err := tx.Exec(ctx, "SELECT pg_advisory_xact_lock($1)", int64(migrationLock)); err != nil {
			return fmt.Errorf("migration lock: %w", err)
		}
		_, err := tx.Exec(ctx,
			"CREATE TABLE IF NOT EXISTS queue_schema (version text PRIMARY KEY, checksum text NOT NULL)")
		if err != nil {
			return fmt.Errorf("schema table: %w", err)
		}
		for _, file := range files {
			if err := applyMigration(ctx, tx, file); err != nil {
				return err
			}
		}
		return nil
	})
}

func applyMigration(ctx context.Context, tx pgx.Tx, file migration) error {
	var recorded string
	err := tx.QueryRow(ctx, "SELECT checksum FROM queue_schema WHERE version=$1", file.name).Scan(&recorded)
	switch {
	case isNoRows(err):
	case err != nil:
		return fmt.Errorf("check %s: %w", file.name, err)
	case recorded != file.checksum:
		return fmt.Errorf("%w: %s was applied with different contents", ErrSchema, file.name)
	default:
		return nil
	}
	if _, applyErr := tx.Exec(ctx, file.sql); applyErr != nil {
		return fmt.Errorf("apply %s: %w", file.name, applyErr)
	}
	_, err = tx.Exec(ctx, "INSERT INTO queue_schema(version,checksum) VALUES ($1,$2)", file.name, file.checksum)
	if err != nil {
		return fmt.Errorf("record %s: %w", file.name, err)
	}
	return nil
}

// Ready reports whether the database has exactly the migrations embedded in this binary,
// with the same contents. A newer database (more files) is accepted: an old replica keeps
// working through a rolling deployment because migrations only add.
func (s *Store) Ready(ctx context.Context) error {
	files, err := embedded()
	if err != nil {
		return err
	}
	rows, err := s.pool.Query(ctx, "SELECT version,checksum FROM queue_schema")
	if err != nil {
		return fmt.Errorf("read schema versions: %w", err)
	}
	applied := map[string]string{}
	var version, checksum string
	_, err = pgx.ForEachRow(rows, []any{&version, &checksum}, func() error {
		applied[version] = checksum
		return nil
	})
	if err != nil {
		return fmt.Errorf("read schema versions: %w", err)
	}
	for _, file := range files {
		switch recorded, ok := applied[file.name]; {
		case !ok:
			return fmt.Errorf("%w: %s is not applied; run Migrate before starting workers", ErrSchema, file.name)
		case recorded != file.checksum:
			return fmt.Errorf("%w: %s was applied with different contents", ErrSchema, file.name)
		}
	}
	return nil
}

func isNoRows(err error) bool { return errors.Is(err, pgx.ErrNoRows) }
