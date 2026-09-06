FROM oven/bun:1.3.14@sha256:e10577f0db68676a7024391c6e5cb4b879ebd17188ab750cf10024a6d700e5c4 AS build
WORKDIR /app
COPY . .
RUN bun install --production --omit optional --frozen-lockfile
RUN ln -s .bun/postgres@3.4.9/node_modules/postgres node_modules/postgres
RUN bun scripts/verify-production-dependency-closure.mjs --root /app
RUN bun build apps/service/bin/production-server.ts --target=bun --packages=external --outdir=/output

FROM oven/bun:1.3.14-slim@sha256:d56a2534ffd262e92c12fd3249d3924d296d97086da773f821d7d0477435ea04
WORKDIR /app
COPY --from=build --chown=bun:bun /app/node_modules ./node_modules
COPY --from=build --chown=bun:bun /output/production-server.js ./production-server.js
USER bun
ENV PORT=8080
EXPOSE 8080
CMD ["bun", "production-server.js"]
