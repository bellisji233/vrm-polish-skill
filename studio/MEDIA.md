English | [中文](MEDIA.zh-CN.md)

# Dances, motions and music

The Director Console ships without dances, motions or music. Below are the sources of the library used during development. Download from the original pages, follow each page's terms, and add the files with `tools/add-media.py`.

Requires Node.js 18+ (to convert MMD motions) and ffmpeg (to cut music). Run the commands inside `studio/`, replacing file names with the paths you downloaded to.

```sh
python3 tools/add-media.py list             # show the library
python3 tools/add-media.py remove 夜色摇      # remove an entry
```

Reload the console page after adding. Motions are stored in `animations/`, music in `music/`, and the library list in `catalog.json`. Entry names are shown as buttons; the Chinese names below match the original library.

## Short motions · VRoid Project

| | |
|---|---|
| Download | [BOOTH: VRM Animation 7-pack](https://booth.pm/ja/items/5512385) (free, pixiv login required) |
| About | [VRoid announcement](https://vroid.com/en/news/6HozzBIV0KkcKf9dc1fZGW) |
| Terms | Commercial use allowed with the credit “Character animation credits to pixiv Inc.'s VRoid Project”; the files may not be redistributed in an extractable form. See the product page |

| Name | Meaning | File |
|---|---|---|
| 展示全身 | Show full body | `VRMA_01.vrma` |
| 打招呼 | Greeting | `VRMA_02.vrma` |
| 比耶 | Peace sign | `VRMA_03.vrma` |
| 射击 | Shoot | `VRMA_04.vrma` |
| 转圈 | Spin | `VRMA_05.vrma` |
| 模特姿势 | Model pose | `VRMA_06.vrma` |
| 下蹲 | Squat | `VRMA_07.vrma` |

```sh
python3 tools/add-media.py motion 打招呼 --motion VRMA_MotionPack/vrma/VRMA_02.vrma \
  --credit "Character animation credits to pixiv Inc.'s VRoid Project"
```

Add the other six the same way, changing the name and file.

## Dances · motions8 (motion and music in one folder)

| | |
|---|---|
| Download | GitHub [Carlutic/motions8](https://github.com/Carlutic/motions8); download the files in the folders below |
| Terms | The repository states that motion and audio rights stay with the original authors: personal use only, no redistribution, no commercial use |

| Name | Folder | Motion | Facial track | Music |
|---|---|---|---|---|
| 女王卡 (Queencard) | [QueenCard（短版）](https://github.com/Carlutic/motions8/tree/main/tracks/QueenCard%EF%BC%88%E7%9F%AD%E7%89%88%EF%BC%89) | `queencard motion by c卡萨.vmd` | — | `Queencard.wav` |
| 夜色摇 | [夜色摇](https://github.com/Carlutic/motions8/tree/main/tracks/%E5%A4%9C%E8%89%B2%E6%91%87) | `夜色摇.vmd` | `夜色摇表情.vmd` | `39650790142-1-30232.wav` |
| 小鹿乱撞 | [小鹿乱撞](https://github.com/Carlutic/motions8/tree/main/tracks/%E5%B0%8F%E9%B9%BF%E4%B9%B1%E6%92%9E) | `小鹿乱撞 动作.vmd` | — | `31714839045-1-30232.wav` |
| 左右猫猫摇 | [kici_ki_左右猫猫摇](https://github.com/Carlutic/motions8/tree/main/tracks/kici_ki_%E5%B7%A6%E5%8F%B3%E7%8C%AB%E7%8C%AB%E6%91%87) | `左右猫猫摇.vmd` | `左右猫猫摇表情.vmd` | `kici ki 左右猫猫摇给力嘎嘎BGM.wav` |
| 弹跳扣扣舞 | [弹跳扣扣舞（普通）](https://github.com/Carlutic/motions8/tree/main/tracks/%E5%BC%B9%E8%B7%B3%E6%89%A3%E6%89%A3%E8%88%9E%EF%BC%88%E6%99%AE%E9%80%9A%EF%BC%89) | `弹跳扣13舞.vmd` | `弹跳扣13舞表情.vmd` | `bgm.wav` |
| 恋爱条件 (Love Options) | [恋爱条件](https://github.com/Carlutic/motions8/tree/main/tracks/%E6%81%8B%E7%88%B1%E6%9D%A1%E4%BB%B6) | `恋爱条件最终.vmd` | `恋爱条件表情.vmd` | `BGM.wav` |

```sh
python3 tools/add-media.py dance 夜色摇 --motion 夜色摇.vmd --expression 夜色摇表情.vmd \
  --music 39650790142-1-30232.wav --category 抖音神曲
python3 tools/add-media.py dance 小鹿乱撞 --motion "小鹿乱撞 动作.vmd" --music 31714839045-1-30232.wav --category 抖音神曲
```

Leave out `--expression` for dances without a facial track. With these arguments the converted files are byte-identical to the development library.

## Dances · おんぞ (BowlRoll, motion only)

| | |
|---|---|
| Download | The BowlRoll file pages below (a BowlRoll login may be required) |
| Author | おんぞ: [BowlRoll](https://bowlroll.net/user/123543), [YouTube](https://www.youtube.com/channel/UClW4VZNzyQa4voFlcuurt4g) |
| Terms | Neither the file pages nor the bundled readme state terms of use; ask the author before use |
| Music | Not included. Get the song from a licensed source and cut it at the start time |

| Name | Motion | Song | Start | Length |
|---|---|---|---|---|
| Power舞 | [パワーダンス](https://bowlroll.net/file/348532): `パワーダンス.vmd` | TOOBOE “錠剤” [official MV](https://www.youtube.com/watch?v=cRFSbeHXFwk) | 59.52 s | 9.43 s |
| 喵喵 | [みゃおみゃお](https://bowlroll.net/file/342764): `みゃおみゃお.vmd` | 奏みみ “絶対王政♡みゃおみゃお” [official MV](https://www.youtube.com/watch?v=zdMhUtmCBus) | 20.11 s | 25.47 s |
| Reze舞 | [レゼダンス](https://bowlroll.net/file/346475): `レゼダンス.vmd`, correction `左腕修正用モーション.vmd` | 米津玄師 “IRIS OUT” [official MV](https://www.youtube.com/watch?v=LmZD-TU96q4) | not measured | 16.17 s |
| 极乐净土 | [極楽浄土](https://bowlroll.net/file/343534): `極楽浄土.vmd` | GARNiDELiA “極楽浄土” [official video](https://www.youtube.com/watch?v=yv32__UWhVs) | 56.80 s | 21.43 s |

The start time is where the dance begins in the full song, measured on the single releases (“錠剤” 3:25, “絶対王政♡みゃおみゃお” 2:35, “極楽浄土” 3:39). Versions with a different intro, such as music videos, start elsewhere; adjust by ear.

```sh
python3 tools/add-media.py dance Power舞 --motion パワーダンス.vmd --music jouzai.mp3 \
  --start 59.52 --length 9.43 --category 日本舞曲 --credit おんぞ
python3 tools/add-media.py dance Reze舞 --motion レゼダンス.vmd --overlay 左腕修正用モーション.vmd \
  --music iris_out.mp3 --start START_SECONDS --length 16.17 --category 日本舞曲 --credit おんぞ
```

`--overlay` applies a correction motion the author ships separately: for the same bone and frame the correction wins, as when loading both files in MMD one after the other.

## Other

| Item | Status |
|---|---|
| Comic marks (anger, sweat) | Drawn for this project; included |
| Characters | Not included. Drop your own `.vrm` into the window; imported characters are kept in the local browser |
| Bedroom props | Made for this project; included. You can also import your own `.glb` on the stage |

## Your own motions

Any VRM Animation (`.vrma`) or MMD motion (`.vmd`) can be added with the same commands. To play without adding to the library, drop a `.vrma` and a music file into the window.
