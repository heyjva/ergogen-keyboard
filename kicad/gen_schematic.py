#!/usr/bin/env python3
"""
gen_schematic.py  (v2 - properly wired)

Generates a connected KiCad schematic (.kicad_sch) from the ergogen .kicad_pcb.
Each mapped footprint becomes a real symbol (full definition embedded in
lib_symbols). For every connected pad we draw a short wire from the pin's
endpoint to a global net label, so the schematic is electrically connected
(ERC-clean nets), laid out on a grid.

Usage (with KiCad's python):
    python3 gen_schematic.py <board.kicad_pcb> <out_dir> <project_name>
"""

import sys
import re
import uuid
import pcbnew

SYM_LIBS = "/usr/share/kicad/symbols"

# footprint id -> (lib_id, symbol-file, symbol-name, {pad: pin_number}, ref)
SYMBOL_MAP = {
    "ceoloide:switch_choc_v1_v2": (
        "Switch:SW_Push", "Switch", "SW_Push", {"1": "1", "2": "2"}, "SW"),
    "ceoloide:diode_tht_sod123": (
        "Device:D", "Device", "D", {"1": "2", "2": "1"}, "D"),
    "ceoloide:encoder_evqwgd001": (
        "Device:RotaryEncoder_Switch", "Device", "RotaryEncoder_Switch",
        {"A": "1", "C": "2", "B": "3", "1": "4", "2": "5", "D": "3"}, "ENC"),
    "ceoloide:battery_connector_jst_ph_2": (
        "Connector:Conn_01x02_Pin", "Connector", "Conn_01x02_Pin",
        {"1": "1", "2": "2"}, "J"),
    "ceoloide:power_switch_smd_side": (
        "Switch:SW_SPDT", "Switch", "SW_SPDT",
        {"1": "1", "2": "2", "3": "3"}, "SW"),
    "ceoloide:reset_switch_tht_top": (
        "Switch:SW_Push", "Switch", "SW_Push", {"1": "1", "2": "2"}, "SW"),
    "ceoloide:mcu_nice_nano": (
        "Connector_Generic:Conn_02x12_Odd_Even", "Connector_Generic",
        "Conn_02x12_Odd_Even", {str(i): str(i) for i in range(1, 25)}, "U"),
}


def uid():
    return str(uuid.uuid4())


