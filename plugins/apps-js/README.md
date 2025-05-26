# OmiSend

A comprehensive Node.js server application for AI-powered email management and presentation generation with voice command integration.

## 🚀 Features

### 📧 Email Management
- **AI-powered email search and analysis** with enhanced semantic search
- **Voice-controlled email composition** and sending
- **Smart email fetching** with context-aware filtering
- **Contact management** with intelligent name resolution
- **OAuth integration** with Google Gmail API
- **Email thread summarization** and analysis

### 📊 Presentation Generation
- **Voice-triggered presentation creation** with "Hey Omi" commands
- **AI-powered slide generation** using SlidesGPT API
- **Real-time progress tracking** with web viewer interface
- **Persistent presentation storage** with Supabase database
- **Multiple output formats** (embed links, PowerPoint downloads)

### 🎯 Voice Command Processing
- **Intent detection** with natural language processing
- **Multi-language support** for voice commands
- **Context-aware conversation flow** management
- **Real-time webhook processing** for voice segments

### 🔧 Infrastructure
- **Redis caching** for session state management
- **Supabase database** for persistent data storage
- **Rate limiting** and performance monitoring
- **Comprehensive error handling** and logging
- **Security middleware** with Helmet and CORS

## 📋 Prerequisites

- Node.js (v14 or higher)
- Redis (for session management)
- Supabase account (for database)
- OpenAI API key (for AI features)
- SlidesGPT API key (for presentation generation)
- Google OAuth credentials (for email features)

## 🛠️ Installation

1. **Clone the repository:**
```bash
git clone https://github.com/yourusername/omisend.git
cd omisend
```

2. **Install dependencies:**
```bash
npm install
```

3. **Create a `.env` file** in the root directory:
```env
# Server Configuration
PORT=3000
NODE_ENV=development

# Database
SUPABASE_URL=your_supabase_url_here
SUPABASE_KEY=your_supabase_anon_key_here

# Redis (Upstash)
UPSTASH_REDIS_HOST=your_redis_host
UPSTASH_REDIS_PASSWORD=your_redis_password
UPSTASH_REDIS_PORT=your_redis_port

# AI Services
OPENAI_API_KEY=your_openai_api_key_here
SLIDESGPT_API_KEY=your_slidesgpt_api_key_here

# Google OAuth (for email features)
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=your_redirect_uri

# Security
JWT_SECRET=your_jwt_secret_here
```

4. **Set up the database:**
```bash
npm run setup-supabase
```

## 📁 Project Structure

```
src/
├── config/
│   └── constants.js          # Application configuration
├── controllers/
│   └── webhookController.js  # Webhook request handling
├── middleware/               # Custom middleware functions
├── models/
│   ├── intentDetection.js    # Voice command pattern matching
│   ├── aiEmailFetcher.js     # AI-powered email retrieval
│   ├── aiEmailSender.js      # AI-powered email composition
│   ├── enhancedEmailSearch.js # Advanced email search
│   ├── Email.js              # Email data model
│   └── User.js               # User data model
├── routes/
│   ├── auth.js               # Authentication endpoints
│   ├── email.js              # Email management API
│   └── deck.js               # Presentation generation API
├── services/
│   └── authService.js        # Authentication services
└── utils/
    ├── dbUtils.js            # Database utilities
    ├── redisUtils.js         # Redis cache management
    ├── emailUtils.js         # Email processing utilities
    ├── deckUtils.js          # Presentation utilities
    ├── googleAuth.js         # Google OAuth integration
    ├── supabaseUtils.js      # Supabase database utilities
    ├── contactUtils.js       # Contact management
    ├── nameUtils.js          # Name resolution utilities
    ├── omiUtils.js           # Core Omi utilities
    ├── mailUtils.js          # Mail processing
    └── errorHandler.js       # Error handling utilities

public/
├── index.html                # Main web interface
├── deck.html                 # Presentation interface
├── success.html              # Success page
└── style.css                 # Styling

tests/                        # Test suites
server.js                     # Main application entry point
```

## 🔌 API Endpoints

### Authentication
- `GET /api/auth/oauth/callback` - Google OAuth callback
- `POST /api/auth/login` - User authentication
- `GET /api/auth/profile` - Get user profile

### Email Management
- `POST /api/email/send` - Send email via voice command
- `GET /api/email/search` - Search emails with AI
- `GET /api/email/fetch` - Fetch emails with context
- `GET /api/email/contacts` - Get contact list
- `GET /api/email/summary/:threadId` - Get email thread summary

### Presentation Generation
- `POST /api/deck/webhook` - Process voice commands for presentations
- `GET /api/deck/status/:presentation_id` - Check generation status
- `GET /api/deck/viewer/:presentation_id` - View presentation progress
- `GET /api/deck/history/:session_id` - Get presentation history

### System
- `POST /webhook` - Main webhook endpoint for voice processing
- `GET /health` - Health check endpoint

## 🎮 Usage

### Starting the Server

**Development mode:**
```bash
npm run dev
```

**Production mode:**
```bash
npm start
```

### Voice Commands

**Email Commands:**
- "Hey Omi, send an email to [contact] about [subject]"
- "Find emails from [sender] about [topic]"
- "Show me recent emails"

**Presentation Commands:**
- "Hey Omi, create a presentation about [topic]"
- "Make slides on [subject]"

### Web Interface

1. **Main Interface:** Visit `http://localhost:3000`
2. **Presentation Viewer:** Visit `http://localhost:3000/deck`
3. **Real-time Tracking:** Each presentation gets a unique viewer URL

## 🔧 Development

### Running Tests
```bash
npm test
```

### Database Setup
```bash
# Initialize Supabase tables
npm run setup-supabase

# Test database connection
node tests/test_database.js
```

### Performance Monitoring
The application includes built-in performance monitoring that logs:
- Request count and error rates
- Average and maximum response times
- Webhook processing statistics
- Email sending metrics

## 🛡️ Security Features

- **Helmet.js** for security headers
- **CORS** configuration for cross-origin requests
- **Rate limiting** (200 requests per minute per IP)
- **Input validation** with express-validator
- **JWT authentication** for secure sessions
- **Environment variable validation** on startup

## 📊 Database Schema

### Presentations Table
- Stores presentation generation data
- Tracks status, content, and SlidesGPT responses
- Maintains persistent URLs for embed and download

### Users Table
- User authentication and profile data
- OAuth integration details

### Emails Table
- Email metadata and processing history
- Search indexing and caching

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the ISC License - see the LICENSE file for details.

## 🆘 Support

For detailed setup instructions for the presentation system, see [PRESENTATION_SETUP.md](./PRESENTATION_SETUP.md).

For issues and questions, please open an issue on GitHub. 