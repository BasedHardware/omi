# Omi Frontend

A Next.js web application for the Omi wearable device by Based Hardware. This frontend provides interfaces for managing memories, apps, and interacting with the Omi ecosystem.

## Tech Stack

- **Framework**: Next.js 14 with App Router
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **UI Components**: Radix UI, Shadcn/ui
- **Authentication**: Firebase Auth
- **Database**: Firebase Firestore
- **Search**: Algolia
- **Caching**: Redis
- **Icons**: Lucide React, Iconoir
- **Animations**: Framer Motion

## Getting Started

### Prerequisites

- Node.js 18+
- npm, yarn, or pnpm package manager
- Firebase project setup
- Redis instance (for caching)
- Algolia account (for search functionality)

### Installation

1. **Clone the repository and navigate to the frontend directory**

   ```bash
   git clone <repository-url>
   cd omi/web/frontend
   ```

2. **Install dependencies**

   ```bash
   npm install
   # or
   yarn install
   # or
   pnpm install
   ```

3. **Set up environment variables**

   ```bash
   cp .env.template .env.local
   # Edit .env.local with your actual values
   ```

4. **Start the development server**

   ```bash
   npm run dev
   # or
   yarn dev
   # or
   pnpm dev
   ```

5. **Open your browser**
   Navigate to [http://localhost:3000](http://localhost:3000)

## Signing in locally (Firebase Auth emulator)

Signed-in surfaces such as `/memory-platform` need a real Omi session. Rather than a
production Firebase project, point the app at the repo's local dev harness, which runs
the Firebase Auth emulator on `127.0.0.1:9099`, the Firestore emulator on `127.0.0.1:8085`,
and the backend on `127.0.0.1:8000`.

1. **Start the stack** from the repo root:

   ```bash
   PROVIDER_MODE=offline make dev-up   # backend + Firestore/Auth emulators + Redis + Typesense
   ```

   The harness allows `http://localhost:3000` and `http://localhost:3001` through the
   backend's default-deny CORS policy, so browser requests from `npm run dev` work.

2. **Create `web/frontend/.env`** (never committed — `.env*` is gitignored). Fake but
   well-formed Firebase values are fine; the emulator ignores the API key, but the project
   id must match the harness project:

   ```bash
   NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
   API_URL=http://127.0.0.1:8000
   NEXT_PUBLIC_FIREBASE_API_KEY=fake-api-key
   NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=demo-omi-local.firebaseapp.com
   NEXT_PUBLIC_FIREBASE_PROJECT_ID=demo-omi-local
   NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=demo-omi-local.appspot.com
   NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=000000000000
   NEXT_PUBLIC_FIREBASE_APP_ID=1:000000000000:web:0000000000000000000000

   # Opt in to the emulator. Unset it and the app talks to real Firebase.
   NEXT_PUBLIC_FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9099
   ```

3. **Run `npm run dev` and sign in.** Use the header's sign-in button; the Google popup is
   served by the emulator, where **Add new account** creates a test user (the first field is
   the email). A red *"Running in emulator mode"* banner confirms the app is not talking to
   production.

`NEXT_PUBLIC_FIREBASE_AUTH_EMULATOR_HOST` is honoured only in a non-production build and
only for a loopback host — see `src/lib/firebase-auth-emulator.mjs`. A production deploy
therefore cannot be redirected to an emulator by a stray environment variable.

To act as the harness's seeded canonical memory user, give the emulator's `alice` account a
password and sign in as it:

```bash
curl -X POST "http://127.0.0.1:9099/identitytoolkit.googleapis.com/v1/projects/demo-omi-local/accounts:update" \
  -H "Authorization: Bearer owner" -H "Content-Type: application/json" \
  -d '{"localId":"alice","email":"alice@omi.local","password":"omi-local-dev","emailVerified":true}'
```

## Environment Variables

See `.env.template` for all required environment variables. Key variables include:

- **Firebase Configuration**: Complete Firebase project setup
- **API Configuration**: Backend API URL
- **Redis**: Database connection for caching
- **Algolia**: Search service configuration
- **Gleap**: Customer support integration

## Available Scripts

- `npm run dev` - Start development server with Turbo
- `npm run build` - Build for production
- `npm run start` - Start production server
- `npm run lint` - Run ESLint
- `npm run lint:fix` - Fix ESLint issues automatically
- `npm run lint:format` - Format code with Prettier

## Docker Deployment

### Build and run with Docker

```bash
# Build the image
docker build -t omi-frontend .

# Run the container
docker run -p 3000:3000 omi-frontend
```

### Using Docker Compose

```bash
docker-compose up --build
```

## Project Structure

```
src/
├── app/                    # Next.js App Router pages
│   ├── apps/              # Apps management
│   ├── memories/          # Memory management
│   ├── my-apps/           # User apps
│   └── components/        # Page-specific components
├── components/            # Reusable UI components
│   ├── shared/           # Shared components
│   └── ui/               # UI component library
├── constants/            # App constants and configuration
├── hooks/                # Custom React hooks
├── lib/                  # Utility libraries (Firebase, etc.)
├── types/                # TypeScript type definitions
├── utils/                # Utility functions
└── actions/              # Server actions
```

## Key Features

- **Memory Management**: View and organize personal memories
- **App Ecosystem**: Browse and manage Omi apps
- **Search**: Algolia-powered search functionality
- **Real-time Updates**: Firebase integration for live data
- **Responsive Design**: Mobile-first responsive interface
- **Performance**: Optimized with Next.js features and caching

## API Integration

The frontend connects to the Omi backend API for:

- User authentication and management
- Memory data synchronization
- App marketplace functionality
- Device communication

## Deployment

### Production Build

```bash
npm run build
npm run start
```

### Environment Setup

Ensure all environment variables are properly configured for your deployment environment. The app supports multiple deployment targets:

- **Development**: Local development with hot reload
- **Staging**: Pre-production testing environment
- **Production**: Live production deployment

## Contributing

1. Follow the existing code style and conventions
2. Use TypeScript for type safety
3. Ensure responsive design principles
4. Test thoroughly before submitting PRs
5. Update documentation as needed

## Support

For issues related to the Omi frontend application, please check the documentation or contact the development team.

## License

This project is part of the Omi ecosystem by Based Hardware.
