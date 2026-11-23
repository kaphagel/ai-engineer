#!/bin/sh
# Runs inside the worker image (FreeCAD 1.1.4). Each step is a fresh freecadcmd process.
export SPIKE_DIR=/tmp/spike SPIKE_OUT=/tmp/out
mkdir -p "$SPIKE_OUT"
cd /tmp
run() {
    echo "== $1"
    timeout 300 freecadcmd "$SPIKE_DIR/$2" > "$SPIKE_OUT/$1.log" 2>&1 || echo "exit code $?" >> "$SPIKE_OUT/$1.log"
}
run builtin_build builtin_build.py
run builtin_reopen builtin_reopen.py
run scripted_build scripted_build.py
SPIKE_WITH_MODULE=1 run scripted_reopen scripted_reopen.py
SPIKE_WITH_MODULE=0 run scripted_reopen_nomodule scripted_reopen.py
