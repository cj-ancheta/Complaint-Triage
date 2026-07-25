FROM postgres:18.4-alpine3.23@sha256:996d0920e4ff9df1fc19dacb904492f3c1ec0ec1cc338f0ad7123be7731c5f5e

# The upstream digest predates fixed Alpine packages reported by QA-105.
# Rebuilds intentionally fail closed if the pinned repository cannot supply
# current packages; the resulting image is scanned before use in CI.
RUN apk upgrade --no-cache
