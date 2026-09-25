# Wheel builder: Python 3.15 (musl, arm64) + the toolchain and -dev packages Home Assistant's own wheel
# workflow uses (home-assistant/core .github/workflows/wheels.yml, "integrations" job), so the same sdists compile.
# Every package name below was checked to exist on Alpine 3.24 (2026-09-25).
ARG PY_IMAGE=python:3.15.0rc2-alpine3.24
FROM ${PY_IMAGE}
RUN apk add --no-cache build-base linux-headers pkgconf cmake ninja git rust cargo autoconf automake libtool meson \
      bluez-dev libffi-dev openssl-dev glib-dev eudev-dev libxml2-dev libxslt-dev libpng-dev libjpeg-turbo-dev \
      tiff-dev gmp-dev mpfr-dev mpc1-dev ffmpeg-dev yaml-dev openblas-dev fftw-dev lapack-dev gfortran blas-dev \
      eigen-dev freetype-dev harfbuzz-dev hdf5-dev openjpeg-dev uchardet-dev nasm zlib-ng-dev zlib-dev c-ares-dev \
      libusb-dev cups-dev postgresql-dev mariadb-dev unixodbc-dev bzip2-dev xz-dev \
 && pip install -q -U pip wheel setuptools cython
ENV MAKEFLAGS=-j4 CARGO_BUILD_JOBS=4 CMAKE_BUILD_PARALLEL_LEVEL=4 GRPC_PYTHON_BUILD_EXT_COMPILER_JOBS=4 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_PREFER_BINARY=1
