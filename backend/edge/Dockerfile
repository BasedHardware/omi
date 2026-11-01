# listen-edge (plan D): the Rust websocket edge in front of backend-listen.
# Build from the repository root so the image carries listen's Silero model:
#
#   docker build -f backend/edge/Dockerfile \
#     --build-arg OMI_RELEASE_SHA="$(git rev-parse HEAD)" .
#
# Built and probed by .github/workflows/role_images.yml and published by the
# gcp_backend.yml build-only train (backend/scripts/role_images.py). No chart or
# deploy references it yet; D2's deploy step adds the GKE Deployment.
#
# Keep the release stamp last so a new SHA invalidates metadata only.

FROM rust:1.99.1-slim-bookworm AS builder

# libopus through pkg-config (the opus crate's preferred path; cmake covers its
# bundled fallback); ort downloads its prebuilt static ONNX Runtime at build time
# through ureq/native-tls, so the builder needs libssl-dev (not the runtime).
RUN apt-get update && apt-get install -y --no-install-recommends \
    pkg-config \
    libopus-dev \
    libssl-dev \
    cmake \
    g++ \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY backend/edge/ ./
RUN cargo build --locked --release --bin listen-edge

FROM debian:bookworm-slim AS runtime

RUN apt-get update && apt-get -y dist-upgrade \
    && apt-get install -y --no-install-recommends libopus0 libstdc++6 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 omi \
    && useradd --system --uid 10001 --gid omi --no-create-home omi

COPY --from=builder /src/target/release/listen-edge /usr/local/bin/listen-edge
# The same Silero model listen's gate scores (D2 parity goldens ran against it).
COPY backend/utils/stt/assets/silero_vad.onnx /models/silero_vad.onnx

ENV EDGE_VAD_MODEL_PATH=/models/silero_vad.onnx
USER omi
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/listen-edge"]
ARG OMI_RELEASE_SHA=unknown
ENV OMI_RELEASE_SHA=${OMI_RELEASE_SHA}
LABEL org.opencontainers.image.revision=${OMI_RELEASE_SHA}
