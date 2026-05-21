# Pulse frontend — Next.js 16 (standalone output)
FROM node:22-slim AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

FROM node:22-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Next bakes the rewrite destination at build time, so the backend URL must
# be present here. Defaults to the compose service name; override with
#   --build-arg PULSE_BACKEND_URL=https://api.example.com
ARG PULSE_BACKEND_URL=http://backend:8787
ENV PULSE_BACKEND_URL=$PULSE_BACKEND_URL \
    NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-slim AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3030 \
    HOSTNAME=0.0.0.0
# standalone output bundles only what's needed to run
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
EXPOSE 3030
CMD ["node", "server.js"]
