# Fit the template hands in the head frame the build runs in (build_character.json "frame"):
# move the rig (children follow) by x_purple = (x - t) / s, then run make_template_hand.py unchanged.
# usage: blender -b work/weights/weighted.blend -P polish/hand/fit_in_head_frame.py -- S TX TY TZ assets/makehuman-hand OUT_DIR
import bpy, sys, runpy
from mathutils import Matrix, Vector
a = sys.argv[sys.argv.index('--') + 1:]
s, t = float(a[0]), Vector((float(a[1]), float(a[2]), float(a[3])))
rig = next(o for o in bpy.data.objects if o.type == 'ARMATURE' and o.name.endswith('_Rig'))
for o in bpy.data.objects:
    if o.type == 'ARMATURE' and o is not rig:
        bpy.data.objects.remove(o, do_unlink=True)          # the fitter takes the first armature it finds
rig.matrix_world = Matrix.Diagonal((1 / s, 1 / s, 1 / s, 1.0)) @ Matrix.Translation(-t) @ rig.matrix_world
bpy.context.view_layer.update()
sys.argv = [sys.argv[0], '--', a[4], a[5]]
runpy.run_path(str(__import__('pathlib').Path(__file__).with_name('make_template_hand.py')), run_name='__main__')
