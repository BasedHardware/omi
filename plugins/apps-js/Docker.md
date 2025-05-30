# Docker Setup for Apps-JS

This directory contains multiple Docker configurations for the apps-js Node.js application, each optimized for different deployment scenarios.

## Available Dockerfiles

### 1. `Dockerfile` (Production)
**Purpose**: Standard production deployment
**Features**:
- Multi-stage build for optimized image size
- Node.js 18 Alpine base for security and performance
- Non-root user for enhanced security
- Health check endpoint monitoring
- Production environment variables
- Optimized dependency installation

**Usage**:
```bash
# Build the image
docker build -f plugins/apps-js/Dockerfile -t apps-js:latest .

# Run the container
docker run -d -p 8080:8080 --name apps-js apps-js:latest

# Test health endpoint
curl http://localhost:8080/health
```

### 2. `Dockerfile.datadog` (Monitoring)
**Purpose**: Production deployment with Datadog APM monitoring
**Features**:
- All features from standard Dockerfile
- Datadog dd-trace integration for APM
- Simplified setup without serverless-init complexity
- Ready for production observability

**Usage**:
```bash
# Build the image
docker build -f plugins/apps-js/Dockerfile.datadog -t apps-js:datadog .

# Run with Datadog environment variables
docker run -d -p 8080:8080 \
  -e DD_API_KEY=your_datadog_api_key \
  -e DD_SITE=datadoghq.com \
  -e DD_SERVICE=apps-js \
  -e DD_ENV=production \
  --name apps-js-datadog apps-js:datadog
```

## Configuration

### Environment Variables
The application supports the following environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | 3000 | Server port (set to 8080 in Docker) |
| `NODE_ENV` | development | Node.js environment |
| `DD_API_KEY` | - | Datadog API key (for monitoring) |
| `DD_SITE` | datadoghq.com | Datadog site |
| `DD_SERVICE` | apps-js | Service name for Datadog |
| `DD_ENV` | - | Environment name for Datadog |

### Health Check
All Docker images include a health check endpoint:
- **Endpoint**: `GET /health`
- **Response**: `{"status":"ok"}`
- **Interval**: 30 seconds
- **Timeout**: 3 seconds
- **Retries**: 3

## Security Features

### Non-Root User
All containers run as a non-root user (`nodejs:1001`) for enhanced security:
- Prevents privilege escalation attacks
- Follows Docker security best practices
- Maintains application functionality

### Minimal Base Image
Using Node.js 18 Alpine provides:
- Smaller attack surface
- Reduced image size
- Security-focused Linux distribution
- Regular security updates

### .dockerignore
The `.dockerignore` file excludes:
- Development files and logs
- Environment files with secrets
- Version control files
- IDE configuration files

## Build Optimization

### Multi-Stage Build
The Dockerfiles use multi-stage builds to:
- Separate build dependencies from runtime
- Reduce final image size
- Improve build caching
- Enhance security by excluding build tools

### Dependency Caching
Build process optimizes for Docker layer caching:
1. Copy package files first
2. Install dependencies (cached if unchanged)
3. Copy application code
4. Set up user and permissions

## Deployment Examples

### Docker Compose
```yaml
version: '3.8'
services:
  apps-js:
    build:
      context: .
      dockerfile: plugins/apps-js/Dockerfile
    ports:
      - "8080:8080"
    environment:
      - NODE_ENV=production
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 3s
      retries: 3
    restart: unless-stopped
```

### Kubernetes Deployment
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: apps-js
spec:
  replicas: 3
  selector:
    matchLabels:
      app: apps-js
  template:
    metadata:
      labels:
        app: apps-js
    spec:
      containers:
      - name: apps-js
        image: apps-js:latest
        ports:
        - containerPort: 8080
        env:
        - name: NODE_ENV
          value: "production"
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
```

## Troubleshooting

### Common Issues

1. **Port Conflicts**
   - Ensure port 8080 is available
   - Use different host ports: `-p 8081:8080`

2. **Permission Errors**
   - Verify file ownership in container
   - Check if running as non-root user

3. **Health Check Failures**
   - Verify application starts correctly
   - Check logs: `docker logs <container_name>`
   - Test endpoint manually: `curl http://localhost:8080/health`

4. **Datadog Issues**
   - Ensure DD_API_KEY is set
   - Verify Datadog agent connectivity
   - Check dd-trace initialization logs

### Debugging Commands
```bash
# View container logs
docker logs apps-js

# Execute shell in running container
docker exec -it apps-js sh

# Inspect container configuration
docker inspect apps-js

# View resource usage
docker stats apps-js
```

## Performance Considerations

### Resource Limits
Recommended resource limits for production:
```bash
docker run -d \
  --memory=512m \
  --cpus=0.5 \
  -p 8080:8080 \
  apps-js:latest
```

### Scaling
For high-traffic deployments:
- Use container orchestration (Kubernetes, Docker Swarm)
- Implement horizontal pod autoscaling
- Configure load balancing
- Monitor with Datadog APM

## Security Scanning

Regularly scan images for vulnerabilities:
```bash
# Using Docker Scout
docker scout cves apps-js:latest

# Using Trivy
trivy image apps-js:latest
```

## Maintenance

### Updates
1. Update base image regularly
2. Keep dependencies current
3. Rebuild images for security patches
4. Test thoroughly before production deployment

### Monitoring
- Monitor container health and performance
- Set up alerts for failures
- Track resource usage trends
- Use Datadog for comprehensive observability 