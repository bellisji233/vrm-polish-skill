[中文](../配合Charakuru.md) | English

# Using This Skill with Charakuru

Charakuru version 1.1.1.

## Responsibilities

Charakuru handles the workflow through weighting; this skill then takes over polishing, springs (hair and skirt physics), expressions, joint corrections, and acceptance checks. This skill does not modify kit files; when kit functionality is needed, it calls scripts from the user's own installation.

| Stage | Charakuru (workbench + kit skill) | This skill |
|---|---|---|
| Image generation (images) | 8 part images and 3 full-body orthographic views; user confirmation | — |
| Candidates (candidates) | Tripo generates 4 candidates each for the head and body; user selection | — |
| Parts and textures (materials) | Segmentation, classification, Smart UV, 4K textures, assembly; user adjusts head and body proportions | — |
| Rigging (rig) | Tripo rigging and reading back bone positions | `rig.sh upload` exports an upload file under 10 MB; `rig.sh check` checks left/right symmetry and mirrors corrections when fingers on one side are offset |
| Weights (rig) | Base-body weight transfer produces `weighted.blend` | `finish_weights.py` completes the process when separate small wrist accessories prevent weight calculation |
| **Handoff** | Copy `weighted.blend` to the project's `work/weights/` | Start here |
| Polishing | — | `prepare.sh` measures and configures; `polish.sh` builds the skull, neck transition, template hands, per-piece colors, and physics bones |
| Springs | Kit `spring-setup.py` (setup and checks), `apply-skirt-colliders.py` | `build.sh` calls them, then adds arm and hand colliders for the skirt |
| Expressions | The standard workflow uses a neutral face and fixed gaze; the expression-authoring workflow does not create a new mouth interior, teeth, or tongue | About 100 VRM expressions, a closed mouth bag, and a tongue; written through the kit's expression workspace and integration scripts (`expression-lab.mjs`, `integrate-expressions.py`), passing the kit's preservation checks |
| Joints and proportions | Head and body proportions are adjusted during materials and locked after rigging | Shoulder, knee, and elbow corrective shapes, safety shorts; `head_ratio.sh` changes head proportion on the weighted result |
| Registration | The workbench saves the completed VRM | When a request ID is supplied, register the confirmation model with springs back in the workbench and complete the request; the final deliverable is the VRM output by `polish.sh` |
| Acceptance and streaming | Workbench preview | Director Console (`studio/`) |

The following sections follow Charakuru's stages, noting where this skill connects and the issues encountered in practice.

## 0. Gates at Every Step

- **Stop if the input is unacceptable.** If a step's required input cannot be produced (Codex quota exhausted, Tripo failure, unsuitable reference images), pause that step and report it; do not substitute something else. For example, texture reference images must be newly drawn for this group of parts. Cropping and aligning part images does not make them valid references: Tripo will fill areas invisible from both front and back (under the chin, sides of the face) with incorrect content.
- **Accessory inventory.** After generating the character illustration, list every accessory: location, left or right side, and material (for example: black watch on the left wrist, dark bracelet on the right wrist, two silver necklaces, wallet chain on the left hip, silver hoops and black studs in both ears). Check against this inventory at every subsequent step.
- **Do not mix small rigid accessories into clothing groups.** Charakuru specifies grouping small accessories with their clothing; this works for printed patterns and buttons, but not for separate chains, watches, or bracelets that sit away from the clothing surface. Textures are projected from front and back, so clothing and skin colors bleed onto their sides; wrists occupy only a dozen or so pixels in full-body references, making bracelets and watches indistinguishable. Put them in separate accessory groups, or apply uniform material-based colors in this skill (`region_paint.metal`).
- **Add left and right views to texture references.** Tripo multi-view texturing has 4 slots: front, left, right, and back. With only front and back views, Tripo guesses shoulder tops, body sides, and the underside of the chin.
- **Inspect returned textures against the checklist.** Check 6 directions plus the underside of the chin, top of the head, armpits, and close-ups of every item in the accessory inventory against the character illustration. Register only after all pass. Checking only for 4096, matching meshes, and successful assembly is not acceptance.

## 1. Part Images and Orthographic Views

- Head images must include all hair; body images must use a T-pose.
- Changing outfits on the same character: reuse the 4 head images directly and regenerate only the 4 body images. Regenerating from the same images does not guarantee the same mesh; vertex-by-vertex reuse of a full head profile requires reusing the original candidate or original GLB.

