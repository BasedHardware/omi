// Package pgtest gives each test its own empty Postgres database.
//
// Tests that share one database delete each other's rows and block on each other's advisory
// locks, across packages and across worktrees on one machine. A database per test removes
// both, so database tests can run in parallel and two agents can run them at once.
package pgtest

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"net/url"
	"os"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
)

const (
	// URLEnv names the variable holding the URL of a Postgres 16 server the tests may
	// create databases on.
	URLEnv = "TEST_DATABASE_URL"
	// RequiredEnv names the variable that, when set to 1, turns a missing URLEnv from a skip
	// into a failure. CI and `make check` set it, so a run with no database can never pass
	// as green.
	RequiredEnv = "TEST_DATABASE_REQUIRED"

	setupLimit = 30 * time.Second
)

// New creates an empty database and returns its URL. The database is dropped when the test
// ends. Without URLEnv the test is skipped, or fails when RequiredEnv is 1.
func New(tb testing.TB) string {
	tb.Helper()
	admin := os.Getenv(URLEnv)
	if admin == "" {
		if os.Getenv(RequiredEnv) == "1" {
			tb.Fatalf("%s is not set and %s=1: this run must not skip database tests", URLEnv, RequiredEnv)
		}
		tb.Skipf("set %s to a disposable Postgres 16 server (see `make check`)", URLEnv)
	}
	parsed, err := url.Parse(admin)
	if err != nil {
		tb.Fatalf("parse %s: %v", URLEnv, err)
	}
	suffix := make([]byte, 8)
	if _, err := rand.Read(suffix); err != nil {
		tb.Fatal(err)
	}
	name := "t_" + hex.EncodeToString(suffix)
	exec(tb, admin, "CREATE DATABASE "+name)
	tb.Cleanup(func() { exec(tb, admin, "DROP DATABASE IF EXISTS "+name+" WITH (FORCE)") })
	parsed.Path = "/" + name
	return parsed.String()
}

// exec runs one statement on the admin connection. name is generated here from hex digits,
// so the statement text holds no outside input.
func exec(tb testing.TB, admin, statement string) {
	tb.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), setupLimit)
	defer cancel()
	conn, err := pgx.Connect(ctx, admin)
	if err != nil {
		tb.Fatalf("connect to %s: %v", URLEnv, err)
	}
	defer func() {
		if err := conn.Close(ctx); err != nil {
			tb.Errorf("close admin connection: %v", err)
		}
	}()
	if _, err := conn.Exec(ctx, statement); err != nil {
		tb.Fatalf("%s: %v", statement, err)
	}
}
