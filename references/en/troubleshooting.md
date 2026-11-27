[中文](../通用问题手册.md) | English

# Troubleshooting

Common problems in models made with Charakuru, organized by symptom. Records fixes and measurements for the purple version (紫色版), Lavender Denim (薰衣草牛仔), and Character 2 (人物2). Example measurements are not guaranteed values for other characters.

## Head and Face

### Back of the Head Is Open, Like a Mask

- **Symptom**: the back of the head is open, like a mask.
- **Cause**: the Tripo-generated head has only a front face and hairstyle, without a closed skull; the interior becomes visible when turning or lowering the head.
- **Action**: fit a closed skull to the inside of the hair, sampling surrounding skin colors at seams. Configure `skull`.
- **Configuration key**: `skull`.

### Neck and Head Are Disconnected or Differ in Color

- **Symptom**: neck and head are disconnected or differ in color.
- **Cause**: head and body are generated separately; the neck is a short stump inserted into a flat-bottomed head, and the generated body's neck also has painted shadows.
- **Action**: add a ring of transitional skin around the neck, blending from neck color to head color (`neck_loft`). First unify the neck piece with the facial skin tone and flatten generated shadows (`region_paint.skin`); this must precede the neck transition so it samples the corrected colors.
- **Configuration keys**: `neck_loft`, `region_paint.skin`.

### Chin Creases or Hair Fragments Around the Mouth

- **Symptom**: chin creases or hair fragments around the mouth.
- **Cause**: the Tripo mesh has hard folds at the jaw; fragments of the hair mesh remain inside the face.
- **Action**: `jaw_round` rounds the jaw; `hair_cavity_box` removes hair fragments near the mouth and nose.
- **Configuration keys**: `jaw_round`, `hair_cavity_box`.

### Bangs Hide the Eyebrows

- **Symptom**: bangs hide the eyebrows.
- **Cause**: bangs obscure separate eyebrow components.
- **Action**: `brow_overlay` duplicates eyebrows in front of the bangs, composited with transparency.
- **Configuration key**: `brow_overlay`.

### Head Too Small Relative to the Body

- **Symptom**: head too small relative to the body.
- **Cause**: head height does not match stature; uniformly scaling the entire character does not change heads tall.
- **Action**: measure heads tall with `zsh polish/pipeline/head_ratio.sh built.vrm`. To change it, scale the weighted result around the head joint, then run `prepare.sh --force` and `polish.sh`, without returning to Charakuru or rerigging. See [Head Proportions](head-proportions.md) for recommendations, the Character 2 example of 8.89 → 8.0 heads tall, and hand placement relative to the face during dance.
- **Configuration key**: `work/weights/head_scale.json`, generated from the command-line target value.

## Expressions

### Mouth Too Wide, Even Wider with Combined Mouth Shapes

- **Symptom**: mouth too wide, even wider with combined mouth shapes.
- **Cause**: lateral displacements from multiple mouth shapes add together, exceeding visible mouth-corner width.
- **Action**: limit every mouth shape to the wider of the happy and sad shapes, measured at the visible mouth corners (on closed heads, lip-gap endpoints are hidden inside the mouth corners); open-mouth shapes generally add no width. When facial tracking combines multiple mouth shapes, the Director Console uses `mouthNarrow` each frame according to `extras.vrmPolish.mouthWidth` to retract the excess.
- **Configuration keys**: `extras.vrmPolish.mouthWidth`, `mouthNarrow` (export metadata and expression name).

### 「啊」 (ah) Opens Too Far and Moves the Nose

- **Symptom**: 「啊」 (ah) opens too far and moves the nose.
- **Cause**: transferred mouth-shape amplitude does not match this head's mouth width.
- **Action**: `mouth_open` sets the maximum opening height for 「啊」 (ah) (as a mouth-width multiplier; start at 0.6 times for realistic faces, about 1.1 times for anime). It only reduces shapes and applies to `aa/ih/ou/ee/oh/happy_mouth/surprised_mouth`, not every final open-mouth shape. When unset, new-head `MOUTH_GAIN` may still reduce it; mouth deformation holds the nose fixed (`NOSE_HOLD`).
- **Configuration key**: `mouth_open`; put persistent values in `work/build_overrides.json`.

