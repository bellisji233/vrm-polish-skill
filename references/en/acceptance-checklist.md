[中文](../验收检查表.md) | English

# Acceptance Checklist

Before saying “finished,” inspect every item in the Director Console, save screenshots for static items and recordings or frame sequences for motion and transitions, and record real interactions. Mark uninspected items as “not yet checked.”

## Where to Inspect

- Inspect in the Director Console; do not draw conclusions from Blender or fixed-frame-rate test pages.
- Use the user's screen refresh rate (for example, 120Hz): time-dependent behavior such as skirt physics, motion, and smoothing can hide problems at 60 frames.

## Close-ups (Side by Side with the Baseline)

- Neck/head seam: front, 45°, and side; inspect shape and skin tone.
- Wrist/hand seam: back of hand, palm, and side.
- Armpits: with arms raised.
- Knees: at the lowest point of a deep squat, from front and side.
- Clothing/skin boundaries: hem, cuffs, and belt, from front, back, and low angles.
- Full body from the back, hair from the back.
- Sleeves: while flipping the palms and raising arms overhead.
- Small accessories: necklaces and earrings; check clarity up close.
- Elbows: elbow tips remain visible at about 110° flexion.
- Hands and face: resting the chin on a hand, hands beside the mouth, touching the head, and pushing upward from under the chin; check all five fingers, the thumb's middle joint, and palms. Inspect static frames and real-time playback separately; do not treat the former as proof of the latter. If fast hand-to-face motion causes a few frames of 1–3 mm contact, record location, frame count, and depth; do not use this limitation to dismiss sustained or deeper penetration. Also inspect camera-driven motion, writing test poses before avoidance.
- Head proportion: follow [Head Proportions](head-proportions.md) and use `head_ratio.sh` to measure skull top to chin and the same top point to soles; record head height (cm), stature (cm), and heads tall. Report differences of more than 0.3 heads from the user's target. After changes, recheck neck seams, hair, and expressions; also record arm span ÷ stature and chin-rest hand placement.

## Expressions

- Inspect every expression at 1.0 and 0.5, from the front and 45°.
- Sclera and irises must not show through during blinking; mouth corners must not tear when opening. Inspect 「啊」 (ah) from the front, 45°, and side: the mouth interior has depth, is closed, and has a tongue, without board edges, pink inner walls, or chin penetration. Check whole heads with existing pockets and face shells with generated mouth bags separately.
- Gaze: inspect left/right gaze at 0.6 and full strength, viewing the iris from the front and left/right 45°; no white layer may cover it. Happy or squinting expressions combined with gaze must not roll the eyes white.
- Mouth size: report resting and smiling mouth width relative to interpupillary distance (reference: about 0.76 at rest, preferred smile 0.55–0.62; Character 2 (人物2) measured 0.52 at rest and 0.61 smiling; these references are not mandatory universal targets). Angry and sad mouths stay closed, with corners only slightly downturned.

## Motion and Physics

- Inspect at least one deep-squat dance, one leg-raising dance, one dance with extensive arm movement, plus several short motions.
- Switch from a dance in progress to a short motion, or stop and return to idle; check whether skirt and hair settle back into place.
- The arms-overhead passage in Gokuraku Jodo: wrists must not twist into thin lines, and sleeve interiors must not be skin-colored.
- Open Director Console demo mode, watch for 20 seconds, and click expression buttons: it should only idle (blinking, slight head sway, small gaze movements), without the mouth opening and closing to simulate speech. If the dance library is empty, import your own motions and music first.
- Judge the visuals by eye; clipping scores are only a reference.

## Regression

- Turn every user-reported problem into a checklist item and recheck it in every subsequent round.
- Better numbers with worse visuals mean a worse result.
- When the skill adds a fix for one character, regenerate other characters made through the same workflow and run this checklist again.

## Configuration and Delivery Checks

| Symptom | Cause | Action and acceptance | Configuration key |
|---|---|---|---|
| Appearance changes after remeasurement | Manual parameters were not persisted | Compare manual settings before/after `--force` and confirm override values remain | `work/build_overrides.json`, `mouth_open`, `neck_widen.factor` |
| Hands deleted or recolored as clothing | Cuff-lining or skin-color removal extends beyond cuffs | Disable lining when retaining original hands; inspect hand backs, palms, and cuffs | `cuff_lining`, `template_hand`, `region_paint.cloth[].abs_x` |
| Joints thin or collapse | Helper bones or corrections are inactive | Check band for long sleeves and 4-segment twist for exposed forearms; move shoulders, knees, and elbows from neutral to key angles and back, checking elbows at 110° | `helper_bones`; 6 joint corrections are driven by angle in the Director Console |
| Combined mouth shapes or gaze exceed limits | Multiple channels drive them together | Check `mouthNarrow` width reduction and UV gaze clamping; inspect separate and combined expressions | `mouth_mood`, `mouth_open`, `extras.vrmPolish.mouthWidth/gazeUV` |
| No safety shorts under skirt or missing collisions | Plan not enabled | Verify this run's application records for both collision plans; check safety shorts from a low angle and confirm texture-only changes | `safety_shorts`, `work/skirt-colliders.json`, `work/skirt-extra-colliders.json` |
| Director Console initially blank or media fails | Characters, dances, and music are not bundled | With `defaultModel: null`, drag in a VRM; an empty library shows 「舞曲库为空。拖入 .vrma 动作和音乐后可播放」 (The dance library is empty. Drag in .vrma motions and music to play); follow `studio/MEDIA.zh-CN.md` and use `tools/add-media.py` to add media, then actually play and stop it | `studio.json`, `catalog.json`, `scripts/studio-media.json` |

The expression stage builds 77 shape keys; the final VRM has about 100 expressions (standard expressions, ARKit 52, gaze, anime decals, and 6 joint corrections). Verify bindings and drivers for the actual character; do not use a fixed total as a passing condition.

`set -e` + `pipefail` do not replace log inspection; see [Charakuru Integration](charakuru-integration.md) for current error-tolerance wrapper exceptions. Mark unrun items, missing-media items, or unobservable items as “not yet checked,” with reasons; do not substitute measurements from existing characters for this run's results.
