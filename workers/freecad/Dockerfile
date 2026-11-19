# FreeCAD CAD worker (spec §12.6, ADR-0001). Runs one job: /job/job.json in, /job/out/ out.
FROM debian:bookworm-slim

ARG FREECAD_VERSION=1.1.4
ARG FREECAD_APPIMAGE=FreeCAD_${FREECAD_VERSION}-Linux-x86_64-py311.AppImage
ARG FREECAD_SHA256=f6dc6ba676e5ac96a565ebc8d657232f94c6158e85b4352141bd1a46f6b43434

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl \
        libgl1 libegl1 libglib2.0-0 libfontconfig1 libfreetype6 libxkbcommon0 libxkbcommon-x11-0 \
        libx11-6 libx11-xcb1 libxcb1 libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
        libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 libxrender1 \
        libxi6 libxext6 libsm6 libice6 libdbus-1-3 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt
RUN curl -fsSL -o freecad.AppImage \
        "https://github.com/FreeCAD/FreeCAD/releases/download/${FREECAD_VERSION}/${FREECAD_APPIMAGE}" \
    && echo "${FREECAD_SHA256}  freecad.AppImage" | sha256sum -c - \
    && chmod +x freecad.AppImage \
    && ./freecad.AppImage --appimage-extract > /dev/null \
    && mv squashfs-root freecad \
    && rm freecad.AppImage

# PDF export needs the GUI binary; offscreen Qt needs no display (ADR-0001).
ENV PATH="/opt/freecad/usr/bin:${PATH}" \
    QT_QPA_PLATFORM=offscreen \
    IAIEP_JOB_DIR=/job

# FreeCAD needs a user with a passwd entry and a home directory.
ARG UID=1000
RUN useradd --create-home --uid ${UID} freecad \
    && mkdir -p /job/out && chown -R freecad /job

COPY run_job.sh main.py export_pdf.py configure_freecad.py /opt/worker/
COPY iaiep_worker /opt/worker/iaiep_worker

USER freecad
# Fails the build if the preferences were not written (the GUI deadlocks without them, ADR-0001).
RUN freecadcmd /opt/worker/configure_freecad.py \
    && grep -q '"NotificationAreaEnabled" Value="0"' /home/freecad/.config/FreeCAD/v1-1/user.cfg
WORKDIR /job
CMD ["sh", "/opt/worker/run_job.sh"]
