#!/bin/zsh
# Measure the body, fit the template hands and write work/build_character.json from a head profile.
# usage: prepare.sh PROJECT_DIR PROFILE_DIR [--skin 3,5] [--cloth 2,4] [--metal] [--force]
#   PROFILE_DIR  head profile (polish/profile/make_profile.py); the new head must be the same head mesh
#   --skin/--cloth  piece numbers from work/measure/零件.jpg (see make_config.py); without them only the neck is painted
# Writes work/measure/measure.json, work/measure/零件.jpg, work/hand/template_hand.blend, work/build_character.json.
# env: BLENDER
set -e; setopt pipefail
P=${1:A}; PR=${2:A}; shift 2 || { echo "usage: prepare.sh PROJECT_DIR PROFILE_DIR [--skin N,N] [--cloth N,N] [--force]"; exit 2; }
[ -f "$P/work/weights/weighted.blend" ] && [ -f "$PR/profile.json" ] || { echo "need PROJECT/work/weights/weighted.blend and PROFILE/profile.json"; exit 2; }
H=${0:A:h:h}; W="$P/work"; B=${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}
mkdir -p "$W/measure"
$B -b "$W/weights/weighted.blend" --python-exit-code 1 --python "$H/measure/measure.py" -- "$PR" "$W/measure/measure.json" 2>&1 | grep -E "MEASURE_OK|NEW_HEAD|Error|neck:|not found" | cut -c1-400
if python3 -c "import json,sys; sys.exit(0 if json.load(open(sys.argv[1])).get('new_head') else 1)" "$W/measure/measure.json"; then
  # another head than the profile's: prepare its face texture (painted brows, crease contour, mouth line)
  $B -b "$W/weights/weighted.blend" --python-exit-code 1 --python "$H/face/head_texture.py" -- export "$W/measure" 2>&1 | grep -E "TEXTURE_EXPORT|Error" | cut -c1-200
  python3 "$H/face/head_texture.py" fix "$W/measure/texture" | cut -c1-200
fi
$B -b "$W/weights/weighted.blend" --python-exit-code 1 --python "$H/measure/pieces_sheet.py" -- "$W/measure/measure.json" "$W/measure" 2>&1 | grep -E "Error" || true
python3 "$H/measure/make_sheet.py" "$W/measure" | cut -c1-200
if [ ! -f "$W/hand/template_hand.blend" ] || [[ " $* " == *" --force "* ]]; then
  FR=($(python3 -c "import json,sys; f=json.load(open(sys.argv[1])).get('frame') or {'s':1,'t':[0,0,0]}; print(f['s'], *f['t'])" "$W/measure/measure.json"))
  rm -rf "$W/hand"; mkdir -p "$W/hand"
  $B -b "$W/weights/weighted.blend" --python-exit-code 1 --python "$H/hand/fit_in_head_frame.py" -- $FR "${H:h}/assets/makehuman-hand" "$W/hand" 2>&1 | grep -E "Error|Traceback" || true
  [ -f "$W/hand/template_hand.blend" ] && echo "template hand: $W/hand/template_hand.blend"
fi
python3 "$H/measure/make_config.py" "$P" "$PR" "$@"
