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
        "keeb:nice_nano", None, "nice_nano",
        {str(i): str(i) for i in range(1, 25)}, "U"),
}

# Physical nice!nano pin names by connector pad number (matches the ceoloide
# mcu_nice_nano footprint socket order): pad(2k-1) = left of row k, pad(2k) =
# right of row k, top -> bottom.
NICE_NANO_PINS = {
    "1": "P1",  "2": "RAW",
    "3": "P0",  "4": "GND",
    "5": "GND", "6": "RST",
    "7": "GND", "8": "VCC",
    "9": "P2",  "10": "P21",
    "11": "P3", "12": "P20",
    "13": "P4", "14": "P19",
    "15": "P5", "16": "P18",
    "17": "P6", "18": "P15",
    "19": "P7", "20": "P14",
    "21": "P8", "22": "P16",
    "23": "P9", "24": "P10",
}


def build_nice_nano_symbol():
    """Return (symbol_sexpr, pin_positions) for a dedicated nice!nano symbol:
    a 2-column DIP body with each pin labelled by its physical pin name
    (RAW/GND/VCC/P0-P21). Pad numbers match Conn_02x12_Odd_Even so the
    generator's pad->pin mapping still works."""
    rows = 12
    pitch = 2.54
    half_h = (rows - 1) * pitch / 2.0        # 13.97
    body_w = 15.24
    x_left = -body_w / 2.0
    x_right = body_w / 2.0
    pin_len = 3.81
    top = half_h + pitch                     # a little headroom
    bot = -half_h - pitch

    lines = []
    lines.append('(symbol "keeb:nice_nano" (pin_names (offset 0.762)) '
                 '(in_bom yes) (on_board yes)')
    lines.append('  (property "Reference" "U" (at 0 %.2f 0) '
                 '(effects (font (size 1.27 1.27))))' % (top + 1.27))
    lines.append('  (property "Value" "nice!nano" (at 0 %.2f 0) '
                 '(effects (font (size 1.27 1.27))))' % (bot - 1.27))
    # body rectangle
    lines.append('  (symbol "nice_nano_0_1"')
    lines.append('    (rectangle (start %.2f %.2f) (end %.2f %.2f) '
                 '(stroke (width 0.254) (type default)) '
                 '(fill (type background)))' % (x_left, top, x_right, bot))
    lines.append('  )')
    lines.append('  (symbol "nice_nano_1_1"')
    pin_pos = {}
    for k in range(1, rows + 1):
        y = half_h - (k - 1) * pitch
        left_pad = str(2 * k - 1)
        right_pad = str(2 * k)
        lname = NICE_NANO_PINS[left_pad]
        rname = NICE_NANO_PINS[right_pad]
        # left pin: endpoint at (x_left - pin_len, y), points right (angle 0)
        lines.append(
            '    (pin passive line (at %.2f %.2f 0) (length %.2f) '
            '(name "%s" (effects (font (size 1.0 1.0)))) '
            '(number "%s" (effects (font (size 1.0 1.0)))))'
            % (x_left - pin_len, y, pin_len, lname, left_pad))
        pin_pos[left_pad] = (x_left - pin_len, y, 0)
        # right pin: endpoint at (x_right + pin_len, y), points left (angle 180)
        lines.append(
            '    (pin passive line (at %.2f %.2f 180) (length %.2f) '
            '(name "%s" (effects (font (size 1.0 1.0)))) '
            '(number "%s" (effects (font (size 1.0 1.0)))))'
            % (x_right + pin_len, y, pin_len, rname, right_pad))
        pin_pos[right_pad] = (x_right + pin_len, y, 180)
    lines.append('  )')
    lines.append(')')
    return "\n".join(lines), pin_pos


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
        # Custom, generator-built symbols (e.g. the labelled nice!nano).
        if lib_id == "keeb:nice_nano":
            blk, pinpos = build_nice_nano_symbol()
            self.sym_cache[lib_id] = (blk, pinpos, "nice_nano")
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

    def pin_dir(self, placed, pin_num):
        """Return the outward unit direction (dx, dy) a pin's wire should
        leave in, accounting for symbol rotation/mirror. In the KiCad symbol
        library a pin's `angle` points from the pin endpoint toward the body,
        so the outward wire direction is the opposite."""
        x, y, pinpos, angle, mirror = placed
        if pin_num not in pinpos:
            return (1, 0)
        _px, _py, pa = pinpos[pin_num]
        # unit vector the pin *points* (toward body) in lib space
        dirs = {0: (1, 0), 90: (0, 1), 180: (-1, 0), 270: (0, -1)}
        dx, dy = dirs.get(pa, (1, 0))
        # outward is opposite
        dx, dy = -dx, -dy
        if mirror == 'y':
            dx = -dx
        if mirror == 'x':
            dy = -dy
        if angle == 90:
            dx, dy = -dy, dx
        elif angle == 180:
            dx, dy = -dx, -dy
        elif angle == 270:
            dx, dy = dy, -dx
        # schematic Y is inverted vs lib Y
        return (dx, -dy)

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

    def emit_pins_directional(placed, pads, padmap, stub=6.35, stagger=True):
        """Draw a stub wire outward from each pin along its real direction and
        put the net label at the stub end. Handles symbols whose pins point in
        different directions (encoder, SPDT switch) so nothing overlaps the
        symbol body. With stagger=False all stubs in a given direction share the
        same length (good for in-line connectors like the nice!nano)."""
        seen = {}
        for pad_name, net in pads.items():
            if not net:
                continue
            pin_num = padmap.get(pad_name)
            if not pin_num:
                continue
            pxy = S.pin_xy(placed, pin_num)
            if not pxy:
                continue
            dx, dy = S.pin_dir(placed, pin_num)
            key = (round(dx), round(dy))
            n = seen.get(key, 0)
            seen[key] = n + 1
            length = stub + (n * 2.54 if stagger else 0)
            ex, ey = pxy[0] + dx * length, pxy[1] + dy * length
            S.wire(pxy[0], pxy[1], ex, ey)
            if dx > 0:
                just, ang = "left", 0
            elif dx < 0:
                just, ang = "right", 0
            elif dy > 0:
                just, ang = "right", 270
            else:
                just, ang = "right", 90
            S.label(net, ex, ey, angle=ang, justify=just)

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
    # Wide box; the nice!nano is a tall 2-column part, so its pins already fan
    # left/right. We give plenty of width so the net labels sit clear of it.
    mcu_ref = next((r for r, c in extras if "mcu_nice_nano" in c[0]), None)
    mcu_x1, mcu_y1 = ox, oy
    mcu_x2, mcu_y2 = ox + 95.0, oy + 95.0
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
                          mcu_x1 + 47.5, mcu_y1 + 52.0)
        emit_pins_directional(placed, pads, SYMBOL_MAP[fpid][3], stub=7.62,
                              stagger=False)

    # --- Encoder section ---
    # The rotary-encoder symbol has A/B/C on the left and S1/S2 on the right, so
    # use the directional emitter to fan labels out on the correct sides.
    enc_ref = next((r for r, c in extras if "encoder" in c[0]), None)
    enc_x1, enc_y1 = ox, mcu_y2 + 12.0
    enc_x2, enc_y2 = ox + 95.0, mcu_y2 + 72.0
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
                          enc_x1 + 47.5, enc_y1 + 42.0)
        emit_pins_directional(placed, pads, SYMBOL_MAP[fpid][3], stub=8.89)
    # encoder push-switch diode (orphan) drawn to the LEFT of the encoder, well
    # clear of the encoder's pins.
    for di, (dref, (fpid, val, pads)) in enumerate(orphan_diodes):
        d = S.symbol("Device:D", dref, "D",
                     enc_x1 + 15.0, enc_y1 + 40.0 + di * 15.0, angle=90)
        ka = S.pin_xy(d, "2")  # anode (top) -> node ENC1_SW
        kk = S.pin_xy(d, "1")  # cathode (bottom) -> row
        if ka:
            S.wire(ka[0], ka[1], ka[0], ka[1] - 3.81)
            S.label(pads.get("2"), ka[0], ka[1] - 3.81, angle=90, justify="right")
        if kk:
            S.wire(kk[0], kk[1], kk[0], kk[1] + 3.81)
            S.label(pads.get("1"), kk[0], kk[1] + 3.81, angle=270, justify="right")

    # --- Power section (battery + power switch + reset) ---
    pwr_items = [(r, c) for r, c in extras
                 if any(k in c[0] for k in ("battery", "power_switch", "reset"))]
    pwr_x1, pwr_y1 = ox, enc_y2 + 12.0
    pwr_x2, pwr_y2 = ox + 95.0, enc_y2 + 72.0
    S.box(pwr_x1, pwr_y1, pwr_x2, pwr_y2)
    S.text("Power / Reset", pwr_x1 + 2.0, pwr_y1 - 3.0, size=3.0)
    S.note(
        "Battery+ -> power switch -> nice!nano RAW; Battery- -> GND.\\n"
        "Reset (Panasonic EVQ-PUC02K) shorts RST to GND for reflashing.",
        pwr_x1 + 2.0, pwr_y1 + 1.5,
    )
    # Lay the three parts out left-to-right with generous spacing; use the
    # directional emitter so each part's pins fan out cleanly.
    px = pwr_x1 + 20.0
    for ref, (fpid, val, pads) in pwr_items:
        if "battery" in fpid:
            label = "Battery"
        elif "power_switch" in fpid:
            label = "Power SW"
        else:
            label = "Reset"
        placed = S.symbol(SYMBOL_MAP[fpid][0], ref, label,
                          px, pwr_y1 + 42.0, angle=0)
        emit_pins_directional(placed, pads, SYMBOL_MAP[fpid][3], stub=6.35)
        px += 30.0

    sch = S.render(paper="A1")
    path = f"{out_dir}/{proj}.kicad_sch"
    with open(path, "w") as f:
        f.write(sch)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
