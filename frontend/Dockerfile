# Stage 0, build the React workbench with the lockfile used in local verification.
FROM node:25-bookworm-slim AS build-stage

WORKDIR /app

COPY package.json package-lock.json /app/

COPY frontend/package.json /app/frontend/

WORKDIR /app/frontend

RUN npm ci --workspace frontend

COPY ./frontend /app/frontend
ARG VITE_API_URL

RUN npm run build --workspace frontend


# Stage 1, based on Nginx, to have only the compiled app, ready for production with Nginx
FROM nginx:1

COPY --from=build-stage /app/frontend/dist/ /usr/share/nginx/html

COPY ./frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY ./frontend/nginx-backend-not-found.conf /etc/nginx/extra-conf.d/backend-not-found.conf
