FROM node:22-alpine AS build

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
# Cache npm tarballs on the host so repeated `npm ci` does not re-download.
RUN --mount=type=cache,target=/root/.npm npm ci
COPY frontend/ ./
RUN --mount=type=cache,target=/root/.npm npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine

COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
