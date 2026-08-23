// Panasonic EVQWGD001 horizontal ("scroll wheel") rotary encoder.
//
// KiCad 8 (footprint syntax) port of the original ergogen `scrollwheel`
// footprint (which was KiCad 5/6 `module` syntax). Behavior and pad geometry
// are preserved; only the s-expression syntax and the ergogen API usage were
// modernized to match the ceoloide KiCad 8 footprints used in this project.
//
//   __________________
//  (f) (t)         | |
//  | (1)           | |
//  | (2)           | |
//  | (3)           | |
//  | (4)           | |
//  |_( )___________|_|
//
// Nets:
//    from: switch pin 1 (for button/push presses)
//    to:   switch pin 2 (for button/push presses)
//    A:    rotary pin 1
//    B:    rotary pin 2 (usually GND)
//    C:    rotary pin 3
//    D:    rotary pin 4 (often unused)
//
// Params:
//    side: default 'F'
//      the side to place the single-side footprint on, either 'F' or 'B'.
//    reversible: default false
//      if true, places pads on both sides so the PCB can be reversible.
//    designator: default 'ENC'
//    from, to, A, B, C, D: nets (see above)

module.exports = {
  params: {
    designator: 'ENC',
    side: 'F',
    reversible: false,
    include_edge_cuts: true,
    from: { type: 'net', value: undefined },
    to: { type: 'net', value: undefined },
    A: { type: 'net', value: undefined },
    B: { type: 'net', value: undefined },
    C: { type: 'net', value: undefined },
    D: { type: 'net', value: undefined },
    encoder_3dmodel_filename: '',
    encoder_3dmodel_xyz_offset: [0, 0, 0],
    encoder_3dmodel_xyz_scale: [1, 1, 1],
    encoder_3dmodel_xyz_rotation: [0, 0, 0],
  },
  body: p => {
    const standard_opening = `
  (footprint "ceoloide:encoder_evqwgd001"
    (layer "${p.side}.Cu")
    ${p.at}
    (property "Reference" "${p.ref}"
      (at 0 0 ${p.r})
      (layer "${p.side}.SilkS")
      ${p.ref_hide}
      (effects (font (size 1 1) (thickness 0.15)))
    )
    (attr through_hole)

    ${'' /* body outline / corner marks on the user drawings layer */}
    (fp_line (start -8.4 -6.4) (end 8.4 -6.4) (layer "Dwgs.User") (stroke (width 0.12) (type solid)))
    (fp_line (start 8.4 -6.4) (end 8.4 7.4) (layer "Dwgs.User") (stroke (width 0.12) (type solid)))
    (fp_line (start 8.4 7.4) (end -8.4 7.4) (layer "Dwgs.User") (stroke (width 0.12) (type solid)))
    (fp_line (start -8.4 7.4) (end -8.4 -6.4) (layer "Dwgs.User") (stroke (width 0.12) (type solid)))
    `

    // `neg` flips X for the mirrored (reverse) placement, `pos` positions the
    // right-hand roller cutout on the correct side.
    const pins = (neg, pos) => `
      ${p.include_edge_cuts ? `
      ${'' /* edge cuts for the roller opening (only when the encoder sits at
             the board edge; disable via include_edge_cuts for mid-board use) */}
      (fp_line (start ${pos}9.8 7.3) (end ${pos}9.8 -6.3) (layer "Edge.Cuts") (stroke (width 0.15) (type solid)))
      (fp_line (start ${pos}7.4 -6.3) (end ${pos}7.4 7.3) (layer "Edge.Cuts") (stroke (width 0.15) (type solid)))
      (fp_line (start ${pos}9.5 -6.6) (end ${pos}7.7 -6.6) (layer "Edge.Cuts") (stroke (width 0.15) (type solid)))
      (fp_line (start ${pos}7.7 7.6) (end ${pos}9.5 7.6) (layer "Edge.Cuts") (stroke (width 0.15) (type solid)))
      (fp_arc (start ${pos}7.7 7.3) (mid ${pos}7.4878 7.5121) (end ${pos}7.4 7.3) (layer "Edge.Cuts") (stroke (width 0.15) (type solid)))
      (fp_arc (start ${pos}9.5 7.3) (mid ${pos}9.7121 7.5121) (end ${pos}9.5 7.6) (layer "Edge.Cuts") (stroke (width 0.15) (type solid)))
      (fp_arc (start ${pos}7.7 -6.3) (mid ${pos}7.4878 -6.5121) (end ${pos}7.7 -6.6) (layer "Edge.Cuts") (stroke (width 0.15) (type solid)))
      (fp_arc (start ${pos}9.5 -6.3) (mid ${pos}9.7121 -6.5121) (end ${pos}9.8 -6.3) (layer "Edge.Cuts") (stroke (width 0.15) (type solid)))
      ` : ''}

      ${'' /* pins */}
      (pad "1" thru_hole circle (at ${neg}6.85 -6.2 ${p.r}) (size 1.6 1.6) (drill 0.9) (layers "*.Cu" "*.Mask") ${p.from.str})
      (pad "2" thru_hole circle (at ${neg}5 -6.2 ${p.r}) (size 1.6 1.6) (drill 0.9) (layers "*.Cu" "*.Mask") ${p.to.str})
      (pad "A" thru_hole circle (at ${neg}5.625 -3.81 ${p.r}) (size 1.6 1.6) (drill 0.9) (layers "*.Cu" "*.Mask") ${p.A.str})
      (pad "B" thru_hole circle (at ${neg}5.625 -1.27 ${p.r}) (size 1.6 1.6) (drill 0.9) (layers "*.Cu" "*.Mask") ${p.B.str})
      (pad "C" thru_hole circle (at ${neg}5.625 1.27 ${p.r}) (size 1.6 1.6) (drill 0.9) (layers "*.Cu" "*.Mask") ${p.C.str})
      (pad "D" thru_hole circle (at ${neg}5.625 3.81 ${p.r}) (size 1.6 1.6) (drill 0.9) (layers "*.Cu" "*.Mask") ${p.D.str})

      ${'' /* stabilizer / alignment post (non-plated) */}
      (pad "" np_thru_hole circle (at ${neg}5.625 6.3 ${p.r}) (size 1.5 1.5) (drill 1.5) (layers "*.Cu" "*.Mask"))
    `

    const standard_closing = `
      ${p.encoder_3dmodel_filename ? `
    (model ${p.encoder_3dmodel_filename}
      (offset (xyz ${p.encoder_3dmodel_xyz_offset[0]} ${p.encoder_3dmodel_xyz_offset[1]} ${p.encoder_3dmodel_xyz_offset[2]}))
      (scale (xyz ${p.encoder_3dmodel_xyz_scale[0]} ${p.encoder_3dmodel_xyz_scale[1]} ${p.encoder_3dmodel_xyz_scale[2]}))
      (rotate (xyz ${p.encoder_3dmodel_xyz_rotation[0]} ${p.encoder_3dmodel_xyz_rotation[1]} ${p.encoder_3dmodel_xyz_rotation[2]}))
    )
      ` : ''}
  )
    `

    let final = standard_opening
    if (p.reversible) {
      // Reversible: emit both orientations so the PCB can be flipped.
      final += pins('-', '')
      final += pins('', '-')
    } else if (p.side === 'B') {
      // Single-side Back: emit the mirrored orientation only.
      final += pins('', '-')
    } else {
      // Single-side Front.
      final += pins('-', '')
    }
    final += standard_closing
    return final
  },
}
