---
name: docker-patterns
description: Dockerfile and container practices covering multi-stage builds, base image pinning, layer caching, non-root users, secrets handling, healthchecks, and image size. Use when writing or reviewing a Dockerfile, docker-compose file, or container build in CI.
---

# Docker Patterns

## Base image
- Pin a specific version tag. Use a digest for release builds. Never `latest`.
- Prefer slim or distroless runtime images when the app does not need a shell or compilers.

## Multi-stage builds
- Build in one stage with the compilers and dev dependencies. Copy only the artifact into a minimal runtime stage.

```dockerfile
FROM node:20.11-bookworm-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build && npm prune --omit=dev

FROM node:20.11-bookworm-slim
WORKDIR /app
COPY --from=build /app/dist ./dist
COPY --from=build /app/node_modules ./node_modules
USER node
CMD ["node", "dist/server.js"]
```

Confirm the tags exist on the registry before committing them.

## Layer caching
- Copy dependency manifests and install before copying source. Source changes then do not reinstall packages.
- Order instructions from least to most frequently changed.

## Security
- Run as a non-root user: `USER` with a numeric UID is safest.
- Never put secrets in `ENV`, `ARG`, or copied files. They persist in image history. Pass them at runtime or use BuildKit secret mounts (`RUN --mount=type=secret`).
- Add a `.dockerignore` that excludes `.git`, `.env`, `node_modules`, and local build output.
- Scan images in CI with the scanner the project already uses.

## Runtime
- Use exec form for `CMD` and `ENTRYPOINT` (`["node", "server.js"]`) so signals reach the process.
- Add a `HEALTHCHECK` when the orchestrator does not provide its own probe.
- Set memory and CPU limits in compose or the orchestrator.

## Compose
- Use named volumes for data. Do not bind-mount over the image's dependency directories.
- Read configuration from an env file that is not committed.

## Review checklist
- Tag pinned. Runs as non-root. No secrets in layers. `.dockerignore` present. Signals handled. Image size checked (`docker image ls`).
