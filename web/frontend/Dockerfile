FROM node:18-alpine AS base

# Set working directory
WORKDIR /app

# Install dependencies only when needed
FROM base AS deps
RUN apk add --no-cache libc6-compat
WORKDIR /app/web/frontend

# Copy only the lock and package files
COPY web/frontend/package.json web/frontend/yarn.lock* web/frontend/package-lock.json* web/frontend/pnpm-lock.yaml* ./

RUN \
  if [ -f yarn.lock ]; then yarn --frozen-lockfile; \
  elif [ -f package-lock.json ]; then npm ci; \
  elif [ -f pnpm-lock.yaml ]; then yarn global add pnpm && pnpm i --frozen-lockfile; \
  else echo "Lockfile not found." && exit 1; \
  fi

# Rebuild the source code only when needed
FROM base AS builder
WORKDIR /app/web/frontend
COPY --from=deps /app/web/frontend/node_modules ./node_modules
COPY web/frontend .

ENV API_URL=https://backend-hhibjajaja-uc.a.run.app
RUN npm run build

RUN echo "Files in builder:"
RUN ls -la

# Production image
FROM base AS runner
WORKDIR /app

ENV NODE_ENV production

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# Copy built output
COPY --from=builder /app/web/frontend/public ./public

RUN mkdir .next
RUN chown nextjs:nodejs .next

COPY --from=builder --chown=nextjs:nodejs /app/web/frontend/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/web/frontend/.next/static ./.next/static

USER nextjs

EXPOSE 3000
ENV PORT 3000
ENV HOSTNAME "0.0.0.0"

CMD ["node", "server.js"]
