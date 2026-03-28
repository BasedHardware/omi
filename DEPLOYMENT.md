# One-Click Deployment

Deploy omi backend in 2 minutes with Docker.

## Prerequisites

- Docker Desktop (or Docker Engine)
- Docker Compose

## Quick Start

### 1. Clone & Setup

```bash
git clone https://github.com/BasedHardware/omi.git
cd omi
bash setup.sh
```

This creates `.env` file. Edit with your API keys:

```bash
nano .env
```

Required keys:
- **Firebase**: Project ID, Private Key, Client Email
- **Pinecone**: API Key, Index Name
- **OpenAI**: API Key

### 2. Deploy

```bash
bash setup.sh
```

### 3. Verify

```bash
curl http://localhost:8080/health
```

## Services

| Service | Port | Purpose |
|---------|------|---------|
| Backend | 8080 | FastAPI application |
| Redis | 6379 | Caching & queues |
| PostgreSQL | 5432 | Persistent storage |

## Management

```bash
# View logs
docker-compose logs -f backend

# Restart services
docker-compose restart

# Stop services
docker-compose down

# Reset everything
docker-compose down -v
```

## Troubleshooting

### Backend not responding?

```bash
# Check logs
docker-compose logs backend

# Check service health
docker-compose ps
```

### Database connection errors?

```bash
# Reset PostgreSQL
docker-compose down -v postgres
docker-compose up -d postgres
```

### Need help?

- [Documentation](https://docs.omi.me/)
- [Discord](http://discord.omi.me)
- [GitHub Issues](https://github.com/BasedHardware/omi/issues)
