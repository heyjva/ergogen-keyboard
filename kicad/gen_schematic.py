#!/usr/bin/env python3
"""
gen_schematic.py  (v3 - organized layout)

Generates a cleaner KiCad schematic (.kicad_sch) from the ergogen .kicad_pcb.
Instead of a flat grid dump, it lays out:
  - The switch matrix as a proper grid (switch + series diode per cell, aligned
    by column/row), with COLn labels along the top and ROWn labels along the
    left, matching how hand-drawn keyboard schematics look.
  - The nice!nano, encoder, battery/power/reset in separate labelled areas.

Connectivity uses local/global net labels on aligned pins (correct + ERC-
readable). It won't match a hand-polished schematic, but is far tidier than a
raw dump.

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
        {"A": "A", "C": "C", "B": "B", "1": "S1", "2": "S2", "D": "B"}, "ENC"),
    "ceoloide:battery_connector_jst_ph_2": (
        "Connector:Conn_01x02_Pin", "Connector", "Conn_01x02_Pin",
        {"1": "1", "2": "2"}, "J"),
    "ceoloide:power_switch_smd_side": (
        "Switch:SW_SPDT", "Switch", "SW_SPDT",
        {"1": "1", "2": "2", "3": "3"}, "SW"),
    "ceoloide:reset_switch_tht_top": (
        "Switch:SW_Push", "Switch", "SW_Push", {"1": "1", "2": "2"}, "SW"),
    "ceoloide:reset_switch_smd_side": (
        "Switch:SW_Push", "Switch", "SW_Push", {"1": "1", "2": "2"}, "SW"),
    "ceoloide:mcu_nice_nano": (
        "Connector_Generic:Conn_02x12_Odd_Even", "Connector_Generic",
        "Conn_02x12_Odd_Even", {str(i): str(i) for i in range(1, 25)}, "U"),
}

COLS = ["P15", "P16", "P17", "P18", "P19", "P20", "P21"]
ROWS = ["P11", "P12", "P13", "P14", "P2"]


def uid():
    return str(uuid.uuid4())


def esc(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


def snap(v):
    return round(v / 1.27) * 1.27


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


class Sch:
    def __init__(self):
        self.items = []
        self.sym_cache = {}

    def load_symbol(self, lib_id):
        if lib_id in self.sym_cache:
            return self.sym_cache[lib_id]
        libf, symname = None, None
        for _lib_id, _libf, _sym, *_ in SYMBOL_MAP.values():
            if _lib_id == lib_id:
                libf, symname = _libf, _sym
                break
        blk = get_symbol_block(f"{SYM_LIBS}/{libf}.kicad_sym", symname)
        blk2 = re.sub(r'\(symbol "' + re.escape(symname) + r'"',
                      f'(symbol "{lib_id}"', blk, count=1)
        self.sym_cache[lib_id] = (blk2, pin_positions(blk), symname)
        return self.sym_cache[lib_id]

    def symbol(self, lib_id, ref, value, x, y, angle=0, mirror=None):
        _, pinpos, symname = self.load_symbol(lib_id)
        x, y = snap(x), snap(y)
        mstr = f" (mirror {mirror})" if mirror else ""
        self.items.append(
            f'''  (symbol (lib_id "{lib_id}") (at {x:.2f} {y:.2f} {angle}){mstr} (unit 1)
    (in_bom yes) (on_board yes) (dnp no) (uuid {uid()})
    (property "Reference" "{esc(ref)}" (at {x:.2f} {y-10.16:.2f} 0)
      (effects (font (size 1.27 1.27))))
    (property "Value" "{esc(value)}" (at {x:.2f} {y+10.16:.2f} 0)
      (effects (font (size 1.27 1.27))))
  )'''
        )
        return (x, y, pinpos, angle, mirror)

    def pin_xy(self, placed, pin_num):
        x, y, pinpos, angle, mirror = placed
        if pin_num not in pinpos:
            return None
        px, py, _pa = pinpos[pin_num]
        # apply mirror then rotation, schematic Y is inverted vs symbol lib Y
        if mirror == 'y':
            px = -px
        if mirror == 'x':
            py = -py
        if angle == 90:
            px, py = -py, px
        elif angle == 180:
            px, py = -px, -py
        elif angle == 270:
            px, py = py, -px
        return (x + px, y - py)

    def wire(self, x1, y1, x2, y2):
        # Snap endpoints to the 1.27mm grid so connections register cleanly.
        x1, y1, x2, y2 = snap(x1), snap(y1), snap(x2), snap(y2)
        if x1 == x2 and y1 == y2:
            return
        self.items.append(
            f'  (wire (pts (xy {x1:.2f} {y1:.2f}) (xy {x2:.2f} {y2:.2f})) '
            f'(stroke (width 0) (type default)) (uuid {uid()}))'
        )

    def junction(self, x, y):
        # Junction dot so a tap wire meeting a rail is treated as connected.
        x, y = snap(x), snap(y)
        self.items.append(
            f'  (junction (at {x:.2f} {y:.2f}) (diameter 0) (color 0 0 0 0) '
            f'(uuid {uid()}))'
        )

    def label(self, net, x, y, angle=0, justify="left"):
        x, y = snap(x), snap(y)
        self.items.append(
            f'''  (global_label "{esc(net)}" (shape passive) (at {x:.2f} {y:.2f} {angle})
    (effects (font (size 1.27 1.27)) (justify {justify})) (uuid {uid()}))'''
        )

    def text(self, s, x, y, size=2.54):
        self.items.append(
            f'''  (text "{esc(s)}" (at {x:.2f} {y:.2f} 0)
    (effects (font (size {size} {size})) (justify left)) (uuid {uid()}))'''
        )

    def note(self, s, x, y, size=1.27, maxw=None):
        # Multiline descriptive annotation, left-justified. KiCad expects the
        # two-character escape \n inside the quoted string; escape only quotes
        # and backslashes that are NOT part of an intended \n.
        parts = s.split("\\n")
        body = "\\n".join(p.replace("\\", "\\\\").replace('"', '\\"') for p in parts)
        self.items.append(
            f'''  (text "{body}" (at {x:.2f} {y:.2f} 0)
    (effects (font (size {size} {size})) (justify left top)) (uuid {uid()}))'''
        )

    def box(self, x1, y1, x2, y2):
        # Section outline rectangle on the notes graphic layer.
        self.items.append(
            f'''  (rectangle (start {x1:.2f} {y1:.2f}) (end {x2:.2f} {y2:.2f})
    (stroke (width 0.15) (type solid)) (fill (type none)) (uuid {uid()}))'''
        )

    def hlabel(self, net, x, y, angle=0, justify="left", shape="input"):
        # Directional global label (drawn as a tag/box, like COLn/ROWn buses).
        self.items.append(
            f'''  (global_label "{esc(net)}" (shape {shape}) (at {x:.2f} {y:.2f} {angle})
    (effects (font (size 1.27 1.27)) (justify {justify})) (uuid {uid()}))'''
        )

    def render(self, paper="A2"):
        libs = "\n".join(v[0] for v in self.sym_cache.values())
        return f'''(kicad_sch (version 20231120) (generator "ergogen_schematic_gen")
  (uuid {uid()})
  (paper "{paper}")
  (lib_symbols
{libs}
  )
{chr(10).join(self.items)}
  (sheet_instances (path "/" (page "1")))
)
'''


def main():
    board_path, out_dir, proj = sys.argv[1], sys.argv[2], sys.argv[3]
    board = pcbnew.LoadBoard(board_path)

    comps = {}
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
        comps[ref] = (fpid, fp.GetValue(), pads)

    # --- Build matrix grid: (col,row) -> switch ref, and node->diode ref ---
    sw_cell = {}
    node_of = {}
    row_of_node = {}
    diode_ref = {}
    for ref, (fpid, val, pads) in comps.items():
        if "switch_choc" in fpid:
            col = pads.get("1")
            node = pads.get("2")
            node_of[ref] = (col, node)
        if "diode" in fpid:
            node = pads.get("2")
            row = pads.get("1")
            row_of_node[node] = row
            diode_ref[node] = ref
    for ref, (col, node) in node_of.items():
        row = row_of_node.get(node)
        sw_cell[(col, row)] = (ref, node)

    S = Sch()

    # ===== Switch matrix section (Lily58-style: drawn COL/ROW bus rails,
    #       cells wired to them; labels only at the bus entry points) =====
    # Use grid-aligned (multiples of 1.27) geometry so pin taps land exactly on
    # the rails.
    cell_w, cell_h = 25.4, 33.02          # 20 and 26 grid units
    n_cols, n_rows = len(COLS), len(ROWS)
    cx0, cy0 = 69.85, 55.88               # first switch center (grid aligned)
    col_rail_dx = 12.7                    # COL rail sits left of the switch
    row_rail_dy = 22.86                   # ROW rail sits below the diode
    mat_x1 = cx0 - col_rail_dx - 12.7
    mat_y1 = cy0 - 25.4
    mat_x2 = cx0 + (n_cols - 1) * cell_w + 19.05
    mat_y2 = cy0 + (n_rows - 1) * cell_h + row_rail_dy + 8.89

    S.box(mat_x1, mat_y1, mat_x2, mat_y2)
    S.text("Switch Matrix", mat_x1 + 2.0, mat_y1 - 3.0, size=3.0)
    S.note(
        "Each key = a switch in series with a diode (COL -> switch -> diode -> ROW).\\n"
        "The rotary encoder's push-switch sits on col P15 x row P11 (see Encoder).",
        mat_x1 + 2.0, mat_y1 + 1.5, size=1.27,
    )

    # Geometry of every column/row line (all grid-aligned).
    col_x = {c: cx0 + i * cell_w for i, c in enumerate(COLS)}
    row_y = {r: cy0 + i * cell_h for i, r in enumerate(ROWS)}
    row_rail_y = {r: row_y[r] + row_rail_dy for r in ROWS}

    rail_left = snap(mat_x1 + 5.08)
    rail_right = snap(mat_x2 - 5.08)

    # Horizontal ROW rails only (drawn wires, one net each) with the ROW name
    # labelled at the left. COLumns enter as labels on each switch's top pin
    # (like the reference schematic) -- this avoids crossing COL/ROW buses that
    # would otherwise short the matrix together.
    for r in ROWS:
        ry = row_rail_y[r]
        S.wire(rail_left, ry, rail_right, ry)
        # Label placed exactly on the rail's left endpoint so it attaches.
        S.label(r, rail_left, ry, angle=180, justify="right")

    for (col, row), (ref, node) in sw_cell.items():
        if col not in COLS or row not in ROWS:
            continue
        x = col_x[col]
        y = row_y[row]
        ry = row_rail_y[row]
        # Switch (vertical, angle 90): top pin -> COL label; bottom pin -> diode.
        sw = S.symbol("Switch:SW_Push", ref, "SW_Push", x, y, angle=90)
        p_top = S.pin_xy(sw, "2")     # top
        p_bot = S.pin_xy(sw, "1")     # bottom
        if p_top:
            S.wire(p_top[0], p_top[1], p_top[0], p_top[1] - 3.81)
            S.label(col, p_top[0], p_top[1] - 3.81, angle=90, justify="right")
        # Diode straight below; cathode drops onto the horizontal ROW rail.
        dref = diode_ref.get(node, f"D_{ref}")
        d = S.symbol("Device:D", dref, "D", x, y + 12.7, angle=90)
        da = S.pin_xy(d, "2")  # anode (top)
        dk = S.pin_xy(d, "1")  # cathode (bottom)
        if p_bot and da:
            S.wire(p_bot[0], p_bot[1], da[0], da[1])   # straight down
        if dk:
            S.wire(dk[0], dk[1], dk[0], ry)            # cathode to ROW rail
            S.junction(dk[0], ry)

    # ===== Everything else: MCU, encoder, power, reset, battery =====
    ox = mat_x2 + 25.0
    oy = mat_y1
    extras = [(r, c) for r, c in comps.items()
              if "switch_choc" not in c[0] and "diode" not in c[0]]

    # Diodes whose colrow node was NOT placed in the matrix grid (e.g. the
    # encoder's push-switch diode ENC1_SW -> P11). Render them near the encoder.
    placed_nodes = {node for (_c, _r), (_ref, node) in sw_cell.items()}
    orphan_diodes = [
        (ref, c) for ref, c in comps.items()
        if "diode" in c[0] and c[2].get("2") not in placed_nodes
    ]

    def emit_pins(placed, pads, padmap, side="right"):
        for pad_name, net in pads.items():
            if not net:
                continue
            pin_num = padmap.get(pad_name)
            pxy = S.pin_xy(placed, pin_num) if pin_num else None
            if not pxy:
                continue
            if side == "right":
                S.wire(pxy[0], pxy[1], pxy[0] + 5.08, pxy[1])
                S.label(net, pxy[0] + 5.08, pxy[1], angle=0, justify="left")
            else:
                S.wire(pxy[0], pxy[1], pxy[0] - 5.08, pxy[1])
                S.label(net, pxy[0] - 5.08, pxy[1], angle=0, justify="right")

    def emit_pins_vertical(placed, pads, padmap):
        # Fan pin labels out to the right with increasing stub lengths so labels
        # from different pins never coincide (avoids accidental net merges).
        i = 0
        for pad_name, net in pads.items():
            if not net:
                continue
            pin_num = padmap.get(pad_name)
            pxy = S.pin_xy(placed, pin_num) if pin_num else None
            if not pxy:
                continue
            off = 5.08 + i * 2.54
            S.wire(pxy[0], pxy[1], pxy[0] + off, pxy[1])
            S.label(net, pxy[0] + off, pxy[1], angle=0, justify="left")
            i += 1

    extras_d = {r: c for r, c in extras}

    # --- Microcontroller section ---
    mcu_ref = next((r for r, c in extras if "mcu_nice_nano" in c[0]), None)
    mcu_x1, mcu_y1, mcu_x2, mcu_y2 = ox, oy, ox + 70.0, oy + 80.0
    S.box(mcu_x1, mcu_y1, mcu_x2, mcu_y2)
    S.text("Microcontroller", mcu_x1 + 2.0, mcu_y1 - 3.0, size=3.0)
    S.note(
        "nice!nano (or Pro Micro compatible). Pin name = physical pin;\\n"
        "net label = logical signal assigned to it. Match your firmware\\n"
        "to these pins.",
        mcu_x1 + 2.0, mcu_y1 + 1.5,
    )
    if mcu_ref:
        fpid, val, pads = extras_d[mcu_ref]
        placed = S.symbol(SYMBOL_MAP[fpid][0], mcu_ref, "nice!nano",
                          mcu_x1 + 35.0, mcu_y1 + 45.0)
        emit_pins(placed, pads, SYMBOL_MAP[fpid][3], side="right")

    # --- Encoder section ---
    enc_ref = next((r for r, c in extras if "encoder" in c[0]), None)
    enc_x1, enc_y1, enc_x2, enc_y2 = ox, mcu_y2 + 10.0, ox + 70.0, mcu_y2 + 65.0
    S.box(enc_x1, enc_y1, enc_x2, enc_y2)
    S.text("Encoder", enc_x1 + 2.0, enc_y1 - 3.0, size=3.0)
    S.note(
        "Panasonic EVQWGD001 scroll encoder. A/C to MCU, B/D to GND.\\n"
        "Push-switch (S1/S2) is in the key matrix (col P15 x row P11)\\n"
        "via node ENC1_SW and diode D30.",
        enc_x1 + 2.0, enc_y1 + 1.5,
    )
    if enc_ref:
        fpid, val, pads = extras_d[enc_ref]
        placed = S.symbol(SYMBOL_MAP[fpid][0], enc_ref, "EVQWGD001",
                          enc_x1 + 30.0, enc_y1 + 35.0)
        emit_pins(placed, pads, SYMBOL_MAP[fpid][3], side="right")
    # encoder push-switch diode (orphan) drawn inside the encoder box,
    # vertically like the matrix diodes so its two labels stay well separated.
    for di, (dref, (fpid, val, pads)) in enumerate(orphan_diodes):
        d = S.symbol("Device:D", dref, "D",
                     enc_x1 + 15.0 + di * 15.0, enc_y1 + 48.0, angle=90)
        ka = S.pin_xy(d, "2")  # anode (top) -> node ENC1_SW
        kk = S.pin_xy(d, "1")  # cathode (bottom) -> row
        if ka:
            S.wire(ka[0], ka[1], ka[0], ka[1] - 2.54)
            S.label(pads.get("2"), ka[0], ka[1] - 2.54, angle=90, justify="right")
        if kk:
            S.wire(kk[0], kk[1], kk[0], kk[1] + 2.54)
            S.label(pads.get("1"), kk[0], kk[1] + 2.54, angle=270, justify="right")

    # --- Power section (battery + power switch + reset) ---
    pwr_items = [(r, c) for r, c in extras
                 if any(k in c[0] for k in ("battery", "power_switch", "reset"))]
    pwr_x1, pwr_y1 = ox, enc_y2 + 10.0
    pwr_x2, pwr_y2 = ox + 70.0, enc_y2 + 60.0
    S.box(pwr_x1, pwr_y1, pwr_x2, pwr_y2)
    S.text("Power / Reset", pwr_x1 + 2.0, pwr_y1 - 3.0, size=3.0)
    S.note(
        "Battery+ -> power switch -> nice!nano RAW; Battery- -> GND.\\n"
        "Reset (Panasonic EVQ-PUC02K) shorts RST to GND for reflashing.",
        pwr_x1 + 2.0, pwr_y1 + 1.5,
    )
    # Lay the three parts out left-to-right, each in its own column so their
    # pin labels can't overlap.
    px = pwr_x1 + 15.0
    for ref, (fpid, val, pads) in pwr_items:
        if "battery" in fpid:
            label = "Battery"
        elif "power_switch" in fpid:
            label = "Power SW"
        else:
            label = "Reset"
        placed = S.symbol(SYMBOL_MAP[fpid][0], ref, label,
                          px, pwr_y1 + 35.0, angle=0)
        emit_pins_vertical(placed, pads, SYMBOL_MAP[fpid][3])
        px += 22.86

    sch = S.render(paper="A1")
    path = f"{out_dir}/{proj}.kicad_sch"
    with open(path, "w") as f:
        f.write(sch)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
