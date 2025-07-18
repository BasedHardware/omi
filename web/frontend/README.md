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
