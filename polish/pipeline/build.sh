#!/bin/zsh
# Build work/character.blend for a Charakuru project: polish build -> kit spring setup -> review FBX -> spring audit.
# usage: build.sh PROJECT_DIR [REQUEST_ID]
#   PROJECT_DIR  the Charakuru project folder (projects/<id>), with work/weights/weighted.blend from the kit's rig step
#                and work/build_character.json (see references/配置说明.md)
#   REQUEST_ID   an open rig request in the app: the review model is registered and the request completed
# env: KIT (Charakuru kit root, default: two folders above PROJECT_DIR), BLENDER, APP_URL (default http://localhost:8780)
set -e; setopt pipefail
P=${1:A}; [ -d "$P/work" ] || { echo "usage: build.sh PROJECT_DIR [REQUEST_ID]"; exit 2; }
POLISH=${0:A:h:h}; W="$P/work"; R=$2
KIT=${KIT:-${P:h:h}}; [ -f "$KIT/scripts/spring-setup.py" ] || { echo "KIT not found: $KIT"; exit 2; }
B=${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}; APP_URL=${APP_URL:-http://localhost:8780}
$B -b "$W/weights/weighted.blend" --python-exit-code 1 -P "$POLISH/build_character.py" -- "$W/build_character.json" 2>&1 | grep -E "BUILD_OK|Error|Traceback" | cut -c1-200
rm -f "$W/character-springs.blend"
$B --background "$W/character-built.blend" --disable-autoexec --python-exit-code 1 --python "$KIT/scripts/spring-setup.py" -- setup "$W/spring-config.json" "$W/character-springs.blend" "$W/spring-plan.json" 2>&1 | grep -oE "CHARAKIT_SPRINGS_OK|Error.*" | head -2
[ -e "$W/character.blend" ] && mv "$W/character.blend" "$W/character-prev.blend"
if [ -f "$W/skirt-colliders.json" ]; then
  # a skirt: the kit's skirt collider plan for this outfit (scripts/plan-skirt-colliders.py, see references/配合Charakuru.md)
  python3 -c "import json,sys; c=json.load(open(sys.argv[1])); c['output_blend']=sys.argv[2]; json.dump(c,open(sys.argv[1],'w'),ensure_ascii=False,indent=1)" "$W/skirt-colliders.json" "$W/character.blend"
  $B --background "$W/character-springs.blend" --disable-autoexec --python-exit-code 1 --python "$KIT/scripts/apply-skirt-colliders.py" -- "$W/skirt-colliders.json" 2>&1 | grep -E "Error|Traceback" | head -3 || true
  [ -e "$W/character.blend" ] || { echo "stopped: skirt colliders were not applied"; exit 1; }
else
  cp "$W/character-springs.blend" "$W/character.blend"
fi
# arms and hands beside the hips: extra capsules on the skirt chains (work/skirt-extra-colliders.json, post/add_skirt_colliders.py)
if [ -f "$W/skirt-extra-colliders.json" ]; then
  $B --background "$W/character.blend" --disable-autoexec --python-exit-code 1 --python "$POLISH/post/add_skirt_colliders.py" -- "$W/skirt-extra-colliders.json" 2>&1 | grep -oE "EXTRA_COLLIDERS_OK [0-9]+|Error.*" | head -2
fi
rm -rf "$W/review"; mkdir -p "$W/review"
$B -b "$W/character.blend" --disable-autoexec -P "$POLISH/post/export_review.py" -- "$W/review/character-review.fbx" 2>&1 | grep -oE "EXPORTED|Error.*"
(cd "$W" && $B --background "$W/character.blend" --disable-autoexec --python-exit-code 1 --python "$KIT/scripts/spring-setup.py" -- audit "$W/spring-audit.json" 2>&1 | grep -oE "CHARAKIT_SPRINGS_OK|ValueError.*|Error: .*" | head -2)
if [ -n "$R" ]; then
  echo '{"input": "../project.charakit", "phase": "springs", "includesHair": true, "fbx": "review/character-review.fbx", "blend": "character.blend"}' > "$W/update-springs.json"
  (cd "$KIT" && node scripts/update-model.mjs "$W/update-springs.json" "$P/project.charakit" 2>&1 | tail -1 | cut -c1-160)
  (cd "$KIT" && node scripts/agent-session.mjs complete "$APP_URL" "$R" > "$W/last-complete.json" 2>&1); echo complete-exit $?
fi
