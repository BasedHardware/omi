# OMI Desktop Backend - Rust
# Multi-stage build for smaller image size

# Build stage
FROM rust:1.83-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy manifests
COPY Cargo.toml Cargo.lock* ./

# Create dummy src to cache dependencies
RUN mkdir src && echo "fn main() {}" > src/main.rs

# Build dependencies only (cached layer)
RUN cargo build --release && rm -rf src

# Copy actual source code and templates
COPY src ./src
COPY templates ./templates

# Build the application
RUN touch src/main.rs && cargo build --release

# Runtime stage
FROM debian:bookworm-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    ca-certificates \
    libssl3 \
    && rm -rf /var/lib/apt/lists/*

# Copy binary from builder
COPY --from=builder /app/target/release/omi-desktop-backend /app/omi-desktop-backend

# Copy Google credentials for Firestore access
COPY google-credentials.json /app/google-credentials.json

# Expose port
EXPOSE 8080

# Run the binary
CMD ["./omi-desktop-backend"]
