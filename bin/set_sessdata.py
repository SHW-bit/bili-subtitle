# -*- coding: utf-8 -*-
"""一步到位：设置 SESSDATA 并验证，然后可直接抓字幕。

用法:
  python bin/set_sessdata.py                 # 从剪贴板读取（推荐）
  python bin/set_sessdata.py "SESSDATA=xxx"  # 直接传
  python bin/set_sessdata.py --check         # 只检查现有 sessdata.txt 是否有效
  python bin/set_sessdata.py --series <合集id>   # 用现有登录态抓整个合集

写好后：python bin/bili.py --series <合集id>
"""
import json, os, sys, urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(BASE, "bin", "sessdata.txt")
UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com/",
}

def out(s=""):
    sys.stdout.buffer.write((str(s) + "\n").encode("utf-8", "replace"))
    sys.stdout.flush()

def clean(raw):
    v = (raw or "").strip().strip('"').strip("'")
    for pre in ("SESSDATA=", "sessdata="):
        if v.startswith(pre):
            v = v[len(pre):]
    return v.split(";")[0].strip()

def nav(sess):
    req = urllib.request.Request(
        "https://api.bilibili.com/x/web-interface/nav",
        headers=dict(UA, Cookie="SESSDATA=" + sess))
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))

def main():
    args = sys.argv[1:]

    if "--series" in args:
        i = args.index("--series")
        if i + 1 >= len(args):
            out("用法: python bin/set_sessdata.py --series <合集id>"); return 2
        os.execv(sys.executable, [sys.executable, os.path.join(BASE, "bin", "bili.py"),
                                  "--series", args[i + 1]])

    if "--check" in args:
        if not os.path.isfile(P):
            out("没有 bin/sessdata.txt"); return 2
        sess = clean(open(P, encoding="utf-8").read())
    elif args:
        sess = clean(args[0])
    else:
        try:
            import subprocess
            ps = ("Add-Type -AssemblyName System.Windows.Forms;"
                  "[System.Windows.Forms.Clipboard]::GetText()")
            r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                               capture_output=True, text=True, timeout=15)
            sess = clean(r.stdout)
        except Exception as e:
            out("读剪贴板失败: %r" % (e,)); return 3
        if not sess:
            out("剪贴板是空的。先在浏览器 Console 里 copy(...) 再运行本命令。"); return 3

    if not sess:
        out("SESSDATA 为空"); return 3

    out("SESSDATA 长度 = %d" % len(sess))
    try:
        j = nav(sess)
    except Exception as e:
        out("验证请求失败: %r" % (e,)); return 4

    if j.get("code") != 0:
        out("❌ 未登录 code=%s msg=%s" % (j.get("code"), j.get("message")))
        out("   SESSDATA 无效或已过期，请重新从浏览器复制。")
        return 5

    d = j.get("data") or {}
    out("✅ 登录有效: %s (mid=%s, vip=%s)" % (d.get("uname"), d.get("mid"), (d.get("vipStatus") == 1)))

    with open(P, "w", encoding="utf-8", newline="\n") as f:
        f.write(sess + "\n")
    out("已写入 " + P)
    out("")
    out("下一步: python bin/bili.py --series <合集id>")
    return 0

sys.exit(main())
