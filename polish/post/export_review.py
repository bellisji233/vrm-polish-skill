# Export the review FBX (rig + every avatar mesh incl. hair) with the kit's review-export settings. Does not save the Blend.
# usage: blender -b work/character.blend -P polish/post/export_review.py -- OUT.fbx
import bpy, sys
out = sys.argv[sys.argv.index('--') + 1]
rig = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
objs = [rig] + [o for o in bpy.data.objects if o.type == 'MESH' and o.parent == rig]
bpy.ops.object.select_all(action='DESELECT')
for o in objs:
    o.hide_set(False); o.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.export_scene.fbx(filepath=out, use_selection=True, object_types={'MESH', 'ARMATURE'}, add_leaf_bones=False, bake_anim=False,
                         use_mesh_modifiers=False, path_mode='COPY', embed_textures=True, use_triangles=False)
print('EXPORTED', out, [o.name for o in objs])
