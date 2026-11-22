package main

import (
	"errors"
	"fmt"
	"math"
	"net"
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/BasedHardware/omi/backend-go/internal/adapters/llmgateway"
	"github.com/BasedHardware/omi/backend-go/internal/platform/crypt"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

const gateAbandoned queue.Cause = "gate_abandoned"

type config struct {
	policy                                     queue.Config
	erase                                      eraseConfig
	gateway                                    llmgateway.Config
	databaseURL                                string
	firestoreProject                           string
	encryptionSecret                           string
	healthPort                                 int
	metricsPort                                int
	stopTimeout                                time.Duration
	quietRecovery                              bool
	summaryRepair                              bool
	notesDedupe                                bool
	summaryMaxAge                              time.Duration
	privateArchive, derivedArchive             string
	objectBucket, objectKMSKey                 string
	retractionOrigin, retractionAudience       string
	episodeIntakeAudience, episodeIntakeCaller string
}

type lookupEnv func(string) (string, bool)

var projectID = regexp.MustCompile(`^[a-z][a-z0-9-]{4,28}[a-z0-9]$`)

func readConfig(lookup lookupEnv, migrate bool) (config, error) {
	database, _ := lookup("DATABASE_URL")
	if !validDatabaseURL(database) {
		return config{}, errors.New("DATABASE_URL must be an explicit PostgreSQL URL with host, user and database")
	}
	cfg := config{databaseURL: database}
	if err := cfg.readPolicy(lookup); err != nil {
		return config{}, err
	}
	if err := cfg.policy.Validate(); err != nil {
		return config{}, err
	}
	if migrate {
		return cfg, nil
	}
	if err := cfg.readWorkerConfig(lookup); err != nil {
		return config{}, err
	}
	if err := cfg.readEraseConfig(lookup); err != nil {
		return config{}, err
	}
	return cfg, nil
}

func (c *config) readWorkerConfig(lookup lookupEnv) error {
	c.firestoreProject, _ = lookup("FIRESTORE_PROJECT")
	c.encryptionSecret, _ = lookup("ENCRYPTION_SECRET")
	if !projectID.MatchString(c.firestoreProject) {
		return errors.New("FIRESTORE_PROJECT must be a Google Cloud project ID")
	}
	if err := crypt.Check(c.encryptionSecret); err != nil {
		return fmt.Errorf("ENCRYPTION_SECRET: %w", err)
	}
	if c.healthPort == c.metricsPort {
		return errors.New("HEALTH_PORT and METRICS_PORT must differ")
	}
	if err := c.readSummaryRepair(lookup); err != nil {
		return err
	}
	c.episodeIntakeAudience, _ = lookup("WORKER_EPISODE_INTAKE_AUDIENCE")
	c.episodeIntakeCaller, _ = lookup("WORKER_EPISODE_INTAKE_CALLER")
	c.episodeIntakeAudience = strings.TrimSpace(c.episodeIntakeAudience)
	c.episodeIntakeCaller = strings.TrimSpace(c.episodeIntakeCaller)
	if (c.episodeIntakeAudience == "") != (c.episodeIntakeCaller == "") ||
		(c.episodeIntakeCaller != "" && !strings.HasSuffix(c.episodeIntakeCaller, ".iam.gserviceaccount.com")) {
		return errors.New("episode intake requires an OIDC audience and service account email")
	}
	if err := c.readFinalizationGateway(lookup); err != nil {
		return err
	}
	return c.readFinalizationAdapters(lookup)
}

func (c *config) readFinalizationAdapters(lookup lookupEnv) error {
	if raw, set := lookup("WORKER_QUIET_RECOVERY_ENABLED"); set {
		enabled, err := strconv.ParseBool(raw)
		if err != nil {
			return errors.New("WORKER_QUIET_RECOVERY_ENABLED must be a boolean")
		}
		c.quietRecovery = enabled
	}
	value, _ := lookup("CONVERSATION_LLM_INPUT_DEDUPE_ENABLED")
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "0", "false", "off", "no":
		c.notesDedupe = false
	default:
		c.notesDedupe = true
	}
	archiveEnabled := false
	if raw, set := lookup("WORKER_FINALIZATION_ARCHIVE_ENABLED"); set {
		enabled, err := strconv.ParseBool(raw)
		if err != nil {
			return errors.New("WORKER_FINALIZATION_ARCHIVE_ENABLED must be a boolean")
		}
		archiveEnabled = enabled
	}
	if archiveEnabled || c.quietRecovery {
		private, _ := lookup("BUCKET_PRIVATE_CLOUD_SYNC")
		derived, _ := lookup("BUCKET_AUDIO_DERIVED")
		c.privateArchive, c.derivedArchive = strings.TrimSpace(private), strings.TrimSpace(derived)
		if c.privateArchive == "" {
			return errors.New("recording archive requires BUCKET_PRIVATE_CLOUD_SYNC")
		}
	}
	if err := c.readObjectLake(lookup); err != nil {
		return err
	}
	raw, set := lookup("WORKER_MERGE_RETRACTION_ENABLED")
	if !set {
		return nil
	}
	enabled, err := strconv.ParseBool(raw)
	if err != nil {
		return errors.New("WORKER_MERGE_RETRACTION_ENABLED must be a boolean")
	}
	if !enabled {
		return nil
	}
	origin, _ := lookup("WORKER_MERGE_RETRACTION_ORIGIN")
	u, err := url.Parse(origin)
	if err != nil || u.Scheme != "https" || u.Hostname() == "" || u.User != nil ||
		u.RawQuery != "" || u.ForceQuery || u.Fragment != "" || (u.Path != "" && u.Path != "/") {
		return errors.New("WORKER_MERGE_RETRACTION_ORIGIN must be an HTTPS origin")
	}
	audience, _ := lookup("LISTEN_FINALIZATION_TASKS_OIDC_AUDIENCE")
	if audience == "" {
		audience, _ = lookup("LISTEN_FINALIZATION_TASKS_HANDLER_URL")
	}
	if strings.TrimSpace(audience) == "" {
		return errors.New("merge retraction requires a listen finalization OIDC audience")
	}
	c.retractionOrigin, c.retractionAudience = origin, audience
	return nil
}

