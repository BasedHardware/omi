# Build context: web/admin. Reuses the lockfile; no BigQuery, PostHog or vendor keys.
FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY lib/wall-live.ts lib/omi-tv-live-rates.json ./lib/
COPY jobs/omi-tv-live/ ./jobs/omi-tv-live/
RUN npx tsc -p jobs/omi-tv-live/tsconfig.json
RUN npm prune --omit=dev

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder --chown=node:node /app/node_modules ./node_modules
COPY --from=builder --chown=node:node /app/.live-build ./
USER node
ENTRYPOINT ["node", "jobs/omi-tv-live/entry.js"]
