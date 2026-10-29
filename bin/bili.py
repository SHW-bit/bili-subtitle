# -*- coding: utf-8 -*-
"""bili —— 一条命令拿到 B站视频文字稿

    python bin/bili.py <BV号 / 视频链接 / 合集id>
    python bin/bili.py --series 8930787
    python bin/bili.py --mid 3546721751664904

流程（全自动，无需人工介入）：
    1. 有登录态 -> 直接抓官方/AI 字幕（秒级）
    2. 没登录态 / 无字幕轨 -> 自动下载音频 + 本地 faster-whisper 转写（离线，用本地 small 模型）
输出 out/<BV>.txt 与 out/<BV>.srt（字幕源时另存 .subtitle.txt）

登录态（可选，能让速度快 10 倍以上）：
    python bin/bsub.py login          # 扫码一次，长期有效
    python bin/set_sessdata.py        # 或粘贴 SESSDATA
"""
import os, re, subprocess, sys, time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "out")
BIN = os.path.join(BASE, "bin")
PY = sys.executable


def say(s=""):
    sys.stdout.buffer.write((str(s) + "\n").encode("utf-8", "replace"))
    sys.stdout.flush()


def run(args, env=None):
    e = dict(os.environ)
    e["PYTHONIOENCODING"] = "utf-8"
    if env:
        e.update(env)
    p = subprocess.run(args, env=e, capture_output=True, text=True,
                       encoding="utf-8", errors="ignore")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def have_cred():
    for f in ("sessdata.txt", "bili_cred.json", "cookies.txt"):
        p = os.path.join(BIN, f)
        if os.path.isfile(p) and os.path.getsize(p) > 20:
            return True
    return bool(os.environ.get("BILI_SESSDATA"))


def bvid_of(s):
    m = re.search(r"(BV[0-9A-Za-z]{10})", s)
    return m.group(1) if m else None


def season_bvids(sid):
    """合集 id -> BV 列表（免登录，不需要 UP 主 mid）"""
    import json, urllib.request
    u = ("https://api.bilibili.com/x/polymer/web-space/seasons_archives_list"
         "?season_id=%s&page_num=1&page_size=20" % sid)
    req = urllib.request.Request(u, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Referer": "https://www.bilibili.com/"})
    try:
        j = json.loads(urllib.request.urlopen(req, timeout=25).read().decode("utf-8"))
        return [x["bvid"] for x in ((j.get("data") or {}).get("archives") or [])]
    except Exception as e:
        say("  取合集异常 %r" % (e,))
        return []


def subtitle_ok(bv):
    p = os.path.join(OUT, bv + ".subtitle.txt")
    return os.path.isfile(p) and os.path.getsize(p) > 200


def text_ok(bv):
    p = os.path.join(OUT, bv + ".txt")
    return os.path.isfile(p) and os.path.getsize(p) > 200


def promote_subtitle(bv):
    """把 .subtitle.txt/.srt 复制成标准名 .txt/.srt，方便统一取用"""
    import shutil
    src_t = os.path.join(OUT, bv + ".subtitle.txt")
    src_s = os.path.join(OUT, bv + ".subtitle.srt")
    if not os.path.isfile(src_t):
        return False
    shutil.copyfile(src_t, os.path.join(OUT, bv + ".txt"))
    if os.path.isfile(src_s):
        shutil.copyfile(src_s, os.path.join(OUT, bv + ".srt"))
    return True


def transcribe(bv, size="small"):
    """用本地 faster-whisper 批量推理转写（离线）"""
    t0 = time.time()
    rc, log = run([PY, os.path.join(BIN, "v2t.py"),
                   "https://www.bilibili.com/video/" + bv, size])
    if not text_ok(bv):
        say("  ✗ 转写失败: " + log.strip().splitlines()[-1][:200] if log.strip() else "  ✗ 转写失败")
        return False
    say("  ✓ 转写完成 %ds" % (time.time() - t0))
    return True


def one(bv, size):
    say("=== " + bv)
    if subtitle_ok(bv):
        promote_subtitle(bv)
        say("  ✓ 已有字幕稿（官方/AI）"); return True
    if text_ok(bv):
        say("  ✓ 已有转写稿，跳过"); return True

    if have_cred():
        rc, log = run([PY, os.path.join(BIN, "bsub.py"), bv])
        if subtitle_ok(bv):
            promote_subtitle(bv)
            say("  ✓ 官方/AI 字幕已获取")
            return True
        say("  · 该视频无字幕轨，转本地转写")
    else:
        say("  · 无登录态，直接本地转写（要秒级可先 python bin/bsub.py login）")
    return transcribe(bv, size)


def main():
    a = sys.argv[1:]
    if not a:
        say(__doc__); return 1
    size = "small"
    if "--model" in a:
        i = a.index("--model"); size = a[i + 1]; del a[i:i + 2]

    if a[0] == "--series":
        bvs = season_bvids(a[1])
        say("合集 %s 共 %d 集" % (a[1], len(bvs)))
        if not bvs:
            say("✗ 取合集失败（合集id 是否正确？）"); return 2
    elif a[0] == "--mid":
        say("请用: python bin/bili.py --series <合集id>  或直接给 BV 号"); return 2
    else:
        bvs = [b for b in (bvid_of(x) for x in a) if b]
        if not bvs:
            say("✗ 没识别出 BV 号: " + " ".join(a)); return 2

    ok = 0
    for bv in bvs:
        try:
            ok += 1 if one(bv, size) else 0
        except Exception as e:
            say("  ✗ 异常 %r" % (e,))
    say("")
    say("完成 %d/%d" % (ok, len(bvs)))
    say("输出目录: " + OUT)
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main())
