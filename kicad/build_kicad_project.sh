#!/usr/bin/env bash
#
# build_kicad_project.sh
#
# Regenerates the KiCad project(s) from the ergogen output for a split board.
# Ergogen produces output/pcbs/main_left.kicad_pcb and main_right.kicad_pcb
# (footprints + net connectivity, no schematic). For the requested half this:
#   1. copies the generated PCB into kicad/<half>/keyboard.kicad_pcb
#   2. generates kicad/<half>/keyboard.kicad_sch from the PCB netlist
#   3. leaves kicad/<half>/keyboard.kicad_pro / .kicad_dru in place
#
# IMPORTANT: this OVERWRITES the .kicad_pcb for the chosen half, discarding any
# routing done in KiCad. Only run it for a half you intend to (re)generate from
# scratch. The left half is already routed; re-running 'left' will wipe that.
#
# Requires KiCad installed (pcbnew python module + kicad-cli).
#
# Usage:
#   ./kicad/build_kicad_project.sh right      # (re)generate the right half
#   ./kicad/build_kicad_project.sh left        # WARNING: wipes routed left
#   ./kicad/build_kicad_project.sh both

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

build_half() {
  local half="$1"
  local PCB_SRC="output/pcbs/main_${half}.kicad_pcb"
  local DIR="kicad/${half}"

  if [ ! -f "$PCB_SRC" ]; then
    echo "Missing $PCB_SRC. Run ergogen first (see README)." >&2
    exit 1
  fi
  mkdir -p "$DIR"
  # ensure the shared 3D-model symlink exists for ${KIPRJMOD}/3d_models paths
  [ -e "$DIR/3d_models" ] || ln -s ../3d_models "$DIR/3d_models"

  echo "==> [$half] Copying PCB into project"
  cp "$PCB_SRC" "$DIR/keyboard.kicad_pcb"

  echo "==> [$half] Generating schematic from PCB netlist"
  python3 kicad/gen_schematic.py "$PCB_SRC" "$DIR" keyboard \
    2>/dev/null || python3 kicad/gen_schematic.py "$PCB_SRC" "$DIR" keyboard

  echo "==> [$half] Rendering schematic PDF"
  kicad-cli sch export pdf "$DIR/keyboard.kicad_sch" \
    -o "$DIR/keyboard-schematic.pdf" >/dev/null 2>&1 || \
    echo "   (PDF export skipped)"

  echo "==> [$half] Done. Open $DIR/keyboard.kicad_pro in KiCad."
}

case "${1:-}" in
  left)  build_half left ;;
  right) build_half right ;;
  both)  build_half left; build_half right ;;
  *)
    echo "Usage: $0 {left|right|both}" >&2
    echo "  WARNING: 'left' overwrites the already-routed left PCB." >&2
    exit 1
    ;;
esac
