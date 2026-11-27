#!/bin/zsh
# 双击启动皮套导演台：本机开一个网页服务并打开浏览器（关闭这个窗口即停止）
cd "${0:A:h}"
( sleep 1; open "http://localhost:8190/" ) &
python3 -m http.server 8190 --bind 127.0.0.1
