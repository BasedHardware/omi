# OMI Desktop Backend - Rust
# Multi-stage build for smaller image size

# Build stage
FROM rust:1.88.0-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy manifests
COPY Cargo.toml Cargo.lock ./
COPY shared-rust/Cargo.toml shared-rust/Cargo.toml
COPY macos/Backend-Rust/Cargo.toml macos/Backend-Rust/Cargo.toml

# Create dummy src to cache dependencies
RUN mkdir -p shared-rust/src macos/Backend-Rust/src \
    && echo "pub fn placeholder() {}" > shared-rust/src/lib.rs \
    && echo "fn main() {}" > macos/Backend-Rust/src/main.rs

# Build dependencies only (cached layer)
RUN cargo build --release --locked -p omi-desktop-backend \
    && rm -rf shared-rust/src macos/Backend-Rust/src

# Copy actual source code, templates, and compile-time fixtures.
COPY shared-rust ./shared-rust
COPY macos/Backend-Rust/src ./macos/Backend-Rust/src
COPY macos/Backend-Rust/templates ./macos/Backend-Rust/templates
COPY macos/Backend-Rust/fixtures ./macos/Backend-Rust/fixtures

# Build the application
RUN touch macos/Backend-Rust/src/main.rs && cargo build --release --locked -p omi-desktop-backend

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
COPY macos/Backend-Rust/google-credentials.json /app/google-credentials.json

# Expose port
EXPOSE 8080

# Run the binary
CMD ["./omi-desktop-backend"]
