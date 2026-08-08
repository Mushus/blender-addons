FROM python:3.11-slim

ARG BLENDER_MAJOR=5.2
ARG BLENDER_VERSION=5.2.0

WORKDIR /workspace

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        libdbus-1-3 \
        libegl1 \
        libfontconfig1 \
        libgl1 \
        libgl1-mesa-dri \
        libgomp1 \
        libice6 \
        libsm6 \
        libwayland-client0 \
        libwayland-egl1 \
        libx11-6 \
        libxcursor1 \
        libxfixes3 \
        libxi6 \
        libxkbcommon0 \
        libxrender1 \
        libxxf86vm1 \
        mesa-utils \
        imagemagick \
        xauth \
        xvfb \
        xz-utils \
    && rm -rf /var/lib/apt/lists/*

COPY .blender-cache* /tmp/blender-cache/
RUN if [ -f "/tmp/blender-cache/blender-${BLENDER_VERSION}-linux-x64.tar.xz" ]; then \
        echo "Using cached Blender archive: /tmp/blender-cache/blender-${BLENDER_VERSION}-linux-x64.tar.xz" \
        && cp "/tmp/blender-cache/blender-${BLENDER_VERSION}-linux-x64.tar.xz" /tmp/blender.tar.xz; \
    elif [ -f "/tmp/blender-cache/blender.tar.xz" ]; then \
        echo "Using cached /tmp/blender-cache/blender.tar.xz" \
        && cp "/tmp/blender-cache/blender.tar.xz" /tmp/blender.tar.xz; \
    else \
        echo "Downloading Blender ${BLENDER_VERSION}..." \
        && curl -fsSL "https://download.blender.org/release/Blender${BLENDER_MAJOR}/blender-${BLENDER_VERSION}-linux-x64.tar.xz" -o /tmp/blender.tar.xz; \
    fi \
    && tar -xJf /tmp/blender.tar.xz -C /opt \
    && mv /opt/blender-*linux-x64 /opt/blender \
    && ln -s /opt/blender/blender /usr/local/bin/blender \
    && rm -rf /tmp/blender.tar.xz /tmp/blender-cache

ENV LIBGL_ALWAYS_SOFTWARE=1
ENV GALLIUM_DRIVER=llvmpipe

COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY . .
CMD ["python", "./scripts/run_ci.py"]
