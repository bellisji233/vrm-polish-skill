#!/bin/zsh
# Head-to-body ratio (heads tall = stature / head height, the head measured from the top of the skull to the chin).
# usage: head_ratio.sh BUILT.vrm                      print the ratio of a built model
#        head_ratio.sh PROJECT_DIR BUILT.vrm TARGET   scale the head of PROJECT/work/weights/weighted.blend about the
#                                                     head joint so the next build has TARGET heads; then run
#                                                     prepare.sh --force and polish.sh again
# The first run keeps the weight result as work/weights/weighted-orig.blend and every later run scales that original
# (work/weights/head_scale.json records the scale). Recommended ratios: references/头身比.md.
# env: BLENDER
set -e; setopt pipefail
H=${0:A:h:h}; B=${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}
if [ $# -eq 1 ]; then python3 "$H/measure/head_ratio.py" measure "$1"; exit 0; fi
P=${1:A}; VRM=${2:A}; TARGET=$3
[ -n "$TARGET" ] && [ -f "$P/work/weights/weighted.blend" ] && [ -f "$VRM" ] || { echo "usage: head_ratio.sh PROJECT_DIR BUILT.vrm TARGET"; exit 2; }
WD="$P/work/weights"; [ -f "$WD/weighted-orig.blend" ] || cp "$WD/weighted.blend" "$WD/weighted-orig.blend"
CUR=$(python3 -c "import json,sys,os; p=sys.argv[1]; print(json.load(open(p))['scale'] if os.path.isfile(p) else 1.0)" "$WD/head_scale.json")
PLAN=$(python3 "$H/measure/head_ratio.py" plan "$VRM" "$TARGET" "$CUR"); echo "$PLAN"
K=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['scale'])" "$PLAN")
$B -b "$WD/weighted-orig.blend" --python-exit-code 1 --python "$H/measure/head_ratio.py" -- apply "$K" "$WD/weighted.blend" 2>&1 | grep -E "HEAD_SCALE_OK|Error|Traceback" | cut -c1-300
python3 -c "import json,sys,time; json.dump({'scale': float(sys.argv[2]), 'target': float(sys.argv[3]), 'measured_on': sys.argv[4], 'at': time.strftime('%Y-%m-%d %H:%M')}, open(sys.argv[1], 'w'))" "$WD/head_scale.json" "$K" "$TARGET" "$VRM"
echo "next: zsh $H/pipeline/prepare.sh $P <头部档案> --force  &&  zsh $H/pipeline/polish.sh $P <头部档案> <输出.vrm>"
