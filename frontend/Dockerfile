# Build the Vite app, then serve it with nginx, which also proxies /api to the
# backend container. Build context is frontend/.
#   docker build frontend
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Empty VITE_API_URL = call /api relative to the page (nginx proxies it).
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
