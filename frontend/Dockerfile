# The page, built with Node and served by nginx, which also passes /api to the backend.
# Base images are pinned by digest, so a build gets exactly the image that was checked.

# The Node version in .nvmrc.
FROM node:26.12.1-alpine3.24@sha256:40cd011b55415bc894e45b02fdd5a5dfde056921b7d23a64c74f80497af48797 AS build
WORKDIR /app
# The dependencies first, in a layer that is built again only when they change.
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY index.html tsconfig.json tsconfig.app.json tsconfig.node.json vite.config.ts ./
COPY src ./src
# Copied into the build as they are, such as theme-init.js, which index.html loads by its own name.
COPY public ./public
RUN npm run build

# nginx as an unprivileged user, which is why it listens on 8080.
FROM nginxinc/nginx-unprivileged:1.30.6-alpine3.24@sha256:f5116ed4606f3eb015dd4a8e28cb9b351476dc0ad4bc6e9f93b19cec130cdf03
# Without the pages nginx comes with, so that only the app is served.
USER root
RUN rm -rf /usr/share/nginx/html/*
USER 101
COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD ["curl", "-fsS", "-o", "/dev/null", "http://127.0.0.1:8080/"]
