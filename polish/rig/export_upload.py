"""Geometry-only head + body FBX for Tripo's Rig step.

The kit's own rig export (scripts/export-rig.py) embeds the 4K textures, which
takes the file over the 10 MB browser upload limit. Tripo only needs the geometry
to place bones, so this runs that exporter unchanged from the user's kit and only
asks its FBX call to leave the images out. No kit code is copied here.

usage: blender -b --python export_upload.py -- KIT PROJECT.charakit OUT.fbx
  KIT   Charakuru kit root
"""
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

import bpy


class _Proxy:
    """Stands in for one level of the bpy module inside the kit exporter."""

    def __init__(self, real, **override):
        self._real, self._override = real, override

    def __getattr__(self, name):
        if name in self._override:
            return self._override[name]
        return getattr(self._real, name)


def _fbx_without_textures(**kw):
    kw.update(path_mode='STRIP', embed_textures=False)
    return bpy.ops.export_scene.fbx(**kw)


def main(kit, source, output):
    output = Path(output).resolve()
    if output.exists():
        raise SystemExit(f'output exists: {output}')
    output.parent.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location('kit_export_rig', Path(kit) / 'scripts/export-rig.py')
    kit_export = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kit_export)
    export_scene = _Proxy(bpy.ops.export_scene, fbx=_fbx_without_textures)
    kit_export.bpy = _Proxy(bpy, ops=_Proxy(bpy.ops, export_scene=export_scene))
    # The kit unpacks the project next to its output, so export into a temporary folder.
    tmp = Path(tempfile.mkdtemp(prefix='polish-rigupload-'))
    try:
        kit_export.run(Path(source).resolve(), tmp / output.name)
        shutil.move(tmp / output.name, output)
        meshes = [o for o in bpy.context.selected_objects if o.type == 'MESH']
        size = output.stat().st_size
        info = dict(output=output.name, meshes=len(meshes), faces=sum(len(o.data.polygons) for o in meshes),
                    bytes=size, upload_rotation_xyz=[0, 90, 0], textures=False)
        output.with_suffix('.json').write_text(json.dumps(info, indent=1), encoding='utf-8')
        print('RIG_UPLOAD_OK ' + json.dumps(info))
        if size > 10 * 1024 * 1024:
            print('WARNING: still over 10 MB')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    main(*sys.argv[sys.argv.index('--') + 1:][:3])
