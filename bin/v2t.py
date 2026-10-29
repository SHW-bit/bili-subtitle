# -*- coding: utf-8 -*-
"""v2t - 视频转文字稿（B站/YouTube 等 yt-dlp 支持的站点）

用法:
    python bin/v2t.py <视频URL> [tiny|base|small]

输出:
    out/<视频ID>.srt  带时间轴字幕
    out/<视频ID>.txt  纯文字稿（每行带 [时间戳]）

依赖（已安装在 bin/ 下，不污染系统 Python）:
    bin/ytdlp_lib/      yt-dlp
    bin/asrlib/         faster-whisper + ctranslate2 + tokenizers
    bin/ffmpeg.exe      ffmpeg
    models/faster-whisper-*/  模型
"""
import sys, os, subprocess

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "bin", "asrlib"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

from faster_whisper import WhisperModel


def srt_time(t):
    h, m, s = int(t // 3600), int(t % 3600 // 60), int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    if ms == 1000:
        s, ms = s + 1, 0
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def fetch_audio(url):
    dl = os.path.join(BASE, "dl")
    os.makedirs(dl, exist_ok=True)
    env = dict(os.environ, PYTHONPATH=os.path.join(BASE, "bin", "ytdlp_lib"))
    cmd = [sys.executable, "-m", "yt_dlp", "-f", "bestaudio/best", "-x",
           "--audio-format", "mp3", "--audio-quality", "5",
           "--ffmpeg-location", os.path.join(BASE, "bin", "ffmpeg.exe"),
           "-o", os.path.join(dl, "%(id)s.%(ext)s"), "--no-playlist", url]
    print("[1/3] 下载音频...", flush=True)
    p = subprocess.run(cmd, env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="ignore")
    if p.returncode != 0:
        print(p.stderr[-1200:])
        sys.exit("yt-dlp 下载失败")
    files = [f for f in os.listdir(dl) if f.endswith(".mp3")]
    files.sort(key=lambda f: os.path.getmtime(os.path.join(dl, f)))
    return os.path.join(dl, files[-1])


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    url = sys.argv[1]
    size = sys.argv[2] if len(sys.argv) > 2 else "small"
    mdir = os.path.join(BASE, "models", f"faster-whisper-{size}")
    if not os.path.isdir(mdir):
        sys.exit(f"模型不存在: {mdir}")

    audio = fetch_audio(url)
    print(f"[2/3] 加载模型 {size} ...", flush=True)
    model = WhisperModel(mdir, device="cpu", compute_type="int8",
                         cpu_threads=os.cpu_count() or 4)
    print("[3/3] 转写中（约 1/5 视频时长）...", flush=True)

    segments, info = model.transcribe(audio, language="zh", vad_filter=False,
                                      beam_size=5, condition_on_previous_text=False)
    stem = os.path.splitext(os.path.basename(audio))[0]
    outdir = os.path.join(BASE, "out")
    os.makedirs(outdir, exist_ok=True)

    srt, txt, n = [], [], 0
    for seg in segments:
        n += 1
        t = seg.text.strip()
        if not t:
            continue
        srt.append(f"{n}\n{srt_time(seg.start)} --> {srt_time(seg.end)}\n{t}\n")
        txt.append(f"[{srt_time(seg.start)[:8]}] {t}")

    with open(os.path.join(outdir, stem + ".srt"), "w", encoding="utf-8") as f:
        f.write("\n".join(srt))
    with open(os.path.join(outdir, stem + ".txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(txt))

    print(f"\n完成: {len(txt)} 段 | 视频 {info.duration:.0f}s")
    print("SRT:", os.path.join(outdir, stem + ".srt"))
    print("TXT:", os.path.join(outdir, stem + ".txt"))


if __name__ == "__main__":
    main()
