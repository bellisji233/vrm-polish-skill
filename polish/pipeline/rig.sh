#!/bin/zsh
# Tripo Rig step helpers, used around the kit's own import-bones.
# usage:
#   rig.sh upload PROJECT_DIR        geometry-only head+body FBX for Tripo (under the 10 MB upload limit)
#                                    -> PROJECT_DIR/work/rig/upload/rig-upload.fbx
#   rig.sh check RETURNED.fbx        left/right check of Tripo's returned bones; if a finger chain is off,
#                                    writes a fixed copy next to it (…-symmetric.fbx) and prints the file to import
# env: KIT (default: two folders above PROJECT_DIR), BLENDER
set -e; setopt pipefail
H=${0:A:h:h}; B=${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}
case $1 in
upload)
  P=${2:A}; [ -f "$P/project.charakit" ] || { echo "usage: rig.sh upload PROJECT_DIR"; exit 2; }
  KIT=${KIT:-${P:h:h}}; OUT="$P/work/rig/upload/rig-upload.fbx"
  [ -e "$OUT" ] && mv "$OUT" "${OUT%.fbx}-$(date +%m%d%H%M).fbx"
  $B -b --python-exit-code 1 --python "$H/rig/export_upload.py" -- "$KIT" "$P/project.charakit" "$OUT" 2>&1 | grep -E "RIG_UPLOAD_OK|WARNING|Error|project|expected" | cut -c1-200
  echo "upload: $OUT  (Tripo 最适合的角度 X=0 Y=90 Z=0, Rig 预设 VRM 1.0 Humanoid)";;
check)
  F=${2:A}; [ -f "$F" ] || { echo "usage: rig.sh check RETURNED.fbx"; exit 2; }
  FIX="${F:r}-symmetric.fbx"; rm -f "$FIX"
  $B -b --factory-startup --python-exit-code 1 --python "$H/rig/check_symmetry.py" -- "$F" "$FIX" 2>&1 | grep -E "SYMMETRY|Error" | cut -c1-600
  if [ -f "$FIX" ]; then echo "import: $FIX"; else echo "import: $F"; fi;;
*) echo "usage: rig.sh upload PROJECT_DIR | rig.sh check RETURNED.fbx"; exit 2;;
esac
