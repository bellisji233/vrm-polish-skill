"""Front and back renders of the mesh pieces measure.py found at the standard body sites, one colour per piece,
so a person (or an agent that can see) decides which pieces are skin and which are cloth for region_paint.

usage: blender -b PROJECT/work/weights/weighted.blend --python pieces_sheet.py -- MEASURE.json OUT_DIR
writes OUT_DIR/pieces-front.png, pieces-back.png, pieces.json (colour per piece); polish/measure/make_sheet.py
adds the legend.
"""
import json
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

MEAS, OUT = sys.argv[sys.argv.index('--') + 1:][:2]
OUT = Path(OUT); OUT.mkdir(parents=True, exist_ok=True)
meas = json.loads(Path(MEAS).read_text(encoding='utf-8'))
PAL = [(0.90, 0.20, 0.20), (0.15, 0.55, 0.95), (0.20, 0.75, 0.30), (0.95, 0.65, 0.10),
       (0.65, 0.30, 0.85), (0.10, 0.80, 0.80), (0.95, 0.40, 0.70), (0.55, 0.40, 0.20)]
body = bpy.data.objects['Body']
bm = bmesh.new(); bm.from_mesh(body.data); bm.faces.ensure_lookup_table()
isl = [-1] * len(bm.faces); n = 0
for f in bm.faces:
    if isl[f.index] >= 0: continue
    st = [f]; isl[f.index] = n
    while st:
        g = st.pop()
        for e in g.edges:
            for h in e.link_faces:
                if isl[h.index] < 0: isl[h.index] = n; st.append(h)
    n += 1
bm.free()
colour = {p['island']: PAL[i % len(PAL)] for i, p in enumerate(meas['pieces'])}
attr = body.data.color_attributes.new('piece', 'BYTE_COLOR', 'CORNER')
for poly in body.data.polygons:
    c = colour.get(isl[poly.index], (0.62, 0.62, 0.62)) + (1.0,)
    for li in poly.loop_indices:
        attr.data[li].color = c
body.data.color_attributes.active_color = attr
for o in bpy.data.objects:
    o.hide_render = o.name not in ('Body',)
sc = bpy.context.scene
sc.render.engine = 'BLENDER_WORKBENCH'
sc.display.shading.light = 'STUDIO'; sc.display.shading.color_type = 'VERTEX'
sc.render.resolution_x, sc.render.resolution_y = 700, 1000
P = [body.matrix_world @ v.co for v in body.data.vertices]
lo = Vector([min(p[i] for p in P) for i in range(3)]); hi = Vector([max(p[i] for p in P) for i in range(3)])
mid = (lo + hi) / 2; h = hi.z - lo.z
cd = bpy.data.cameras.new('c'); cd.type = 'ORTHO'; cd.ortho_scale = h * 1.05
cam = bpy.data.objects.new('c', cd); sc.collection.objects.link(cam); sc.camera = cam
for name, y, rot in (('front', -3.0, 0.0), ('back', 3.0, 3.14159)):
    cam.location = (mid.x, mid.y + y, mid.z); cam.rotation_euler = (1.5708, 0, rot)
    sc.render.filepath = str(OUT / f'pieces-{name}.png'); bpy.ops.render.render(write_still=True)
(OUT / 'pieces.json').write_text(json.dumps([dict(p, colour=colour[p['island']]) for p in meas['pieces']], ensure_ascii=False, indent=1), encoding='utf-8')
print('PIECES_OK ' + str(OUT))
