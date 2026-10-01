"""Shared helpers used by every service.

Each service image copies this package (`COPY common/ ./common/`), so the
Docker build context is always the repository root. Keep this package small
and dependency-light: mqtt, buildsim, config, schemas, clock, http.
"""
