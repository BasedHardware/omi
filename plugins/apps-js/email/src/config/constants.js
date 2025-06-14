// Import pattern constants from intentDetection
const {
  RECORDING_TIMEOUT,
  STOP_TRIGGER_PATTERN,
  TRIGGER_PATTERN,
  EMAIL_COMMAND_PATTERN,
  CONFIRMATION_PATTERNS,
} = require('../models/intentDetection');

// State and session management
const STATE_EXPIRY_SECONDS = 300; // 5 minutes for Redis state
const CONFIDENCE_THRESHOLD = 0.65; // Threshold for fuzzy matching confidence

// Request rate limiting
const MAX_REQUESTS_PER_MINUTE = 200;
const RATE_LIMIT_WINDOW_MS = 60000; // 1 minute

// Performance monitoring
const PERFORMANCE_MONITORING_ENABLED = true;
const PERFORMANCE_LOG_INTERVAL = 300000; // Log performance stats every 5 minutes

// Redis configuration
const REDIS_OPERATION_TIMEOUT = 1000; // 1 second for Redis operations

// Voice email flow constants
const EMAIL_CONTEXT_COLLECTION_DURATION = 30000; // 30 seconds
const MIN_COLLECTION_TIME = 3000; // Minimum time to collect context before processing
const SEND_EMAIL_MIN_COLLECTION_TIME = 15000; // Dedicated longer collection time for send_email (15 seconds)

// Environment validation
const REQUIRED_ENV_VARS = [
  'UPSTASH_REDIS_HOST',
  'UPSTASH_REDIS_PASSWORD',
  'UPSTASH_REDIS_PORT',
  'SUPABASE_URL',
  'SUPABASE_KEY',
  'OPENAI_API_KEY'
];

// Cache settings
const STATE_CACHE_TTL = 60000; // 60 seconds cache TTL
const INTENT_CACHE_TTL = 300000; // 5 minutes

module.exports = {
  // Pattern constants
  RECORDING_TIMEOUT,
  STOP_TRIGGER_PATTERN,
  TRIGGER_PATTERN,
  EMAIL_COMMAND_PATTERN,
  CONFIRMATION_PATTERNS,
  
  // State and session
  STATE_EXPIRY_SECONDS,
  CONFIDENCE_THRESHOLD,
  
  // Rate limiting
  MAX_REQUESTS_PER_MINUTE,
  RATE_LIMIT_WINDOW_MS,
  
  // Performance
  PERFORMANCE_MONITORING_ENABLED,
  PERFORMANCE_LOG_INTERVAL,
  
  // Redis
  REDIS_OPERATION_TIMEOUT,
  
  // Voice email flow
  EMAIL_CONTEXT_COLLECTION_DURATION,
  MIN_COLLECTION_TIME,
  SEND_EMAIL_MIN_COLLECTION_TIME,
  
  // Environment
  REQUIRED_ENV_VARS,
  
  // Cache
  STATE_CACHE_TTL,
  INTENT_CACHE_TTL
}; 