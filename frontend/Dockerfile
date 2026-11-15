# Three stages: install, build, run. Only the last one is shipped, so the final image has no
# build tools and no dev dependencies.
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
# npm ci installs exactly what the lockfile says (the same as CI does).
RUN --mount=type=cache,target=/root/.npm npm ci

FROM node:22-alpine AS build
WORKDIR /app
# NEXT_PUBLIC_* values are compiled into the JavaScript the browser downloads, so the API
# address is fixed at BUILD time, not when the container starts. It is the address the
# BROWSER uses to reach the API (not the one between containers).
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS run
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
# The standalone output holds server.js; static files and public/ are copied next to it
# because the standalone build does not include them.
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
# Do not run as root inside the container (the node image ships a "node" user).
USER node
EXPOSE 3000
CMD ["node", "server.js"]
