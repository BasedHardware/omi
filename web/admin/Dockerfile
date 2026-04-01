# 1. Install dependencies only when needed
FROM node:18-alpine AS deps
# Check https://github.com/nodejs/docker-node/tree/b4117f9333da4138b03a546ec926ef50a31506c3#nodealpine to understand why libc6-compat might be needed.
RUN apk add --no-cache libc6-compat
WORKDIR /app

# Install dependencies based on the preferred package manager
COPY package.json yarn.lock* package-lock.json* pnpm-lock.yaml* ./
RUN \
  if [ -f yarn.lock ]; then yarn --frozen-lockfile; \
  elif [ -f package-lock.json ]; then npm ci; \
  elif [ -f pnpm-lock.yaml ]; then yarn global add pnpm && pnpm i --frozen-lockfile; \
  else echo "Lockfile not found." && exit 1; \
  fi


# 2. Rebuild the source code only when needed
FROM node:18-alpine AS builder
WORKDIR /app

# Add ARG declarations for variables passed via --build-arg
ARG NEXT_PUBLIC_FIREBASE_API_KEY
ARG NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN
ARG NEXT_PUBLIC_FIREBASE_PROJECT_ID
ARG NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET
ARG NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID
ARG NEXT_PUBLIC_FIREBASE_APP_ID
ARG NEXT_PUBLIC_FIREBASE_VAPID_KEY
ARG OMI_API_SECRET_KEY
ARG NEXT_PUBLIC_OMI_API_URL
ARG FIREBASE_PROJECT_ID
ARG FIREBASE_CLIENT_EMAIL
ARG FIREBASE_PRIVATE_KEY
ARG TYPESENSE_HOST
ARG TYPESENSE_API_KEY
ARG STRIPE_SECRET_KEY
ARG STRIPE_UNLIMITED_MONTHLY_PRICE_ID
ARG STRIPE_UNLIMITED_ANNUAL_PRICE_ID
ARG REDIS_HOST
ARG REDIS_PORT
ARG REDIS_PASSWORD
ARG SHIPBOB_API_KEY
ARG SHOPIFY_STORE
ARG SHOPIFY_ACCESS_TOKEN
ARG MIXPANEL_SECRET
ARG OPENAI_API_KEY
ARG POSTHOG_PERSONAL_API_KEY
ARG POSTHOG_PROJECT_ID
ARG POSTHOG_HOST

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Next.js collects completely anonymous telemetry data about general usage.
# Learn more here: https://nextjs.org/telemetry
# Uncomment the following line in case you want to disable telemetry during the build.
# ENV NEXT_TELEMETRY_DISABLED 1

RUN \
  if [ -f yarn.lock ]; then yarn build; \
  elif [ -f package-lock.json ]; then npm run build; \
  elif [ -f pnpm-lock.yaml ]; then yarn global add pnpm && pnpm run build; \
  else echo "Lockfile not found." && exit 1; \
  fi

# 3. Production image, copy all the files and run next
FROM node:18-alpine AS runner
WORKDIR /app

# Re-declare ARG for runtime ENV setting (only needed for non-NEXT_PUBLIC_ vars)
ARG OMI_API_SECRET_KEY
ARG FIREBASE_PROJECT_ID
ARG FIREBASE_CLIENT_EMAIL
ARG FIREBASE_PRIVATE_KEY
ARG TYPESENSE_HOST
ARG TYPESENSE_API_KEY
ARG STRIPE_SECRET_KEY
ARG STRIPE_UNLIMITED_MONTHLY_PRICE_ID
ARG STRIPE_UNLIMITED_ANNUAL_PRICE_ID
ARG REDIS_HOST
ARG REDIS_PORT
ARG REDIS_PASSWORD
ARG SHIPBOB_API_KEY
ARG SHOPIFY_STORE
ARG SHOPIFY_ACCESS_TOKEN
ARG MIXPANEL_SECRET
ARG OPENAI_API_KEY
ARG POSTHOG_PERSONAL_API_KEY
ARG POSTHOG_PROJECT_ID
ARG POSTHOG_HOST

ENV NODE_ENV production
# Set the non-NEXT_PUBLIC_ variable as a runtime ENV
ENV FIREBASE_PROJECT_ID=$FIREBASE_PROJECT_ID
ENV FIREBASE_CLIENT_EMAIL=$FIREBASE_CLIENT_EMAIL
ENV FIREBASE_PRIVATE_KEY=$FIREBASE_PRIVATE_KEY
ENV OMI_API_SECRET_KEY=$OMI_API_SECRET_KEY
ENV TYPESENSE_HOST=$TYPESENSE_HOST
ENV TYPESENSE_API_KEY=$TYPESENSE_API_KEY
ENV STRIPE_SECRET_KEY=$STRIPE_SECRET_KEY
ENV STRIPE_UNLIMITED_MONTHLY_PRICE_ID=$STRIPE_UNLIMITED_MONTHLY_PRICE_ID
ENV STRIPE_UNLIMITED_ANNUAL_PRICE_ID=$STRIPE_UNLIMITED_ANNUAL_PRICE_ID
ENV REDIS_HOST=$REDIS_HOST
ENV REDIS_PORT=$REDIS_PORT
ENV REDIS_PASSWORD=$REDIS_PASSWORD
ENV SHIPBOB_API_KEY=$SHIPBOB_API_KEY
ENV SHOPIFY_STORE=$SHOPIFY_STORE
ENV SHOPIFY_ACCESS_TOKEN=$SHOPIFY_ACCESS_TOKEN
ENV MIXPANEL_SECRET=$MIXPANEL_SECRET
ENV OPENAI_API_KEY=$OPENAI_API_KEY
ENV POSTHOG_PERSONAL_API_KEY=$POSTHOG_PERSONAL_API_KEY
ENV POSTHOG_PROJECT_ID=$POSTHOG_PROJECT_ID
ENV POSTHOG_HOST=$POSTHOG_HOST

# Uncomment the following line in case you want to disable telemetry during runtime.
# ENV NEXT_TELEMETRY_DISABLED 1

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public

# Set the correct permission for prerender cache
RUN mkdir .next
RUN chown nextjs:nodejs .next

# Automatically leverage output traces to reduce image size
# https://nextjs.org/docs/advanced-features/output-file-tracing
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

ENV PORT 3000
# set hostname to localhost
ENV HOSTNAME "0.0.0.0"

# Assuming you have a server.js file for the standalone output
# If your package.json defines a different start script used by standalone output, adjust this command.
# Check your .next/standalone/package.json 'scripts' section if unsure.
CMD ["node", "server.js"] 