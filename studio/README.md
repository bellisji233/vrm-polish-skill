English | [中文](README.zh-CN.md)

# Director Console

A browser console for streaming and checking VRM avatars: the webcam drives the face, head, arms and fingers; dances and short motions play on switchable stages. The bedroom stage props are included.

## Open

| System | How |
|---|---|
| macOS | Install Python 3, double-click `start-mac.command` |
| Windows | Install Python 3, double-click `start-windows.bat` |
| Manual | Run `python3 -m http.server 8190` in this folder and open http://localhost:8190/ |

The interface is in Chinese. Use Chrome or Edge. The first launch needs an internet connection: three.js and the webcam tracking models load from a CDN.

## Characters

No character is included. Drop a `.vrm` into the window; imported characters are kept in the local browser and restored next time.

Any VRM works, and face driving depends on the expressions the model has: models with ARKit 52 are driven with perfect sync, others with the VRM standard expressions. Models polished with [vrm-polish](../README.md) carry about 100 expressions and shoulder, knee and elbow correctives.

## Dances and motions

None are included. [MEDIA.md](MEDIA.md) lists the sources of the development library, where to download each item, and the command to add it.

```sh
python3 tools/add-media.py dance 夜色摇 --motion 夜色摇.vmd --expression 夜色摇表情.vmd --music bgm.wav
```

VRM Animation (`.vrma`) and MMD motions (`.vmd`, converted automatically) are supported. To play something once, drop a `.vrma` and a music file into the window.

## Default character and demo

To open the console with a character already loaded, put the file in `models/` and edit `studio.json`:

```json
{
  "defaultModel": {"url": "models/character.vrm", "name": "Display name"},
  "demo": {"dance": "夜色摇"}
}
```

`demo.dance` is the dance used by the demo button, matched against library names (a partial name works). The demo plays that dance with a slow orbiting camera.

## Publishing this folder

Maintainers build this folder from the working console:

```sh
zsh scripts/publish-studio.sh VIEWER_DIR [DEFAULT.vrm DISPLAY_NAME] [DEMO_DANCE]
```

The page code and `tools/` are always copied. Media are copied only when marked `approved: true` in `scripts/studio-media.json`, and the library lists only the files actually copied. The target media folders are emptied first, so do not keep the only copy of anything there.

## Known limits

- Fast hand-to-face movement can leave a few frames of 1–3 mm contact.
- Wide long skirts clip during high kicks and squats.
- Webcam tracking: after a hand is lowered out of the picture, the pose model sometimes still places the wrist in front of the chest, and the avatar's hand stays raised partway.
- Webcam arm motion is not fully smooth: the face, hand and pose models take turns, so each runs at about a third of the camera frame rate (about 10 times a second with a 30 fps camera). The frames in between are interpolated, so fast movements can look stepped or lag.
- Check motion in real-time playback with the [acceptance checklist](../references/en/acceptance-checklist.md); still frames do not replace it.
