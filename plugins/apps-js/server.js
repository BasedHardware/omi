require('dotenv').config();
const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const compression = require('compression');
const cookieParser = require('cookie-parser');
const path = require('path');

// Import configuration
const { 
  REQUIRED_ENV_VARS,
  MAX_REQUESTS_PER_MINUTE,
  RATE_LIMIT_WINDOW_MS,
  PERFORMANCE_MONITORING_ENABLED,
  PERFORMANCE_LOG_INTERVAL
} = require('./email/src/config/constants');

// Import services
const { checkSupabaseConnection } = require('./email/src/services/authService');
const { initializeDatabase } = require('./email/src/utils/dbUtils');
const { closeRedisConnection } = require('./email/src/utils/redisUtils');
// Import routes
const emailRouter = require('./email/src/routes/email');
const deckRouter = require('./deck/src/routes/deck');

const app = express();
const PORT = process.env.PORT || 8080;

// Validate required environment variables
for (const envVar of REQUIRED_ENV_VARS) {
  if (!process.env[envVar]) {
    console.error(`Error: ${envVar} environment variable is required`);
    process.exit(1);
  }
}

// Enable trust proxy
app.set('trust proxy', 1);

// Middleware
app.use(helmet());
app.use(cors());
app.use(compression());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(cookieParser());

// Serve static files from the 'public' directory
app.use(express.static(path.join(__dirname, 'public')));

// Rate limiting middleware
const requestCounts = new Map();

app.use((req, res, next) => {
  const now = Date.now();
  const clientIp = req.ip;
  
  // Clean up expired entries
  for (const [ip, data] of requestCounts.entries()) {
    if (now - data.windowStart > RATE_LIMIT_WINDOW_MS) {
      requestCounts.delete(ip);
    }
  }
  
  // Initialize or get client data
  if (!requestCounts.has(clientIp)) {
    requestCounts.set(clientIp, {
      count: 0,
      windowStart: now
    });
  }
  
  const clientData = requestCounts.get(clientIp);
  
  // Reset window if needed
  if (now - clientData.windowStart > RATE_LIMIT_WINDOW_MS) {
    clientData.count = 0;
    clientData.windowStart = now;
  }
  
  // Increment count and check limits
  clientData.count++;
  
  if (clientData.count > MAX_REQUESTS_PER_MINUTE) {
    console.warn(`Rate limit exceeded for IP: ${clientIp}`);
    return res.status(429).json({
      error: 'rate_limit_exceeded',
      message: 'Too many requests, please try again later.'
    });
  }
  
  next();
});



// Routes
app.use('/api/email', emailRouter);
app.use('/api/deck', deckRouter);

// App routes
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.get('/email', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'email.html'));
});

app.get('/deck', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'deck.html'));
});

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({ status: 'ok' });
});

  // Initialize database and start server
  async function startServer() {
    try {
      // Initialize Supabase tables
      await initializeDatabase();
    
    // Check Supabase connection
    await checkSupabaseConnection();
      
      // Ensure Redis is connected
      try {
      const { initializeRedis } = require('./email/src/utils/redisUtils');
        const redisConnected = await initializeRedis();
        if (redisConnected) {
          console.log('Redis initialized successfully');
        } else {
          console.warn('Redis initialization failed, some features may not work properly');
        }
      } catch (redisError) {
        console.error('Failed to initialize Redis:', redisError);
        console.warn('Continuing without Redis, some features may not work properly');
      }
      
      // Start HTTP server
      const server = app.listen(PORT, () => {
        console.log(`Server running on port ${PORT}`);
      }).on('error', (err) => {
        if (err.code === 'EADDRINUSE') {
          console.error(`Port ${PORT} is already in use. Please try a different port or kill the process using this port.`);
          process.exit(1);
        } else {
          console.error('Failed to start server:', err);
          process.exit(1);
        }
      });

      // Graceful shutdown handler
      const shutdown = async () => {
        console.log('\nGracefully shutting down...');
        
        // Close server first to stop accepting new connections
        server.close(() => {
            console.log('Server closed');
        });

        try {
          // Close Redis connections
          await closeRedisConnection();
          console.log('Redis connection closed');
          
          // Exit process
          process.exit(0);
        } catch (error) {
          console.error('Error during shutdown:', error);
          process.exit(1);
        }
      };

      // Handle shutdown signals
      process.on('SIGTERM', shutdown);
      process.on('SIGINT', shutdown);
      
      return server;
    } catch (error) {
      console.error('Failed to start server:', error);
      process.exit(1);
    }
  }

  // Start the server
  startServer().catch(error => {
    console.error('Unhandled error during server startup:', error);
    process.exit(1);
  });

  module.exports = app;



