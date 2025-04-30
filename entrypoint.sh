#!/bin/sh
set -e

chown -R ${PUID}:${PGID} /app/LimitedMediaServer/instance
su-exec ${PUID}:${PGID} /app/LimitedMediaServer/site-packages/bin/alembic upgrade head
exec su-exec ${PUID}:${PGID} "$@"