### Angry and Sad Mouth Curves Are Excessive

- **Symptom**: angry and sad mouth curves are excessive.
- **Cause**: the kit's angry mouth shape bares teeth: the upper-lip center arches upward 6.6 mm and mouth corners pull outward to smile width.
- **Action**: limit to natural expression amplitudes (this implementation's default production limits, not universal anthropometric findings): width no greater than the closed mouth, upper-lip center rise ≤ 0.04, mouth-corner drop ≤ 0.06, and lip-gap opening ≤ 0.03 mouth widths. When anger is predominantly teeth-baring, replace it with pressed lips pulled downward (0.8 times the sad deformation). Configure `mouth_mood`; it can be disabled for anime styles.
- **Configuration key**: `mouth_mood`.

### Open Mouth Shows Backing Edges or Pink Inner Walls

- **Symptom**: open mouth shows backing edges or pink inner walls.
- **Cause**: when a front-only face shell uses a shallow backing to conceal the mouth interior, 45° and side views reveal the board edge and pink inside of the face shell. Charakuru 1.1.1's expression skill explicitly does not create new mouth interiors, teeth, or tongues; opening the mouth only moves existing lip edges.
- **Action**: use a closed mouth bag for both head types, with visible depth and tongue when open. Closed whole heads (Character 2 type) use Tripo's existing pocket, about 3.5 cm deep; split upper and lower lips by connectivity, let each inner lip follow its own lip, darken toward the interior, and use faces connecting the upper and lower halves as a dark rear wall.
- **Action**: generate a bag for front-only face shells (the purple version type). Its opening sits 3 mm behind the skin around the mouth, invisible at rest; horizontal radius is 1.35 half-mouth widths and vertical radius is 0.9 half-mouth widths. It extends inward about 1.1 mouth widths, about 28 mm for the purple version, closing over 8 rings. The lower half follows the middle of the lower lip and the upper half follows the upper lip; delete the original light rear wall connecting upper/lower lip folds, and darken the interior with depth. Set all interior normals to face forward (the same approach as eyeballs) for uniform toon-shaded color without light/dark blotches. Place the tongue at the bottom, about 0.42 times the bag depth inward.
- **Configuration key**: `mouth_bag`, enabling face-shell bags by default; `false` reverts face shells to the old backing, while closed whole heads still use their original pocket. See [Configuration](configuration.md) for bag fields.
- **Acceptance**: inspect 「啊」 (ah) from the front, 45°, and side; the mouth interior is closed, without board edges or pink inner walls.

### Mouth Opens and Closes by Itself in Demo Mode

- **Symptom**: mouth opens and closes by itself in demo mode.
- **Cause**: the old demo mode cycled expressions and simulated speech (driving 「啊」 (ah), 「咿」 (ee), and 「呜」 (oo) mouth shapes with sine waves), making expression buttons appear to trigger mouth motion.
- **Action**: demo mode should only idle: blinking, slight head sway, and small gaze movements, without simulated speech. Observe for 20 seconds, then click expression buttons.
- **Configuration key**: Director Console runtime mode; no build configuration key. `studio.json.demo.dance` selects the demo dance track; it is not an automatic-speech toggle.

### A White Layer Covers the Iris in Sideways Gaze

- **Symptom**: a white layer covers the iris in sideways gaze.
- **Cause**: after a painted iris is separated into a layer, deformation translates it along a curved surface; deformation interpolates linearly, causing it to sink behind the sclera halfway through. Sclera in eye-corner shadows can also be classified as eyelids and cover the iris.
- **Action**: translate the iris texture for gaze (one material per eye, `textureTransformBinds`), keeping the mesh stationary against the eyeball; heads with separate iris components still use geometric motion. Expand eyelid-layer transparency into shadowed sclera of the same hue; fill the iris portion hidden by the eyelid using visible colors at the corresponding radius.
- **Configuration key**: `iris_layer`; exports `textureTransformBinds`.

### Eyes Roll White When Happy or Squinting

- **Symptom**: eyes roll white when happy or squinting.
- **Cause**: eye-closing deformations push irises behind the eyelids; the separated iris layer moves behind the eyeball as soon as it is pushed.
- **Action**: do not move iris layers backward with eye closure; calculate gaze amplitude from each eye's opening. The Director Console caps deformation weights at 1 (preset and face-tracked gaze can add together when sharing a deformation).
- **Configuration key**: `iris_layer`; `extras.vrmPolish.gazeUV`.

## Hands

### Fingers Stick Together Like Gloves

- **Symptom**: fingers stick together like gloves.
- **Cause**: Tripo's finger gaps reach only the second knuckle; weights bleed into adjacent fingers (3–5% on average, 15–30% in individual cases).
- **Action**: replace with MakeHuman template hands (CC0), fitted to this character's own finger lengths (`polish/hand/`, configuration `template_hand`); beyond the knuckles, retain only the finger's own weights (`finger_clean`).
- **Configuration keys**: `template_hand`, `finger_clean`.

### Ragged Pink Lining Protrudes from Cuffs

- **Symptom**: ragged pink lining protrudes from cuffs.
- **Cause**: texture projection puts hand color on cuff interiors; when cuffs are shorter than the generated wrists, lining edges become visible.
- **Action**: enable only when template hands replace original hands. Delete lining faces protruding beyond the cuffs; the template hand's short forearm tube fills the opening. Repaint remaining lining with sleeve colors. Disable this when retaining generated hands: hands and sleeves share material and color and will be deleted together. The purple version once lost 4005 faces, making the entire hand disappear.
- **Configuration keys**: `cuff_lining` (`delete: true`), `template_hand`; remove `cuff_lining` or set it to `false` when retaining original hands.

### Wrist Twists into a Rope or Thin Line

- **Symptom**: wrist twists into a rope or thin line.
- **Cause**: all hand rotation is concentrated on one bone; motion files (especially MMD conversions) merge wrist-twist bones into the forearm, whose axial rotation can reach 150°. After the Director Console transfers forearm axial rotation to the hand, long sleeves no longer twist, but exposed forearms rotate within only a few centimeters at the wrist and collapse into a thin line (Character 2, Gokuraku Jodo).
- **Action**: use a wrist helper bone for long sleeves (`band` in `helper_bones`); exposed forearms automatically use segmented forearm twist (`twist`: 4 bones along the forearm rotate by 1/4–4/4 of the hand rotation, exported as VRM roll constraints).
- **Configuration key**: `helper_bones`.

### Hands Penetrate the Mouth or Face

- **Symptom**: hands penetrate the mouth or face.
- **Cause**: cross-sectional ellipses push only horizontally and cannot push out fingers moving upward from under the chin; checking only the middle finger also misses other fingers.
- **Action**: when loading the model, `studio/arm-avoid.js` voxelizes the face and skull into a 5 mm distance field, excluding hair, eyes, decals, and the neck transition. Majority voting across scans in three directions determines inside/outside even for meshes with openings; within 1 cm of the surface, exact distances are calculated from triangles, while farther distances propagate through chamfer scans. Loading computation takes about 0.1–0.2 seconds.
- **Action**: check the distal joints and tips of all five fingers, the thumb's middle joint, and two palm points, pushing outward along face-surface normals. Forearms and upper arms still push outward using head cross-sections (distance-field normals point upward at the crown and would push a forearm crossing a large head inward, as at 2 seconds in Gokuraku Jodo). Use least squares at the deepest point to distribute motion between upper arm and elbow. Processing order: arm penetration through the head first, hand-face contact second, then soft contact such as sleeves against the chest; the last two steps push only the hands. Neck contact is treated as hand-face contact. Push-out follows in about 1 frame (time constant 0.004 seconds), releasing slowly with a 0.18-second time constant; maximum upper-arm outward movement is about 26°, elbow adjustment about 23°.
- **Configuration keys**: Director Console module options `maxHead` (default 0.45 rad), `maxElbow` (default 0.4 rad), `tauInFace` (default 0.004 seconds), `tauOut` (default 0.18 seconds); these are not `build_character.json` keys.

Measured during Character 2's real-time Reze playback: frames with hands inside the head fell from 138 → 39, and frames deeper than 5 mm from 116 → 16. Static frame-by-frame inspection of the 8-head-tall version found no fingers inside the head; during real-time playback, fast hand-to-face motion still causes a few frames of transient 1–3 mm contact. The camera-driven path was given the same arm pose before avoidance: without avoidance, 8 finger points were inside the head, with maximum depth 9.5 mm; after avoidance, 0. These are existing measurements, not a guarantee of zero penetration for every motion.

## Deformation

### Shoulders Collapse with Raised Arms, Knees Flatten in Deep Squats, Elbow Tips Disappear When Bent

- **Symptom**: shoulders collapse with raised arms, knees flatten in deep squats, elbow tips disappear when bent.
- **Cause**: linear skinning loses volume at large angles.
- **Action**: `polish/post/shoulder_fix.py` generates shoulder, knee, and elbow corrective shapes (differences between dual-quaternion and linear skinning at key angles); the Director Console drives them by joint angle, with 110° as the elbow correction's key angle.
- **Configuration key**: none; left/right `corrShoulder`, `corrKnee`, and `corrElbow` corrections are generated automatically.

### Crotch Stretches

- **Symptom**: crotch stretches.
- **Cause**: the kit assigns crotch-centerline vertices entirely to one leg, creating left/right asymmetry and abrupt pelvis-weight changes within a few centimeters.
- **Action**: automatically add `crotch_blend` after measuring the crotch: keep the centerline symmetric and blend toward the pelvis from crotch bottom to hip joint. All pants and shorts need this; older characters must be regenerated after this step is added to the skill.
- **Configuration key**: `crotch_blend`.

### Top Clips Through Pants or Skirt

- **Symptom**: top clips through pants or skirt.
- **Cause**: clothing layers follow torso bones in different proportions and diverge when bending or twisting.
- **Action**: give layers at the same height and direction identical torso-weight proportions (`waist_blend`).
- **Configuration key**: `waist_blend`.

## Textures

### Skin-Colored Clothing Edges and Blurry Small Accessories

- **Symptom**: skin-colored clothing edges and blurry small accessories.
- **Cause**: 4K textures project front and back reference images onto the mesh. Skin colors project onto hem undersides, cuff interiors, belt edges, and necklaces touching the neck. Correcting based on “whether the texture color resembles skin” treats these errors as skin and makes them more obvious.
- **Action**: **distinguish skin from clothing by mesh piece, not color** (`region_paint`):
  - Unify skin pieces (neck, exposed waist) with the facial skin tone;
  - Replace skin colors on clothing pieces with surrounding fabric colors; for long sleeves, `region_paint.cloth[].abs_x` stops at the measured cuff without touching hands outside it;
  - Unify the color of complete same-colored rings such as belts by height band;
  - Color small accessories (necklace beads) separately.
- **Do not**: paint entire downward-facing clothing surfaces one color; this creates hard, jagged boundaries.
- **Configuration key**: `region_paint`.

### Inner Thighs, Armpits, or Sleeve Interiors Are Too Dark or Skin-Colored

- **Symptom**: inner thighs, armpits, or sleeve interiors are too dark or skin-colored.
- **Cause**: these faces are invisible in reference images from all four directions, so Tripo paints them dark (denim outfit inner-thigh brightness 0.57 versus front 0.71), or paints skin colors from the arms and legs inside them (Character 2's short-sleeve lining).
- **Action**: match invisible fabric faces channel by channel to nearby visible portions of the same fabric, processing only overly dark or warm areas (`region_paint.cloth.lift_hidden`); brightness-only correction can turn saturated shadows vivid purple. Process adjacent pieces sharing material and color (sleeves, lining) together. When unifying arm skin tones, sample only outward-facing faces; sleeve lining faces the arm and is not skin.
- **Configuration keys**: `region_paint.cloth[].lift_hidden`, `siblings`, `hand_skin`.

- **Note**: adjacent pieces sharing material and color (`siblings`) are found by bounding-box overlap; lower-body clothing (pants) and shoes often share a material, so shoes can be included and downward-facing surfaces such as soles recolored to match the pants (Character 2's white soles became gray-brown). Set `"siblings": false` on a separate `cloth` entry for lower-body clothing; to process only invisible faces without removing skin colors, set `"warm": 1.0` (Character 2's khaki pants append this entry through `"region_paint": {"cloth+": [...]}` in `build_overrides.json`).

## Physics

### Skirt Flies Around, Gets Stuck at the Hips, or Jitters Near Hands

- **Symptom**: skirt flies around, gets stuck at the hips, or jitters near hands.
- **Cause**: VRM spring-bone chains are independent, without inter-chain constraints; there is no collider between the hips; arm colliders in the model file may be misplaced (measured 13 cm away from the forearm).
- **Action**: the Director Console uses bone-based cloth to take over bones whose names start with `Skirt`: inter-chain constraints, arm and leg collisions created from bone positions, crotch constraints, and flip-up limits.
- **Configuration key**: `skirt`; Director Console `Skirt` bone-chain detection.

### Long, Wide Skirts Clip During High Leg Raises or Deep Squats

- **Symptom**: long, wide skirts clip during high leg raises or deep squats.
- **Conclusion**: for bone-driven long, wide skirts, preventing clipping conflicts with preventing excessive flying; both cannot be fully achieved. Prefer short skirts, pants, or fitted skirts in the design.
- **Cause**: bone driving and independent skirt chains cannot cover all cloth contacts.
- **Action**: prioritize clothing-design changes; report clipping limitations if retaining a long, wide skirt.
- **Configuration keys**: `skirt`, `skirt_leg_follow`, `skirt_contact`.

## Bones

### Finger Joints on One Side Are Offset

- **Symptom**: finger joints on one side are offset.
- **Cause**: Tripo occasionally places finger joints on one side about 1.4 cm off.
- **Action**: check left/right symmetry before importing bones (mirrored joint-position differences must not exceed 1% of skeleton height); mirror from the other side if offset.
- **Configuration key**: none; `rig.sh` `check`.

### Head Remains Tilted

- **Symptom**: head remains tilted.
- **Cause**: head rotation was applied during Charakuru proportion adjustment, leaving the rest pose tilted after bone import.
- **Action**: verify head rotation is 0 before confirming proportions. Bone import locks proportion editing in the workbench; changing it requires returning to the project's pre-import state. See Charakuru Integration, step 6.
- **Configuration key**: `Charakuru` head rotation.

## Acceptance

### Declared Finished, but the User Still Sees Problems

- **Symptom**: declared finished, but the user still sees problems.
- **Cause**: inspection only in Blender, only at a fixed frame rate, or only through numbers.
- **Action**: inspect in the Director Console at the user's screen refresh rate, capture each item in the fixed close-up checklist, and compare side by side with the baseline; see [Acceptance Checklist](acceptance-checklist.md).
- **Configuration key**: none; record checks using the acceptance checklist.

## Configuration and Pipeline

| Symptom | Cause | Action | Configuration key |
|---|---|---|---|
| Manual values disappear after remeasurement | Generator does not merge the old `build_character.json` | Write persistent values to the override file; nested objects merge by key, ordinary array keys replace entire arrays, and keys suffixed with `+` append arrays | `work/build_overrides.json` |
| Sleeves clip through torso when lowered | Joints are not centered in sleeves, or the static sleeve shape is unsuitable | Inspect the model, adjust joints, fit sleeves, and check the return from raised arms | `arm_joints`, `sleeve_fit` |
| Cuffs clip through palms during wrist rotation | Cuffs follow only the forearm | Assign some hand weight by cuff region | `cuff_follow` |
| Skirt waist and thighs protrude through skirt | Close-fitting skirt regions have different weights from the body | Transfer body weights at contact regions and make local skirt chains follow legs; long, wide skirts may still clip | `skirt_contact`, `skirt_leg_follow` |
| Skirt lacks collisions or safety shorts | No collision plan or texture configuration supplied for this outfit | Apply the kit's skirt plan, then add arm and hand collisions; safety shorts modify only the texture | `work/skirt-colliders.json`, `work/skirt-extra-colliders.json`, `safety_shorts` |
| Output file remains after a script error | Some commands have error-tolerance wrappers; file existence does not prove the current run succeeded | Check logs and output timestamps, complete failed steps, and rerun; see [Charakuru Integration](charakuru-integration.md) | None; entry points use `set -e` + `pipefail`, but exceptions remain |

Character 2 preserves `mouth_open: 0.6` and `neck_widen.factor: 1.1` through the override file. The purple version preserves `arm_joints`, `cuff_follow`, `skirt_leg_follow`, `sleeve_fit`, hand skin-tone parameters, and safety shorts. See [Configuration](configuration.md) for fields.
