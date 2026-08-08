# Image for the Firebase Firestore + Auth emulators.
# Build context = repo root (../../), so it can copy firestore.rules/indexes from the root.
# The Firestore emulator jar is pre-fetched at BUILD time (setup:emulators:firestore)
# so at RUNTIME no egress to Google is needed.
FROM node:22-trixie-slim

# firebase-tools requires Java >=21 at runtime; trixie provides openjdk-21
RUN apt-get update \
    && apt-get install -y --no-install-recommends openjdk-21-jre-headless curl \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g firebase-tools@15.22.0

WORKDIR /srv
# emulator config with host 0.0.0.0 (the repo's firebase.json pins 127.0.0.1, unreachable
# between containers) + the repo's real rules/indexes
COPY deploy/onprem/firestore-emulator/firebase.compose.json ./firebase.json
COPY firestore.rules ./firestore.rules
COPY firestore.indexes.json ./firestore.indexes.json

# pre-download the Firestore emulator binary (avoids egress at runtime)
RUN firebase setup:emulators:firestore

EXPOSE 8085 9099
CMD ["firebase", "emulators:start", "--only", "firestore,auth", "--project", "demo-omi-local"]
