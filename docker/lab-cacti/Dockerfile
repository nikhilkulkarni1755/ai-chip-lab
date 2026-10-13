# syntax=docker/dockerfile:1
# lab-cacti: CACTI 7 (SRAM/cache area, energy, access-time model) for stage 63_sram_cacti (TASK2 P2.4).
# Source: the official repository github.com/HewlettPackard/cacti, pinned by git commit SHA (content-addressed:
# the build fetches exactly that commit and fails if HEAD is anything else). Base image pinned by digest (same as lab-sim).
# Build: scripts/infra_build_cacti.sh        Use: docker run --rm -v $LAB:/lab -w /opt/cacti <image> ./cacti -infile /lab/<cfg>
ARG UBUNTU_REF=ubuntu:22.04@sha256:5ec03bb3441e8b0bf3b4f9cd4629a1ae763010dc3035bb8da3ae6cf026486401
FROM ${UBUNTU_REF}
ARG CACTI_REPO=https://github.com/HewlettPackard/cacti.git
ARG CACTI_SHA=1ffd8dfb10303d306ecd8d215320aea07651e878
ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 LC_ALL=C.UTF-8
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates git make g++ \
 && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /opt/cacti && cd /opt/cacti \
 && git init -q . && git remote add origin "${CACTI_REPO}" \
 && git fetch -q --depth 1 origin "${CACTI_SHA}" && git checkout -q FETCH_HEAD \
 && test "$(git rev-parse HEAD)" = "${CACTI_SHA}" \
 && make -j2 2>&1 | tail -5 \
 && test -x ./cacti \
 && echo "${CACTI_SHA}" > /opt/cacti/CACTI_COMMIT
# CACTI reads its technology files and writes <cfg>.out next to the config; run it from /opt/cacti.
WORKDIR /opt/cacti
ENV PATH=/opt/cacti:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin HOME=/tmp
