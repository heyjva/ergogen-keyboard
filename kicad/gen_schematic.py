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
        self.items.append(
            f'  (wire (pts (xy {x1:.2f} {y1:.2f}) (xy {x2:.2f} {y2:.2f})) '
            f'(stroke (width 0) (type default)) (uuid {uid()}))'
        )

    def label(self, net, x, y, angle=0, justify="left"):
        self.items.append(
            f'''  (global_label "{esc(net)}" (shape passive) (at {x:.2f} {y:.2f} {angle})
    (effects (font (size 1.27 1.27)) (justify {justify})) (uuid {uid()}))'''
        )

    def text(self, s, x, y, size=2.54):
        self.items.append(
            f'''  (text "{esc(s)}" (at {x:.2f} {y:.2f} 0)
    (effects (font (size {size} {size})) (justify left)) (uuid {uid()}))'''
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

    # ===== Switch matrix section =====
    S.text("Switch Matrix", 20, 12, size=3.81)
    cx0, cy0 = 40.0, 30.0
    cell_w, cell_h = 33.02, 25.4
    # column labels (top)
    for ci, col in enumerate(COLS):
        x = cx0 + ci * cell_w
        S.label(col, x, cy0 - 12.7, angle=90, justify="right")
    # row labels (left)
    for ri, row in enumerate(ROWS):
        y = cy0 + ri * cell_h
        S.label(row, cx0 - 20.32, y + 5.08, angle=0, justify="right")

    for (col, row), (ref, node) in sw_cell.items():
        if col not in COLS or row not in ROWS:
            continue
        ci = COLS.index(col)
        ri = ROWS.index(row)
        x = cx0 + ci * cell_w
        y = cy0 + ri * cell_h
        # switch: pin1 up (to column), pin2 down (to diode)
        sw = S.symbol("Switch:SW_Push", ref, "SW_Push", x, y, angle=90)
        p1 = S.pin_xy(sw, "1")
        p2 = S.pin_xy(sw, "2")
        # column label above pin1
        if p1:
            S.wire(p1[0], p1[1], p1[0], p1[1] - 5.08)
            S.label(col, p1[0], p1[1] - 5.08, angle=90, justify="right")
        # diode below the switch (node between)
        dref = diode_ref.get(node, f"D_{ref}")
        d = S.symbol("Device:D", dref, "D", x, y + 12.7, angle=90)
        da = S.pin_xy(d, "2")  # anode -> node (up, to switch pin2)
        dk = S.pin_xy(d, "1")  # cathode -> row (down)
        if p2 and da:
            S.wire(p2[0], p2[1], da[0], da[1])
        if dk:
            S.wire(dk[0], dk[1], dk[0], dk[1] + 5.08)
            S.label(row, dk[0], dk[1] + 5.08, angle=270, justify="right")

    # ===== Everything else: MCU, encoder, power, reset, battery =====
    ox, oy = cx0 + len(COLS) * cell_w + 30, 30.0
    extras = [(r, c) for r, c in comps.items()
              if "switch_choc" not in c[0] and "diode" not in c[0]]

    # Diodes whose colrow node was NOT placed in the matrix grid (e.g. the
    # encoder's push-switch diode ENC1_SW -> P11). Render them near the encoder.
    placed_nodes = {node for (_c, _r), (_ref, node) in sw_cell.items()}
    orphan_diodes = [
        (ref, c) for ref, c in comps.items()
        if "diode" in c[0] and c[2].get("2") not in placed_nodes
    ]

    # nice!nano
    S.text("Microcontroller", ox, oy - 12, size=3.81)
    for ref, (fpid, val, pads) in extras:
        m = SYMBOL_MAP[fpid]
        lib_id = m[0]
        if "mcu_nice_nano" in fpid:
            placed = S.symbol(lib_id, ref, "nice!nano", ox + 20, oy + 25)
        elif "encoder" in fpid:
            placed = S.symbol(lib_id, ref, "EVQWGD001", ox + 5, oy + 85)
            S.text("Encoder", ox, oy + 70, size=3.81)
        elif "battery" in fpid:
            placed = S.symbol(lib_id, ref, "Battery", ox + 45, oy + 85)
            S.text("Power", ox + 40, oy + 70, size=3.81)
        elif "power_switch" in fpid:
            placed = S.symbol(lib_id, ref, "Power SW", ox + 45, oy + 110)
        elif "reset" in fpid:
            placed = S.symbol(lib_id, ref, "Reset", ox + 45, oy + 130)
        else:
            continue
        for pad_name, net in pads.items():
            if not net:
                continue
            pin_num = m[3].get(pad_name)
            pxy = S.pin_xy(placed, pin_num) if pin_num else None
            if not pxy:
                continue
            # short stub + label to the right
            S.wire(pxy[0], pxy[1], pxy[0] + 3.81, pxy[1])
            S.label(net, pxy[0] + 3.81, pxy[1], angle=0, justify="left")

    # Orphan diodes (e.g. encoder push-switch diode) placed near the encoder.
    for di, (dref, (fpid, val, pads)) in enumerate(orphan_diodes):
        dx = ox + 5
        dy = oy + 100 + di * 15.24
        d = S.symbol("Device:D", dref, "D", dx, dy, angle=0)
        ka = S.pin_xy(d, "2")  # anode -> node
        kk = S.pin_xy(d, "1")  # cathode -> row
        if ka:
            S.wire(ka[0], ka[1], ka[0] - 3.81, ka[1])
            S.label(pads.get("2"), ka[0] - 3.81, ka[1], angle=0, justify="right")
        if kk:
            S.wire(kk[0], kk[1], kk[0] + 3.81, kk[1])
            S.label(pads.get("1"), kk[0] + 3.81, kk[1], angle=0, justify="left")

    sch = S.render(paper="A1")
    path = f"{out_dir}/{proj}.kicad_sch"
    with open(path, "w") as f:
        f.write(sch)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
