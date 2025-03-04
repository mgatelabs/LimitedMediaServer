# Frontend
FROM alpine:latest AS frontedbuilder

WORKDIR /app

# deps for building LimitedMediaServerSite
RUN apk update && apk upgrade --no-cache && \
    apk --no-cache add ca-certificates nodejs git npm

# src
COPY ./LimitedMediaServerSite ./LimitedMediaServerSite

# build LimitedMediaServerSite
RUN cd LimitedMediaServerSite && \
    npm install && \
    npm run build

# Backend
FROM alpine:latest AS backendbuilder

WORKDIR /app

# deps for building LimitedMediaServer
RUN apk update && apk upgrade --no-cache && \
    apk --no-cache add ca-certificates python3 py3-pip build-base linux-headers python3-dev

# src
COPY ./LimitedMediaServer ./LimitedMediaServer

# build LimitedMediaServer
RUN cd LimitedMediaServer && \
    pip install --no-cache-dir -t /app/LimitedMediaServer/site-packages -r requirements.txt && \
    chmod 755 entrypoint.sh

# Final
FROM alpine:latest

WORKDIR /app/LimitedMediaServer

# deps for running LimitedMediaServer
RUN apk update && apk upgrade --no-cache && \
    apk --no-cache add python3 py3-psutil ffmpeg su-exec && rm -rf /var/cache/apk/*

COPY --from=backendbuilder /app/LimitedMediaServer /app/LimitedMediaServer
COPY --from=frontedbuilder /app/LimitedMediaServer/static /app/LimitedMediaServer/static

ENV PYTHONPATH=/app/LimitedMediaServer/site-packages PUID=0 PGID=0
EXPOSE 5000
VOLUME /app/LimitedMediaServer/instance

ENTRYPOINT [ "/app/LimitedMediaServer/entrypoint.sh" ]
CMD [ "python3", "server.py" ]
