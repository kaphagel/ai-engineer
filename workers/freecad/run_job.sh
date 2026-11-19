#!/bin/sh
# Phase 1: model, checks, drawing page and exports without GUI. Phase 2: PDF export with the GUI binary.
# The timeouts stop a hung FreeCAD process; the platform also enforces an overall timeout.
set -e
timeout 600 freecadcmd /opt/worker/main.py
timeout 300 freecad /opt/worker/export_pdf.py
