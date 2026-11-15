# Build the Vite app, then serve it with Caddy, which also proxies /api to the
# backend container. Build context is frontend/.
#   docker build frontend
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Empty VITE_API_URL = call /api relative to the page (Caddy proxies it).
RUN npm run build

FROM caddy:2.10-alpine
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
EXPOSE 80 443
