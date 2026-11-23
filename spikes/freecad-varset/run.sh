#!/bin/sh
# Runs the spike in the FreeCAD worker image. Files are copied in and out with docker cp (no bind
# mounts, so this also works from the Dev Container with Docker outside of Docker).
set -e
cd "$(dirname "$0")"
IMAGE="${IMAGE:-iaiep-freecad-worker:dev}"
cid=$(docker create "$IMAGE" sh /tmp/spike/in_container.sh)
trap 'docker rm -f "$cid" > /dev/null' EXIT
tar -cf - --transform 's,^,spike/,' common.py fchelp.py builtin_build.py builtin_reopen.py scripted_build.py scripted_reopen.py in_container.sh feature \
    | docker cp - "$cid:/tmp"
docker start -a "$cid"
rm -rf out
docker cp "$cid:/tmp/out" out
echo "Results in $(pwd)/out"
