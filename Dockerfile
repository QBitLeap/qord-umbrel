FROM rust:1.89.0-bookworm@sha256:948f9b08a66e7fe01b03a98ef1c7568292e07ec2e4fe90d88c07bb14563c84ff AS builder
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential ca-certificates clang cmake git libclang-dev libssl-dev pkg-config python3 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src/qord
COPY protocol/ ./
ENV GIT_BRANCH=main GIT_COMMIT=a4febe49f10eb6ba10ded6ab42098a5bec7be914 CARGO_BUILD_JOBS=2 CMAKE_BUILD_PARALLEL_LEVEL=2
RUN cargo build --locked --release --bin qord
COPY build/collect_notices.py /tmp/collect_notices.py
RUN cargo metadata --locked --format-version=1 > /tmp/cargo-metadata.json \
    && python3 /tmp/collect_notices.py /tmp/cargo-metadata.json /dependency-notices

FROM debian:bookworm-20261104-slim@sha256:c67e92c8099ba22853ab4cfda7cfb494d253d6012ca82dee98ba8976772af018
RUN apt-get update && apt-get install -y --no-install-recommends python3 ca-certificates libssl3 libstdc++6 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /src/qord/target/release/qord /usr/local/bin/qord
COPY protocol/LICENSE protocol/NOTICE /usr/share/doc/qord/
COPY LICENSE NOTICE /usr/share/doc/qord-app/
COPY --from=builder /dependency-notices /usr/share/doc/qord/dependencies
COPY source-manifest.json /usr/share/doc/qord/source-manifest.json
COPY --chmod=0555 app /opt/index-app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp RUST_LOG=info
RUN mkdir -p /data && chown 1000:1000 /data
USER 1000:1000
STOPSIGNAL SIGTERM
ENTRYPOINT ["python3", "/opt/index-app/indexapp.py"]
CMD ["--help"]
