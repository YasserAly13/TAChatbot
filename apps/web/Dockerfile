# syntax=docker/dockerfile:1
# Multi-stage build for the AI Accelerator web app. Build context = apps/web.
# Produces a Next.js standalone runtime image running as a non-root user.

# ---- base -------------------------------------------------------------------
FROM node:24-bookworm-slim AS base
ENV PNPM_HOME=/pnpm
ENV PATH=$PNPM_HOME:$PATH
RUN corepack enable && corepack prepare pnpm@11.5.2 --activate
WORKDIR /app

# ---- deps -------------------------------------------------------------------
# Install dependencies against the committed lockfile for deterministic builds.
# pnpm-workspace.yaml carries the pnpm 11 build-script settings and MUST be
# present so `pnpm install --frozen-lockfile` behaves deterministically.
FROM base AS deps
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile --ignore-scripts

# ---- build ------------------------------------------------------------------
FROM base AS build
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm build

# ---- runtime ----------------------------------------------------------------
FROM node:24-bookworm-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

# Run as the unprivileged "node" user that ships with the base image.
USER node

# Next standalone output layout:
#   .next/standalone/server.js        -> app root server
#   .next/standalone/.next/static     -> hashed static assets
#   .next/standalone/public           -> public assets
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
COPY --from=build --chown=node:node /app/public ./public

EXPOSE 3000

# Liveness probe (satisfies Checkov CKV_DOCKER_2). node:24-bookworm-slim ships
# no wget/curl, so probe /health with Node's built-in fetch.
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
  CMD ["node", "-e", "fetch('http://127.0.0.1:3000/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]

CMD ["node", "server.js"]
