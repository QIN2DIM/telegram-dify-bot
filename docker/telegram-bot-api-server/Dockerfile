# Telegram Bot API Server Dockerfile
FROM alpine:3.19

ARG PROXY_URL=http://192.168.1.8:2081
ENV http_proxy=$PROXY_URL \
    https_proxy=$PROXY_URL \
    all_proxy=$PROXY_URL

# Install build dependencies
RUN apk add --no-cache \
    alpine-sdk \
    linux-headers \
    git \
    cmake \
    gperf \
    openssl-dev \
    zlib-dev

# Clone and build telegram-bot-api
WORKDIR /build
RUN git clone --recursive https://github.com/tdlib/telegram-bot-api.git && \
    cd telegram-bot-api && \
    mkdir build && \
    cd build && \
    cmake -DCMAKE_BUILD_TYPE=Release .. && \
    cmake --build . --target install && \
    cd / && \
    rm -rf /build

# Create working directory
WORKDIR /var/lib/telegram-bot-api

# Expose the default port
EXPOSE 8081

# Create volume for persistent data
VOLUME ["/var/lib/telegram-bot-api"]

ENV http_proxy="" \
    https_proxy="" \
    all_proxy=""

# Default command with required parameters
# Note: API_ID and API_HASH must be provided via environment variables
ENTRYPOINT ["telegram-bot-api"]
CMD ["--local", "--dir=/var/lib/telegram-bot-api"]