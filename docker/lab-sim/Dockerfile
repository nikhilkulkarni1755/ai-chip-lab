# syntax=docker/dockerfile:1
# lab-sim: simulation / formal / synthesis / architecture-model image for the AI-chip lab (TASK.md §3).
# Build (from the repo root):  scripts/infra_build_lab_sim.sh
# Every external input is pinned: base image by digest, tarballs by URL + SHA256, Python deps by
# hash-locked docker/requirements.lock. (Ubuntu apt packages are pinned by the base digest's release
# only; the versions actually installed are printed by docker/smoke.sh and saved to versions.lock.)

ARG UBUNTU_REF=ubuntu:22.04@sha256:5ec03bb3441e8b0bf3b4f9cd4629a1ae763010dc3035bb8da3ae6cf026486401

# ---- pinned downloads (kept out of the final image layers) -------------------------------------
FROM scratch AS dl
ARG OSS_CAD_DATE=2026-09-28
ARG OSS_CAD_FILE=oss-cad-suite-linux-x64-20260928.tgz
ARG OSS_CAD_SHA256=6d04cf3e36c45d4eacbe2fa07f3860b9a86f503c2b725bdee4d02e54defbf80d
ARG VERIBLE_VER=v0.0-4296-g0f262651
ARG VERIBLE_SHA256=8569defb891d2316067613ea00442af28a7a09d405d95b54c0c91f9942d26635
ARG UV_VER=0.13.0
ARG UV_SHA256=1468ebd5a5541121837c5a2817b9972ba6090fa6caa3d142620850a47fb75154
ADD --checksum=sha256:${OSS_CAD_SHA256} \
    https://github.com/YosysHQ/oss-cad-suite-build/releases/download/${OSS_CAD_DATE}/${OSS_CAD_FILE} /oss-cad-suite.tgz
ADD --checksum=sha256:${VERIBLE_SHA256} \
    https://github.com/chipsalliance/verible/releases/download/${VERIBLE_VER}/verible-${VERIBLE_VER}-linux-static-x86_64.tar.gz /verible.tar.gz
ADD --checksum=sha256:${UV_SHA256} \
    https://github.com/astral-sh/uv/releases/download/${UV_VER}/uv-x86_64-unknown-linux-gnu.tar.gz /uv.tar.gz

# ---- final image -------------------------------------------------------------------------------
FROM ${UBUNTU_REF}
ARG PYTHON_VER=3.12.15
ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 LC_ALL=C.UTF-8
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl make g++ git perl time \
 && rm -rf /var/lib/apt/lists/*

# OSS CAD Suite: yosys, abc, verilator, iverilog, sby, eqy, smtbmc, boolector, bitwuzla, yices, z3, ghdl, nextpnr, gtkwave
RUN --mount=type=bind,from=dl,source=/oss-cad-suite.tgz,target=/tmp/oss-cad-suite.tgz \
    tar -xzf /tmp/oss-cad-suite.tgz -C /opt
# Verible
RUN --mount=type=bind,from=dl,source=/verible.tar.gz,target=/tmp/verible.tar.gz \
    mkdir -p /opt/verible && tar -xzf /tmp/verible.tar.gz -C /opt/verible --strip-components=1
# uv + a uv-managed CPython (ships libpython, which cocotb needs) + hash-locked packages
RUN --mount=type=bind,from=dl,source=/uv.tar.gz,target=/tmp/uv.tar.gz \
    tar -xzf /tmp/uv.tar.gz -C /usr/local/bin --strip-components=1
ENV UV_PYTHON_INSTALL_DIR=/opt/python UV_LINK_MODE=copy UV_NO_CACHE=1 UV_PYTHON_DOWNLOADS=manual
RUN uv python install ${PYTHON_VER} && uv venv /opt/venv --python ${PYTHON_VER}
COPY requirements.lock /opt/requirements.lock
RUN VIRTUAL_ENV=/opt/venv uv pip install --require-hashes --no-deps -r /opt/requirements.lock

# Shims that must precede the suite on PATH (see docker/lab-sim/bin/vvp for why)
COPY lab-sim/bin/ /opt/lab-bin/
# venv first so `python3` is the lab's 3.12 (the suite bundles its own private python for sby/eqy)
ENV VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:/opt/lab-bin:/opt/oss-cad-suite/bin:/opt/verible/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 MPLBACKEND=Agg \
    OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 NUMBA_NUM_THREADS=2 \
    NUMBA_CACHE_DIR=/tmp/numba MPLCONFIGDIR=/tmp/mpl HOME=/tmp
WORKDIR /lab
