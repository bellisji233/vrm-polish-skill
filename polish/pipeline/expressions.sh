#!/bin/zsh
# Expressions for a built character: kit expression workspace -> polish expression build (in the head frame) ->
# export -> kit integration -> VRM finalize (about 100 VRM expressions: presets, ARKit 52, gaze, decals).
# usage: expressions.sh PROJECT_DIR PROFILE_DIR OUT.vrm
#   PROFILE_DIR  the head profile (its expr-data/ holds component ids, eye and mouth points of that head mesh);
#                an expr-data folder itself is accepted too
# env: KIT, BLENDER (as build.sh)
set -e; setopt pipefail
P=${1:A}; HD=${2:A}; OUT=${3:A}; [ -d "$P/work" ] && [ -d "$HD" ] && [ -n "$3" ] || { echo "usage: expressions.sh PROJECT_DIR PROFILE_DIR OUT.vrm"; exit 2; }
CAM='{"center": [0.003, -0.08, 1.515], "ortho_scale": 0.24}'
if [ -f "$HD/profile.json" ]; then
  CAM=$(python3 -c "import json,sys; print(json.dumps(json.load(open(sys.argv[1])).get('lab_camera') or json.loads(sys.argv[2])))" "$HD/profile.json" "$CAM")
  export POLISH_PROFILE_JSON="$HD/profile.json"
  HD="$HD/expr-data"
fi
POLISH=${0:A:h:h}; W="$P/work"; E="$W/expr"
KIT=${KIT:-${P:h:h}}; B=${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}
mkdir -p "$E/int"
export POLISH_DIR="$POLISH" POLISH_HEAD_DATA="$HD" POLISH_BUILD_CONFIG="$W/build_character.json"
export POLISH_FRAME=$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(json.dumps(d.get('frame') or {'s':1.0,'t':[0,0,0]}))" "$POLISH_BUILD_CONFIG")
# face camera of the expression lab: the head profile's camera, carried into this head's frame
python3 - "$POLISH_FRAME" "$E/lab-config.json" "$CAM" <<'PY'
import json, sys
fr = json.loads(sys.argv[1]); s, t = fr['s'], fr['t']; cam = json.loads(sys.argv[3]); c = cam['center']
json.dump({"objects": ["Head"], "camera": {"center": [round(s * c[i] + t[i], 4) for i in range(3)], "front": [0, -1, 0], "up": [0, 0, 1], "ortho_scale": round(cam['ortho_scale'] * s, 4), "size": 800}}, open(sys.argv[2], 'w'))
PY
rm -rf "$E/ws"; (cd "$KIT" && node scripts/expression-lab.mjs init "$W/character.blend" "$E/ws" --config "$E/lab-config.json" > "$E/init.log" 2>&1); echo init $?
run() { $B -b "$E/ws/current.blend" --python-exit-code 1 --python "$POLISH/expr/run_studio.py" -- "$KIT/scripts/expression-studio.py" "$E/ws" "$1" 2>&1 | { grep -vE "^(Blender|Read blend|Info: Saved|Blender quit)|unfreed|Not freed|^$" || true; } | tail -${2:-6}; }
# another head than the profile's: find this head's parts in the workspace first (in the face frame) and use them
if python3 -c "import json,sys; sys.exit(0 if json.load(open(sys.argv[1])).get('hair_affine') else 1)" "$POLISH_BUILD_CONFIG"; then
  [ -f "$HD/overrides.json" ] && echo "note: profile eye point overrides are not used for another head"
  # mouth, nose and chin as measured before the build (profile frame)
  export POLISH_KNOWN_LANDMARKS=$(python3 -c "
import json,sys; m=json.load(open(sys.argv[1])); f=m['frame']; L=m.get('new_head',{}).get('landmarks',{})
print(json.dumps({k:[(v[i]-f['t'][i])/f['s'] for i in range(3)] for k,v in L.items()}))" "$W/measure/measure.json")
  o_=$(POLISH_PROFILE_OUT="$E" POLISH_FRAME_SCRIPT="$POLISH/profile/auto_head.py" run "$POLISH/expr/expr_build_frame.py" 4 | grep -oE 'AUTO_HEAD.{0,200}|Error.*|Traceback.*|not found.*' || true)
  echo "$o_"; [[ "$o_" == *AUTO_HEAD* ]] || { echo "stopped: parts of this head not found"; exit 1; }
  export POLISH_HEAD_DATA="$E/expr-data"
fi
o_=$(run "$POLISH/expr/expr_build_frame.py" 40 | tee "$E/expr-build.log" | grep -oE '"eyeX": \{.{0,120}|RUN_OK|Error.*|Traceback.*' || true)
grep -oE 'EXPR_BUILD .*' "$E/expr-build.log" | cut -c12- > "$E/expr-report.json" || true
echo "$o_"; [[ "$o_" == *RUN_OK* && "$o_" != *Error* ]] || { echo "stopped: expression build failed"; exit 1; }
run "$POLISH/expr/export_only.py" 2 | grep -oE "RUN_OK|Error.*" || { echo "stopped: export failed"; exit 1; }
python3 - "$W" "$E" <<'PY'
import json, sys
W, E = sys.argv[1:]
json.dump({"source": W + "/character.blend", "authored": E + "/ws/exports/expressions.blend", "blend": E + "/int/integrated.blend",
           "vrm": E + "/int/review.vrm", "fbx": E + "/int/integrated.fbx", "report": E + "/int/preservation.json"}, open(E + "/int/config.json", "w"))
PY
node "$POLISH/expr/mapping.mjs" "$E/ws/session.json" "$E/int/config.json" "$KIT"
(cd "$E/int" && rm -f review.vrm && $B --background --factory-startup --disable-autoexec --python-exit-code 1 --python "$KIT/scripts/integrate-expressions.py" -- "$E/int/config.json" > blender.log 2>&1) || { echo "stopped: expression integration failed (see $E/int/blender.log)"; exit 1; }
echo "integrate exit 0"
python3 "$POLISH/post/vrm_finalize.py" "$E/int/review.vrm" "$OUT" "$E/expr-report.json"