def esc(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


def get_symbol_block(libfile, symname):
    data = open(libfile).read()
    key = f'(symbol "{symname}"'
    i = data.find(key)
    if i < 0:
        return None
    depth = 0
    j = i
    while j < len(data):
        if data[j] == '(':
            depth += 1
        elif data[j] == ')':
            depth -= 1
            if depth == 0:
                return data[i:j + 1]
        j += 1
    return None


def pin_positions(block):
    out = {}
    for m in re.finditer(
        r'\(pin\s+\S+\s+\S+\s*\(at ([\-\d.]+) ([\-\d.]+) (\d+)\)(.*?)\(number "([^"]+)"',
        block, re.S,
    ):
        num = m.group(5)
        if num not in out:
            out[num] = (float(m.group(1)), float(m.group(2)), int(m.group(3)))
    return out


def rot(x, y, angle):
    # rotate point (x,y) by angle degrees (0/90/180/270)
    if angle == 0:
        return x, y
    if angle == 90:
        return -y, x
    if angle == 180:
        return -x, -y
    if angle == 270:
        return y, -x
    return x, y


def main():
    board_path, out_dir, proj = sys.argv[1], sys.argv[2], sys.argv[3]
    board = pcbnew.LoadBoard(board_path)

    comps = []
    for fp in board.GetFootprints():
        fpid = fp.GetFPIDAsString()
        if fpid not in SYMBOL_MAP:
            continue
        ref = fp.GetReference()
        pads = {}
        for pad in fp.Pads():
            n = pad.GetName()
            if n:
                pads.setdefault(n, pad.GetNetname())
        comps.append((ref, fpid, fp.GetValue(), pads))
    comps.sort(key=lambda c: (c[1], int(re.sub(r"\D", "", c[0]) or 0)))

    # Cache symbol blocks + pin positions.
    sym_cache = {}
    for lib_id, libf, symname, padmap, refp in SYMBOL_MAP.values():
        if lib_id in sym_cache:
            continue
        blk = get_symbol_block(f"{SYM_LIBS}/{libf}.kicad_sym", symname)
        if blk is None:
            print(f"WARN: symbol {symname} not found", file=sys.stderr)
            continue
        # Re-key the embedded symbol's top name to the lib_id (KiCad expects
        # lib_symbols entries keyed as "Lib:Name").
        blk2 = re.sub(r'\(symbol "' + re.escape(symname) + r'"',
                      f'(symbol "{lib_id}"', blk, count=1)
        sym_cache[lib_id] = (blk2, pin_positions(blk))

    lib_symbols = "\n".join(v[0] for v in sym_cache.values())

    body = []
    x0, y0 = 30.0, 30.0
    dx, dy = 50.8, 40.64
    per_row = 8
    for idx, (ref, fpid, value, pads) in enumerate(comps):
        lib_id, libf, symname, padmap, refp = SYMBOL_MAP[fpid]
        if lib_id not in sym_cache:
            continue
        _, pinpos = sym_cache[lib_id]
        col = idx % per_row
        row = idx // per_row
        sx = round((x0 + col * dx) / 1.27) * 1.27
        sy = round((y0 + row * dy) / 1.27) * 1.27

        body.append(
            f'''  (symbol (lib_id "{lib_id}") (at {sx:.2f} {sy:.2f} 0) (unit 1)
    (in_bom yes) (on_board yes) (dnp no) (uuid {uid()})
    (property "Reference" "{esc(ref)}" (at {sx-2.54:.2f} {sy-17.78:.2f} 0)
      (effects (font (size 1.27 1.27)) (justify left)))
    (property "Value" "{esc(value or symname)}" (at {sx-2.54:.2f} {sy+17.78:.2f} 0)
      (effects (font (size 1.27 1.27)) (justify left)))
    (property "Footprint" "{esc(fpid)}" (at {sx:.2f} {sy:.2f} 0)
      (effects (font (size 1.27 1.27)) hide))
  )'''
        )

        # For each connected pad, draw a wire from the pin endpoint outward and
        # place a global label at the wire end.
        for pad_name, net in pads.items():
            if not net:
                continue
            pin_num = padmap.get(pad_name)
            if pin_num is None or pin_num not in pinpos:
                continue
            px, py, pangle = pinpos[pin_num]
            # symbol placed at angle 0, but KiCad Y is inverted in schematic
            # coordinates relative to symbol lib Y; mirror Y.
            wx = sx + px
            wy = sy - py
            # extend outward along pin direction (pangle: 0 points left in lib =>
            # endpoint is the connection point; wire goes further out).
            ext = 5.08
            if pangle == 0:      # pin body to the right, endpoint at left
                lx, ly = wx - ext, wy
                just = "right"
            elif pangle == 180:  # endpoint at right
                lx, ly = wx + ext, wy
                just = "left"
            elif pangle == 90:
                lx, ly = wx, wy + ext
                just = "left"
            else:                # 270
                lx, ly = wx, wy - ext
                just = "left"
            body.append(
                f'''  (wire (pts (xy {wx:.2f} {wy:.2f}) (xy {lx:.2f} {ly:.2f}))
    (stroke (width 0) (type default)) (uuid {uid()}))'''
            )
            body.append(
                f'''  (global_label "{esc(net)}" (shape passive) (at {lx:.2f} {ly:.2f} 0)
    (effects (font (size 1.27 1.27)) (justify {just}))
    (uuid {uid()}))'''
            )

    sch = f'''(kicad_sch (version 20231120) (generator "ergogen_schematic_gen")
  (uuid {uid()})
  (paper "A1")
  (lib_symbols
{lib_symbols}
  )
{chr(10).join(body)}
  (sheet_instances (path "/" (page "1")))
)
'''
    path = f"{out_dir}/{proj}.kicad_sch"
    with open(path, "w") as f:
        f.write(sch)
    print(f"wrote {path} ({len(comps)} symbols)")


if __name__ == "__main__":
    main()
