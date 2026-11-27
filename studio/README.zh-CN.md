[English](README.md) | 中文

# 皮套导演台

浏览器里的 VRM 直播和验收台：摄像头驱动表情、头部、手臂和手指，播放舞蹈和小动作，切换舞台。卧室舞台的道具随导演台提供。

## 打开

| 系统 | 方法 |
|---|---|
| macOS | 安装 Python 3，双击 `start-mac.command` |
| Windows | 安装 Python 3，双击 `start-windows.bat` |
| 手动 | 在本文件夹运行 `python3 -m http.server 8190`，打开 http://localhost:8190/ |

用 Chrome 或 Edge。首次打开需要联网，three.js 和摄像头识别模型从 CDN 加载。

## 角色

不附带角色。把 `.vrm` 拖进窗口即可；导入的角色保存在本机浏览器，下次打开自动恢复。

任何 VRM 都能用，表情驱动取决于模型自带的表情：有 ARKit 52 时按完美同步驱动，否则用 VRM 标准表情。用 [vrm-polish](../README.zh-CN.md) 精修的模型带约 100 个表情和肩、膝、肘修正形态。

## 舞蹈和小动作

不附带。开发时所用曲库的来源、下载地址和添加命令见 [MEDIA.zh-CN.md](MEDIA.zh-CN.md)。

```sh
python3 tools/add-media.py dance 夜色摇 --motion 夜色摇.vmd --expression 夜色摇表情.vmd --music bgm.wav
```

支持 VRM Animation（`.vrma`）和 MMD 动作（`.vmd`，自动转换）。只想临时播放时，把 `.vrma` 和音乐直接拖进窗口。

## 默认角色和演示

要让导演台打开就显示某个角色，把文件放进 `models/`，修改 `studio.json`：

```json
{
  "defaultModel": {"url": "models/角色.vrm", "name": "显示名"},
  "demo": {"dance": "夜色摇"}
}
```

`demo.dance` 是「播放演示」使用的舞曲名，按曲库名称匹配，可写一部分。演示会播放这支舞并缓慢环绕镜头。

## 发布开箱版

维护者从工作中的导演台生成本文件夹：

```sh
zsh scripts/publish-studio.sh 导演台目录 [默认角色.vrm 显示名] [演示舞曲]
```

页面代码和 `tools/` 每次都会复制；媒体只复制 `scripts/studio-media.json` 里 `approved: true` 的文件，曲库只列实际复制了的文件。目标的媒体文件夹会先清空，不要把唯一原件放在这里。

## 已知限制

- 手快速贴到脸上时，仍可能有几帧 1–3 mm 的接触。
- 宽长裙在高抬腿、深蹲时会穿模。
- 摄像头动捕：手放下离开画面后，姿态模型有时仍判断手在胸前，角色的手会停在半空。
- 摄像头动捕的手臂动作不够连贯：面部、手、身体三个识别模型轮流运行，每个约为摄像头帧率的三分之一（30 帧摄像头约每秒 10 次），中间靠插值补，快速动作会显得一顿一顿或有延迟。
- 验收按 [验收检查表](../references/验收检查表.md) 在实时播放中看，静止逐帧不能代替。