func (c *config) readObjectLake(lookup lookupEnv) error {
	if enabled, set := lookup("OBJECT_LAKE_READ_ENABLED"); set && !strings.EqualFold(enabled, "true") {
		return nil
	}
	bucket, _ := lookup("BUCKET_OBJECT_LAKE")
	key, _ := lookup("OBJECT_LAKE_KMS_KEY")
	if (bucket == "") != (key == "") {
		return errors.New("object-lake reads require BUCKET_OBJECT_LAKE and OBJECT_LAKE_KMS_KEY")
	}
	c.objectBucket, c.objectKMSKey = bucket, key
	return nil
}

func (c *config) readSummaryRepair(lookup lookupEnv) error {
	c.summaryMaxAge = 72 * time.Hour
	raw, set := lookup("WORKER_SUMMARY_REPAIR_ENABLED")
	if !set || raw == "" {
		return nil
	}
	enabled, err := strconv.ParseBool(raw)
	if err != nil {
		return errors.New("WORKER_SUMMARY_REPAIR_ENABLED must be a boolean")
	}
	c.summaryRepair = enabled
	if age, configured := lookup("ENRICHMENT_MAX_AGE_HOURS"); configured {
		hours, parseErr := strconv.ParseFloat(strings.TrimSpace(age), 64)
		nanos := hours * float64(time.Hour)
		if parseErr == nil && !math.IsNaN(nanos) && nanos >= 0 && nanos < float64(math.MaxInt64) {
			c.summaryMaxAge = time.Duration(nanos)
		}
	}
	return nil
}

func validDatabaseURL(raw string) bool {
	u, err := url.Parse(raw)
	if err != nil || (u.Scheme != "postgres" && u.Scheme != "postgresql") {
		return false
	}
	if u.Hostname() == "" || u.User == nil || u.User.Username() == "" || len(u.Path) < 2 {
		return false
	}
	parsed, err := pgxpool.ParseConfig(raw)
	if err != nil {
		return false
	}
	if configUsesOnlyLoopback(parsed) {
		return true
	}
	if parsed.ConnConfig.TLSConfig == nil {
		return false
	}
	for _, fallback := range parsed.ConnConfig.Fallbacks {
		if fallback.TLSConfig == nil {
			return false
		}
	}
	return true
}

func configUsesOnlyLoopback(parsed *pgxpool.Config) bool {
	if !isLoopbackHost(parsed.ConnConfig.Host) {
		return false
	}
	for _, fallback := range parsed.ConnConfig.Fallbacks {
		if !isLoopbackHost(fallback.Host) {
			return false
		}
	}
	return true
}

func isLoopbackHost(host string) bool {
	if ip := net.ParseIP(host); ip != nil {
		return ip.IsLoopback()
	}
	return strings.EqualFold(strings.TrimSuffix(host, "."), "localhost")
}

func (c *config) readPolicy(lookup lookupEnv) error {
	p := &c.policy
	p.GateAbandoned = gateAbandoned
	settings := []struct {
		name             string
		defaultValue     int
		minimum, maximum int
		set              func(int)
	}{
		{"HEALTH_PORT", 8080, 1, 65535, func(n int) { c.healthPort = n }},
		{"METRICS_PORT", 9090, 1, 65535, func(n int) { c.metricsPort = n }},
		{"SHUTDOWN_SECONDS", 25, 5, 300, func(n int) { c.stopTimeout = time.Duration(n) * time.Second }},
		{"WORKERS", 4, 1, 64, func(n int) { p.Workers = n }},
		{"LEASE_SECONDS", 60, 3, 86400, func(n int) { p.Lease = time.Duration(n) * time.Second }},
		{"BACKOFF_BASE_MS", 1000, 1, 86400000, func(n int) { p.Backoff = time.Duration(n) * time.Millisecond }},
		{"BUDGET_REQUEUE_SECONDS", 2700, 0, 31536000, func(n int) { p.BudgetDelay = time.Duration(n) * time.Second }},
		{"GATE_TIMEOUT_SECONDS", 1209600, 1, 31536000, func(n int) { p.GateTimeout = time.Duration(n) * time.Second }},
		{"MAX_ATTEMPTS", 5, 1, 1000000, func(n int) { p.MaxAttempts = n }},
		{"DETERMINISTIC_MAX_ATTEMPTS", 4, 1, 1000000, func(n int) { p.DeterministicMax = n }},
		{"RECONCILE_MAX_ATTEMPTS", 20, 1, 1000000, func(n int) { p.ReconcileMax = n }},
	}
	for _, setting := range settings {
		value := setting.defaultValue
		if raw, ok := lookup(setting.name); ok {
			parsed, err := strconv.Atoi(raw)
			if err != nil || parsed < setting.minimum || parsed > setting.maximum {
				return fmt.Errorf("%s must be an integer between %d and %d", setting.name, setting.minimum, setting.maximum)
			}
			value = parsed
		}
		setting.set(value)
	}
	return nil
}