## 2. Candidates

- Tripo multi-view: Smart Mesh P2.0, quads, face count 25000, generate 4. Face-count settings do not persist; check before each generation.
- For outfit changes using the same head, copy the 4 head candidates directly from the original project without spending more credits.
- Prefer body candidates with a larger gap between the legs; weight transfer and clipping are easier to handle.

## 3. Segmentation

- In Tripo's segmentation panel, select Auto → Simple (3–6 parts).
- For outfit changes using the same head, reuse the original head GLB, verify that it is byte-for-byte identical to the original, then reuse the original project's head segmentation results.

## 4. Textures

- When uploading a part FBX, enter X=0, Y=90, Z=0 in “Best angle” and confirm that the front faces forward before continuing.
- Do not draw hair in the head group's reference image (a Charakuru requirement): paint the face, ears, underside of the chin, and nape as skin.
- The kit's rendered wireframe guides sometimes show large black diagonal bands: a part's wireframe modifier has produced huge triangles; the model itself is intact. Re-render with the same camera parameters and remove wireframe vertices outside the model's bounds.
- After Smart UV unwrapping, click “Save.” If you switch to the next model without saving, the result is not retained (a prompt may not appear).
- An assembly error “Returned topology changed” usually means Tripo's coordinate precision caused individual faces to match neighboring vertices. Snap the returned model's vertices back to their corresponding original mesh vertices, save separately, then register.
- The workbench requires exactly 4 candidates each for the head and body. If a candidate failed to start, generate a replacement; registration appends candidates, up to 4.
- Do not include phrases such as “do not draw the body under the clothing” in reference-image prompts; image-generation safety filters will block them.
- Textured exports are ZIP files (FBX plus 4K base-color maps). Extract each into its own group's folder before registration.
- For outfit changes using the same head, the hair and head part meshes match the original project, so its 4K textures can be reused.

## 5. Proportion Adjustment

- **Keep head rotation at 0.** Proceeding with a rotated head leaves it tilted in the rest pose and misaligns expression coordinates.
- The head and neck must connect; inspect front, side, and back views.

## 6. Rigging

- In Tripo's Rig → skeleton preset, select **VRM 1.0 Humanoid** and confirm before running.
- The kit's head-plus-body FBX exceeds the browser's 10 MB upload limit when textures are included. Use `zsh polish/pipeline/rig.sh upload <project>` to export a version without textures (about 2 MB, with geometry and material slots identical to the kit export vertex by vertex), and upload that file.
- Tripo ignores the rig export filename; the download is named `tripo_convert_*.zip`.
- Before importing bones, run `zsh polish/pipeline/rig.sh check <returned FBX>`: it reports mirrored position differences between corresponding left/right joints greater than 1% of stature. If fingers are offset, it keeps the side closer to the finger mesh centers, mirrors it to the other side, and saves as `…-symmetric.fbx`. Import this file (`node scripts/import-bones.mjs`). Normal Tripo results have left/right differences within 0.7%.
- After bone import, the workbench locks head/body proportion editing, and the “Reload” button does not read files modified on disk. If only head proportion needs changing, use this skill's `head_ratio.sh` on the weighted result without rerigging. For other proportions or head rotation, edit a pre-import project copy, overwrite the project files following the kit's write checks, then refresh the workbench page.

## 7. Weights

- When the kit's weighting task finishes, `weighted.blend` remains in a `charakit-job-*` folder in the system temporary directory. Copy it to `work/weights/`; this is where this skill starts.
- Separate small wrist pieces such as bracelets or watches can cause “Automatic hand weights missing” at the weighting task's last step: the kit calculates automatic hand weights separately, and floating wrist pieces can cause calculation to fail for the entire hand region. Continue from the intermediate result in the task folder:
  `blender -b <charakit-job-*>/backups/transfer-*/weighted.blend --python polish/rig/finish_weights.py -- <kit> <project>/work/weights`
  It completes this step exactly as the kit does, except that on failure it removes accessory-group pieces and other small pieces and retries once; accessories inherit weights from the nearest skin.

## 8. This Skill

- With short sleeves and exposed forearms, template hands are tinted to the forearm skin and joined at the wrist (cut length 2.5 cm), with seams under watches and bracelets; emission is disabled on the template material. The purple version (紫色版) and the denim outfit have long sleeves and still use the old method.

