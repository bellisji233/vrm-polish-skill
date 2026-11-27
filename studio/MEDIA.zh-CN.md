[English](MEDIA.md) | 中文

# 舞蹈、小动作和音乐

导演台不附带舞蹈、小动作和音乐。下面是开发时所用曲库的来源。请从原页面下载，按各页面的条款使用，再用 `tools/add-media.py` 加进曲库。

需要：Node.js 18 以上（转换 MMD 动作），ffmpeg（裁剪音乐）。命令在 `studio/` 文件夹里运行；文件名换成你下载到的实际路径。

```sh
python3 tools/add-media.py list            # 查看曲库
python3 tools/add-media.py remove 夜色摇     # 移除
```

加完刷新导演台页面。动作文件保存在 `animations/`，音乐保存在 `music/`，曲库清单是 `catalog.json`。

## 小动作 · VRoid Project

| | |
|---|---|
| 下载 | [BOOTH：VRMアニメーション7種セット](https://booth.pm/ja/items/5512385)（免费，需登录 pixiv） |
| 介绍 | [VRoid 官方公告](https://vroid.com/en/news/6HozzBIV0KkcKf9dc1fZGW) |
| 条款 | 可商用，需署名「キャラクターアニメーション: ピクシブ株式会社 VRoidプロジェクト」；不得以可提取的形式再分发文件。详见商品页 |

| 名称 | 文件 |
|---|---|
| 展示全身 | `VRMA_01.vrma` |
| 打招呼 | `VRMA_02.vrma` |
| 比耶 | `VRMA_03.vrma` |
| 射击 | `VRMA_04.vrma` |
| 转圈 | `VRMA_05.vrma` |
| 模特姿势 | `VRMA_06.vrma` |
| 下蹲 | `VRMA_07.vrma` |

```sh
python3 tools/add-media.py motion 打招呼 --motion VRMA_MotionPack/vrma/VRMA_02.vrma \
  --credit "キャラクターアニメーション: ピクシブ株式会社 VRoidプロジェクト"
```

其余 6 个同样添加，只换名称和文件。

## 舞蹈 · motions8（动作和音乐在同一文件夹）

| | |
|---|---|
| 下载 | GitHub [Carlutic/motions8](https://github.com/Carlutic/motions8)，在下表的文件夹里下载各文件 |
| 条款 | 仓库说明：动作和音频版权归原作者，仅限个人使用，禁止再分发和商用 |

| 名称 | 文件夹 | 动作 | 表情 | 音乐 |
|---|---|---|---|---|
| 女王卡 | [QueenCard（短版）](https://github.com/Carlutic/motions8/tree/main/tracks/QueenCard%EF%BC%88%E7%9F%AD%E7%89%88%EF%BC%89) | `queencard motion by c卡萨.vmd` | — | `Queencard.wav` |
| 夜色摇 | [夜色摇](https://github.com/Carlutic/motions8/tree/main/tracks/%E5%A4%9C%E8%89%B2%E6%91%87) | `夜色摇.vmd` | `夜色摇表情.vmd` | `39650790142-1-30232.wav` |
| 小鹿乱撞 | [小鹿乱撞](https://github.com/Carlutic/motions8/tree/main/tracks/%E5%B0%8F%E9%B9%BF%E4%B9%B1%E6%92%9E) | `小鹿乱撞 动作.vmd` | — | `31714839045-1-30232.wav` |
| 左右猫猫摇 | [kici_ki_左右猫猫摇](https://github.com/Carlutic/motions8/tree/main/tracks/kici_ki_%E5%B7%A6%E5%8F%B3%E7%8C%AB%E7%8C%AB%E6%91%87) | `左右猫猫摇.vmd` | `左右猫猫摇表情.vmd` | `kici ki 左右猫猫摇给力嘎嘎BGM.wav` |
| 弹跳扣扣舞 | [弹跳扣扣舞（普通）](https://github.com/Carlutic/motions8/tree/main/tracks/%E5%BC%B9%E8%B7%B3%E6%89%A3%E6%89%A3%E8%88%9E%EF%BC%88%E6%99%AE%E9%80%9A%EF%BC%89) | `弹跳扣13舞.vmd` | `弹跳扣13舞表情.vmd` | `bgm.wav` |
| 恋爱条件 | [恋爱条件](https://github.com/Carlutic/motions8/tree/main/tracks/%E6%81%8B%E7%88%B1%E6%9D%A1%E4%BB%B6) | `恋爱条件最终.vmd` | `恋爱条件表情.vmd` | `BGM.wav` |

```sh
python3 tools/add-media.py dance 夜色摇 --motion 夜色摇.vmd --expression 夜色摇表情.vmd \
  --music 39650790142-1-30232.wav --category 抖音神曲
python3 tools/add-media.py dance 小鹿乱撞 --motion "小鹿乱撞 动作.vmd" --music 31714839045-1-30232.wav --category 抖音神曲
```

没有表情文件的舞蹈省略 `--expression`。按这些参数转换，结果和开发时的曲库逐字节相同。

## 舞蹈 · おんぞ（BowlRoll，只有动作）

| | |
|---|---|
| 下载 | 下表的 BowlRoll 文件页（下载可能需要登录 BowlRoll） |
| 作者 | おんぞ：[BowlRoll](https://bowlroll.net/user/123543)、[YouTube](https://www.youtube.com/channel/UClW4VZNzyQa4voFlcuurt4g) |
| 条款 | 文件页和压缩包里的 readme 没有写使用条款；使用前请向作者确认 |
| 音乐 | 不含音乐。从正版渠道获取歌曲，按「起点」裁剪 |

| 名称 | 动作 | 歌曲 | 起点 | 长度 |
|---|---|---|---|---|
| Power舞 | [パワーダンス](https://bowlroll.net/file/348532)：`パワーダンス.vmd` | TOOBOE《錠剤》[官方 MV](https://www.youtube.com/watch?v=cRFSbeHXFwk) | 59.52 秒 | 9.43 秒 |
| 喵喵 | [みゃおみゃお](https://bowlroll.net/file/342764)：`みゃおみゃお.vmd` | 奏みみ《絶対王政♡みゃおみゃお》[官方 MV](https://www.youtube.com/watch?v=zdMhUtmCBus) | 20.11 秒 | 25.47 秒 |
| Reze舞 | [レゼダンス](https://bowlroll.net/file/346475)：`レゼダンス.vmd`，修正 `左腕修正用モーション.vmd` | 米津玄師《IRIS OUT》[官方 MV](https://www.youtube.com/watch?v=LmZD-TU96q4) | 未测 | 16.17 秒 |
| 极乐净土 | [極楽浄土](https://bowlroll.net/file/343534)：`極楽浄土.vmd` | GARNiDELiA《極楽浄土》[官方视频](https://www.youtube.com/watch?v=yv32__UWhVs) | 56.80 秒 | 21.43 秒 |

起点是舞蹈在完整歌曲里开始的位置，在单曲音源上测得（《錠剤》3:25、《絶対王政♡みゃおみゃお》2:35、《極楽浄土》3:39）。MV 等带前奏的版本起点不同，需要按耳朵微调。

```sh
python3 tools/add-media.py dance Power舞 --motion パワーダンス.vmd --music 錠剤.mp3 \
  --start 59.52 --length 9.43 --category 日本舞曲 --credit おんぞ
python3 tools/add-media.py dance Reze舞 --motion レゼダンス.vmd --overlay 左腕修正用モーション.vmd \
  --music IRIS_OUT.mp3 --start 起点秒数 --length 16.17 --category 日本舞曲 --credit おんぞ
```

`--overlay` 把作者另附的修正动作叠到主动作上，同一骨骼同一帧以修正为准，和在 MMD 里先后读入两份动作相同。

## 其他

| 内容 | 状态 |
|---|---|
| 漫符（生气、汗滴） | 为本项目绘制，随导演台提供 |
| 角色 | 不附带。把自己的 `.vrm` 拖进窗口；导入的角色保存在本机浏览器 |
| 卧室道具 | 为本项目生成，随导演台提供；也可在舞台里导入自己的 `.glb` |

## 自己的动作

任何 VRM Animation（`.vrma`）或 MMD 动作（`.vmd`）都可以用同样的命令添加。也可以不进曲库，直接把 `.vrma` 和音乐拖进窗口临时播放。
