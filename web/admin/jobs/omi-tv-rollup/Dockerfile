# Build context: web/admin. Reuses the lockfile, with no analytics SDK or keys.
FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY lib/qualified-activity.ts lib/wall-mcp.ts lib/wall-capture-sql.ts lib/wall-rollup-extract.ts ./lib/
COPY jobs/omi-tv-rollup/ ./jobs/omi-tv-rollup/
RUN npx tsc -p jobs/omi-tv-rollup/tsconfig.json
RUN npm prune --omit=dev

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder --chown=node:node /app/node_modules ./node_modules
COPY --from=builder --chown=node:node /app/.rollup-build ./
USER node
ENTRYPOINT ["node", "jobs/omi-tv-rollup/entry.js"]
