# Phase 0 spike: FreeCAD 1.1.4 running without user interaction in a container.
FROM debian:bookworm-slim

ARG FREECAD_VERSION=1.1.4
ARG FREECAD_APPIMAGE=FreeCAD_${FREECAD_VERSION}-Linux-x86_64-py311.AppImage
ARG FREECAD_SHA256=f6dc6ba676e5ac96a565ebc8d657232f94c6158e85b4352141bd1a46f6b43434

# Libraries the AppImage expects from the host, plus Xvfb as a fallback for GUI-only operations.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl \
        libgl1 libegl1 libglib2.0-0 libfontconfig1 libfreetype6 libxkbcommon0 libxkbcommon-x11-0 \
        libx11-6 libx11-xcb1 libxcb1 libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
        libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 libxrender1 \
        libxi6 libxext6 libsm6 libice6 libdbus-1-3 \
        xvfb xauth fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt
RUN curl -fsSL -o freecad.AppImage \
        "https://github.com/FreeCAD/FreeCAD/releases/download/${FREECAD_VERSION}/${FREECAD_APPIMAGE}" \
    && echo "${FREECAD_SHA256}  freecad.AppImage" | sha256sum -c - \
    && chmod +x freecad.AppImage \
    && ./freecad.AppImage --appimage-extract > /dev/null \
    && mv squashfs-root freecad \
    && rm freecad.AppImage

ENV PATH="/opt/freecad/usr/bin:${PATH}" \
    QT_QPA_PLATFORM=offscreen

# FreeCAD needs a user with a passwd entry and a home directory; run as non-root.
ARG UID=1000
RUN useradd --create-home --uid ${UID} freecad
USER freecad

WORKDIR /work
