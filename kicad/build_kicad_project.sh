#!/usr/bin/env bash
#
# build_kicad_project.sh
#
# Regenerates the complete KiCad project (schematic + PCB + project file) from
# the ergogen output. Ergogen only produces a .kicad_pcb (with footprints and
# net connectivity but no schematic), so this:
#   1. copies the generated PCB into kicad/keyboard.kicad_pcb
#   2. generates kicad/keyboard.kicad_sch from the PCB netlist (symbols + global
#      net labels) using gen_schematic.py (requires KiCad's python / pcbnew)
#   3. leaves kicad/keyboard.kicad_pro in place to tie them together
#
# Requires KiCad installed (pcbnew python module + kicad-cli).
#
# Usage: ./kicad/build_kicad_project.sh

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PCB_SRC="output/pcbs/main.kicad_pcb"
if [ ! -f "$PCB_SRC" ]; then
  echo "Missing $PCB_SRC. Run ergogen first (see README)." >&2
  exit 1
fi

echo "==> Copying PCB into project"
cp "$PCB_SRC" kicad/keyboard.kicad_pcb

echo "==> Generating schematic from PCB netlist"
python3 kicad/gen_schematic.py "$PCB_SRC" kicad keyboard \
  2>/dev/null || python3 kicad/gen_schematic.py "$PCB_SRC" kicad keyboard

echo "==> Rendering schematic PDF (optional, proves it opens)"
kicad-cli sch export pdf kicad/keyboard.kicad_sch \
  -o kicad/keyboard-schematic.pdf >/dev/null 2>&1 || \
  echo "   (PDF export skipped)"

echo "==> Done. Open kicad/keyboard.kicad_pro in KiCad."
