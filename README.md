# bili-subtitle

一条命令拿到 B站视频文字稿。**1.5 秒一集**，带时间轴，输出 `.txt` + `.srt`。

```bash
python bin/bili.py BV1GHh56VEzM
```

```
=== BV1GHh56VEzM
  学完还是看不懂？从一段C程序看懂整门计组【第 1 期·综述】
  P1 字幕轨 1 条: ai-zh
    lan=ai-zh 732 行 -> BV1GHh56VEzM.subtitle.txt
  ✓ 官方/AI 字幕已获取
```

## 它解决什么问题

B站 2023 年后给几乎所有视频生成了 AI 字幕（`ai-zh`），质量不错、分句细、时间轴准。
但这个字幕**在网页上不显示**，接口也要求登录态：

- `/x/player/wbi/v2?aid=&cid=` 匿名返回 `"subtitles": []` + `"need_login_subtitle": true`
- `playurl` 的 `subtitle` 字段匿名恒为 `null`
- `/x/web-interface/view/conclusion/get`（AI 总结）匿名 → `code=-101 账号未登录`

登录之后就能拿到，而拿到之后整个流程只需要两个 HTTP 请求。
本项目就是把这套流程封装成一条命令。

## 安装

```bash
pip install -r requirements.txt
```

只有本地转写兜底才需要重依赖（`faster-whisper` + `ffmpeg`）。
**只用字幕功能的话，纯标准库即可，不需要装任何东西。**

## 登录（一次，长期有效）

```bash
python bin/bsub.py login      # 终端出二维码，B站 App 扫码
python bin/bsub.py check      # 验证 + 自动续期
```

或者直接给 SESSDATA：

```bash
python bin/set_sessdata.py    # 从剪贴板读
```

凭据存在 `bin/sessdata.txt` / `bin/bili_cred.json` / `bin/cookies.txt`，**已在 .gitignore 里**。

> SESSDATA 等同于账号登录态。别提交，别发人。

## 用法

```bash
python bin/bili.py BV1GHh56VEzM                 # 单集
python bin/bili.py BV1GHh56VEzM BV1thhA6qExm    # 多集
python bin/bili.py --series 8930787             # 整个合集
python bin/bili.py https://www.bilibili.com/video/BV1GHh56VEzM   # 直接贴链接
```

输出到 `out/<BV>.txt`：

```
[00:00:01] 大家好，这期视频我们来讲一下
[00:00:04] 计算机组成原理这门课
```

和 `out/<BV>.srt`（标准 SRT，可直接丢进播放器 / 剪辑软件）。

## 两条路，自动选

```
有字幕轨  → 抓官方 ai-zh 字幕          ~1.5s/集
无字幕轨  → yt-dlp 下音频 + whisper 转写   ~1/5 视频时长
```

判断逻辑在 `bin/bili.py` 的 `one()`：

1. `out/<BV>.subtitle.txt` 已存在且 >200 字节 → 跳过（幂等，可重跑）
2. `out/<BV>.txt` 已存在 → 跳过（断点续跑）
3. 有凭据 → `bsub.py` 抓字幕
4. 抓不到 → `v2t.py` 本地转写兜底

## 实测数据

一个 5 集、总时长 3.9 小时的合集：

| | 行数 | 字符数 | 耗时 |
|---|---|---|---|
| 官方字幕 | 7,509 | 310,110 | **8 秒** |
| 本地 whisper small | 5,568 | 299,000 | 54 分钟 |

**约 400 倍差距。**

## 一个反直觉的发现

B站的 `ai-zh` 字幕**本身就是 ASR 生成的**，所以专业术语错误和本地 faster-whisper 高度相似。
同一段 20:45 的对比：

```
B站字幕:  [00:20:47] 他的这个tooth complement
whisper:  [00:20:45] 就是0101它的这个tooth complement
```

两边都把「two's complement」听成「tooth complement」。词频对比也几乎一致
（`tooth` 8:8、`compliment` 12:12、`补码` 59:56）。

**所以字幕省的是时间，不是准确度。** 要更准只能换更大的模型或人工校对。

## 多语言轨

部分视频有 6 条轨：`ai-zh, ai-en, ai-ja, ai-es, ai-ar, ai-pt`。
`bin/bsub.py:199` 按 `0 if "zh" in lan else 1` 排序，优先取中文。

## 文件

```
bin/bili.py          主入口，调度字幕/转写
bin/bsub.py          字幕抓取（纯标准库）
bin/v2t.py           本地转写（faster-whisper）
bin/set_sessdata.py  粘贴 SESSDATA
```

## 依赖

| 用途 | 依赖 |
|---|---|
| 抓字幕 | **无**（Python 标准库） |
| 本地转写 | `faster-whisper`、`yt-dlp`、`ffmpeg` |
| 自动续期 | `bilibili-api-python`（可选） |

## 免责

只下载**你自己有权访问**的内容，用于个人学习、无障碍阅读、检索。
字幕版权归原作者。请勿二次分发他人视频的文字稿。
频繁请求可能触发风控，脚本里已加 0.5s 间隔。

## License

MIT