- Start new heads with `assets/head-profile/`; full profiles are for outfit changes using the same head. Packaging currently supports only purple-head-type heads; see [Head Profiles](head-profiles.md).
- `prepare.sh <project> <head-profile>` measures and writes `work/build_character.json`. Inspect `work/measure/零件.jpg` before adding skin pieces (see Configuration).
- Run `polish.sh <project> <head-profile> <out.vrm>`.
- Supplying a request ID registers the confirmation model back in Charakuru and completes the request; the final deliverable is the VRM output by `polish.sh` (with expressions).

## 9. Polishing Integration Rules

| Symptom | Cause | Action | Configuration key |
|---|---|---|---|
| Head too small after rigging | Head height does not match stature | Run `zsh polish/pipeline/head_ratio.sh <project> <built.vrm> <target>`, then measure and polish again; no Tripo credits consumed | `work/weights/head_scale.json`; see [Head Proportions](head-proportions.md) |
| Manual values lost after `--force` | Generator does not read the old build configuration | Put manual values in `work/build_overrides.json`; nested objects merge by key, ordinary array keys replace entire arrays, and keys suffixed with `+` append arrays | `mouth_open`, `neck_widen.factor`, etc.; see [Configuration](configuration.md) |
| Skirt lacks colliders | Default physics does not cover the hem and arms adequately | First make a plan with the kit's `scripts/plan-skirt-colliders.py`; `build.sh` calls the kit's `apply-skirt-colliders.py`, then this repository's `polish/post/add_skirt_colliders.py` to add arm and hand collisions | `work/skirt-colliders.json`, `work/skirt-extra-colliders.json`; applied only when the files exist |
| Safety shorts needed under the skirt | Original texture has no safety shorts | `polish.sh` changes only the texture, adding no mesh | `safety_shorts: {"hem": 0.5, "material": "Material_lower_body", "palette": "lavender"}`; `hem` is the position 0.5 of the way from hip to knee |
| Hands disappear when retaining original hands | Hands and sleeves share material and color and are mistaken for lining | Enable cuff lining only when template hands replace the original hands; clothing skin-color removal stops at the measured cuff | `cuff_lining`, `template_hand`, `region_paint.cloth[].abs_x` |

## 10. Mouth Interior and Code-Calling Boundaries

Charakuru 1.1.1's `skills/avatar-expression-authoring/SKILL.md` states: 「口内・歯・舌・テクスチャを新造して欠点を隠しません」 (Do not create new mouth interiors, teeth, tongues, or textures to hide defects). Opening the mouth moves the existing lip edges without creating a new mouth interior, teeth, or tongue. This skill cleans up an existing mouth pocket or generates a closed mouth bag and adds a tongue. See [Troubleshooting](troubleshooting.md). Version source: [Charakuru v1.1.1](https://github.com/nanocle/Charakuru/releases/tag/v1.1.1).

This skill contains no Charakuru code; it only calls kit scripts. `expr_build_frame.py` uses the kit's own `signature`, passing only object views that report original positions; `finish_weights.py` calls the kit's `transfer.finish` unchanged, only substituting a `bpy` wrapper for the `body_finish` it loads. The kit's `import-bones.mjs`, `spring-setup.py`, `expression-lab.mjs`, and other scripts must come from the user's own Charakuru installation and are not copied into this repository.

## 11. Dependencies and Failure Handling

The polishing pipeline requires macOS, zsh, Blender 5.2 + VRM Add-on, Python 3 + numpy + Pillow, and Node.js 22. `BLENDER` points to the Blender executable, defaulting to `/Applications/Blender.app/Contents/MacOS/Blender`; `KIT` can specify the Charakuru root directory. The Director Console runs on macOS / Windows; this does not mean the polishing pipeline supports Windows.

Pipeline entry points enable `set -e` and `pipefail`; build, expression-integration, and post-processing failures should stop execution rather than deliver old artifacts. Exceptions remain: piece sheet rendering and template hand fitting commands in `prepare.sh` are wrapped in `|| true`; skirt application in `build.sh` is also wrapped in `|| true`, followed only by an output-file existence check. Therefore, automatic stopping on every substep failure cannot be guaranteed. On errors, check logs and output timestamps for the current run, complete failed steps, and rerun; do not treat old files as new deliverables.
