# -*- coding: utf-8 -*-
"""bsub —— B站字幕抓取工具（一次配置，长期可用）

  一次配置:
      python bin/bsub.py login          # 扫码，自动保存凭据
      python bin/bsub.py check          # 验证登录态 / 自动续期

  日常使用:
      python bin/bsub.py BV1GHh56VEzM             # 单集（可多个）
      python bin/bsub.py --series 8930787         # 整个合集
      python bin/bsub.py --mid 3546721751664904   # UP 主全部投稿
      python bin/bsub.py <视频链接>                # 直接贴 URL

  输出: out/<BV>.subtitle.txt（[HH:MM:SS] 文本）与 out/<BV>.subtitle.srt

  凭据来源（按优先级，任一即可）:
      bin/sessdata.txt    一行 SESSDATA 明文
      bin/bili_cred.json  login 生成
      bin/cookies.txt     Netscape 格式
      环境变量 BILI_SESSDATA
"""
import json, os, re, sys, time, urllib.parse, urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "out")
BIN = os.path.join(BASE, "bin")
LIB = os.path.join(BIN, "bili_lib")
MID_DEFAULT = 3546721751664904

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def out(s=""):
    sys.stdout.buffer.write((str(s) + "\n").encode("utf-8", "replace"))
    sys.stdout.flush()


# ---------------- 凭据 ----------------
def load_cred_dict():
    """返回 (dict, 来源描述)"""
    p = os.path.join(BIN, "sessdata.txt")
    if os.path.isfile(p):
        v = open(p, encoding="utf-8").read().strip().strip('"').strip("'")
        if v.lower().startswith("sessdata="):
            v = v.split("=", 1)[1]
        v = v.split(";")[0].strip()
        if v:
            return {"sessdata": v}, "sessdata.txt"

    p = os.path.join(BIN, "bili_cred.json")
    if os.path.isfile(p):
        try:
            d = json.load(open(p, encoding="utf-8"))
            if d.get("sessdata"):
                return d, "bili_cred.json"
        except Exception:
            pass

    p = os.path.join(BIN, "cookies.txt")
    if os.path.isfile(p):
        jar = {}
        for line in open(p, encoding="utf-8"):
            if line.startswith("#") or not line.strip():
                continue
            f = line.rstrip("\n").split("\t")
            if len(f) >= 7:
                jar[f[5]] = f[6]
        if jar.get("SESSDATA"):
            return {"sessdata": jar["SESSDATA"], "bili_jct": jar.get("bili_jct"),
                    "dedeuserid": jar.get("DedeUserID"), "buvid3": jar.get("buvid3"),
                    "ac_time_value": jar.get("ac_time_value")}, "cookies.txt"

    v = os.environ.get("BILI_SESSDATA", "").strip()
    if v:
        return {"sessdata": v}, "env"
    return None, None


def cookie_header(cd):
    if not cd:
        return None
    parts = []
    m = {"sessdata": "SESSDATA", "bili_jct": "bili_jct",
         "dedeuserid": "DedeUserID", "buvid3": "buvid3", "buvid4": "buvid4"}
    for k, name in m.items():
        if cd.get(k):
            parts.append(name + "=" + cd[k])
    return "; ".join(parts) if parts else None


def save_cred(cd):
    clean = {k: v for k, v in cd.items() if v}
    with open(os.path.join(BIN, "bili_cred.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(clean, f, ensure_ascii=False, indent=1)
    if clean.get("sessdata"):
        with open(os.path.join(BIN, "sessdata.txt"), "w", encoding="utf-8", newline="\n") as f:
            f.write(clean["sessdata"] + "\n")
    if clean.get("sessdata"):
        lines = ["# Netscape HTTP Cookie File", ""]
        for k, v in clean.items():
            name = {"sessdata": "SESSDATA", "dedeuserid": "DedeUserID"}.get(k, k)
            lines.append("\t".join([".bilibili.com", "TRUE", "/", "FALSE", "2000000000", name, v]))
        with open(os.path.join(BIN, "cookies.txt"), "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")


# ---------------- HTTP ----------------
def api(url, cd=None, raw=False):
    h = dict(UA)
    ck = cookie_header(cd)
    if ck:
        h["Cookie"] = ck
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode("utf-8", "replace")
    return json.loads(body)


def nav(cd):
    return api("https://api.bilibili.com/x/web-interface/nav", cd)


def bvid_of(s):
    if re.fullmatch(r"BV[0-9A-Za-z]{10}", s):
        return s
    m = re.search(r"(BV[0-9A-Za-z]{10})", s)
    return m.group(1) if m else None


# ---------------- 抓取 ----------------
def ts(sec):
    sec = max(0, int(float(sec)))
    return "%02d:%02d:%02d" % (sec // 3600, sec % 3600 // 60, sec % 60)


def srt_ts(sec):
    sec = max(0.0, float(sec))
    h, m = int(sec // 3600), int(sec % 3600 // 60)
    s, ms = int(sec % 60), int(round((sec - int(sec)) * 1000))
    if ms == 1000:
        s, ms = s + 1, 0
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def write_sub(bvid, items, tag=""):
    lines, srt = [], []
    for i, it in enumerate(items, 1):
        t = (it.get("content") or "").strip()
        if not t:
            continue
        a, b = it.get("from", 0), it.get("to", 0)
        lines.append("[%s] %s" % (ts(a), t))
        srt.append("%d\n%s --> %s\n%s\n" % (i, srt_ts(a), srt_ts(b), t))
    if not lines:
        return None
    os.makedirs(OUT, exist_ok=True)
    p1 = os.path.join(OUT, bvid + tag + ".subtitle.txt")
    p2 = os.path.join(OUT, bvid + tag + ".subtitle.srt")
    open(p1, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
    open(p2, "w", encoding="utf-8", newline="\n").write("\n".join(srt) + "\n")
    return p1, p2, len(lines)


def fetch_one(bvid, cd):
    out("=== " + bvid)
    j = api("https://api.bilibili.com/x/web-interface/view?bvid=" + bvid, cd)
    if j.get("code") != 0:
        out("  ❌ 取视频信息失败 code=%s msg=%s" % (j.get("code"), j.get("message")))
        return 0
    d = j["data"]
    aid, title = d["aid"], d["title"]
    pages = d.get("pages") or []
    out("  " + title)
    got = 0
    for p in pages:
        cid = p["cid"]
        u = "https://api.bilibili.com/x/player/wbi/v2?aid=%d&cid=%d" % (aid, cid)
        try:
            r = api(u, cd)
        except Exception as e:
            out("  P%s 请求异常 %r" % (p.get("page"), e)); continue
        if r.get("code") != 0:
            out("  P%s 接口 code=%s msg=%s" % (p.get("page"), r.get("code"), r.get("message")))
            continue
        sub = (r.get("data") or {}).get("subtitle") or {}
        subs = sub.get("subtitles") or []
        need = (r.get("data") or {}).get("need_login_subtitle")
        if not subs:
            out("  P%s 无字幕轨  need_login=%s" % (p.get("page"), need))
            continue
        out("  P%s 字幕轨 %d 条: %s" % (p.get("page"), len(subs),
                                       ", ".join(s.get("lan", "?") for s in subs)))
        subs.sort(key=lambda s: 0 if "zh" in (s.get("lan") or "").lower() else 1)
        s = subs[0]
        su = s.get("subtitle_url") or ""
        if su.startswith("//"):
            su = "https:" + su
        try:
            body = api(su, cd)
        except Exception as e:
            out("    下载失败 %r" % (e,)); continue
        tag = "" if len(pages) == 1 else ".P%s" % p.get("page")
        w = write_sub(bvid, body.get("body") or [], tag)
        if w:
            out("    lan=%s %d 行 -> %s" % (s.get("lan"), w[2], os.path.basename(w[0])))
            got += 1
    return got


def list_series(sid, cd):
    """合集 id -> [(bvid, title)]。免登录，不需要 UP 主 mid。"""
    res, pn = [], 1
    while True:
        u = ("https://api.bilibili.com/x/polymer/web-space/seasons_archives_list"
             "?season_id=%s&page_num=%d&page_size=30" % (sid, pn))
        j = api(u, cd)
        if j.get("code") != 0:
            out("  合集接口 code=%s msg=%s" % (j.get("code"), j.get("message")))
            break
        arc = ((j.get("data") or {}).get("archives") or [])
        if not arc:
            break
        res += [(a["bvid"], a.get("title", "")) for a in arc]
        total = (j.get("data") or {}).get("page") or {}
        if pn >= int(total.get("total") or 1):
            break
        pn += 1
    return res


def list_mid(mid, cd):
    res, pn = [], 1
    while True:
        j = api("https://api.bilibili.com/x/space/wbi/arc/search?mid=%d&pn=%d&ps=50" % (mid, pn), cd)
        if j.get("code") != 0:
            out("  列表接口 code=%s msg=%s（可能需要登录）" % (j.get("code"), j.get("message")))
            break
        vl = ((j.get("data") or {}).get("list") or {}).get("vlist") or []
        if not vl:
            break
        res += [(v["bvid"], v.get("title", "")) for v in vl]
        if len(vl) < 50:
            break
        pn += 1
    return res


# ---------------- 子命令 ----------------
def cmd_check():
    cd, src = load_cred_dict()
    if not cd:
        out("❌ 没有凭据。请先执行:  python bin/bsub.py login")
        out("   或把 SESSDATA 写入 bin/sessdata.txt（一行）")
        return 2
    out("凭据来源: " + src)
    out("SESSDATA 长度: %d" % len(cd.get("sessdata") or ""))
    j = nav(cd)
    if j.get("code") != 0:
        out("❌ 未登录 code=%s msg=%s" % (j.get("code"), j.get("message")))
        out("   SESSDATA 已失效，请重新 login 或重新复制。")
        return 3
    d = j.get("data") or {}
    out("✅ 登录有效: %s (mid=%s)" % (d.get("uname"), d.get("mid")))
    # 尝试自动续期（bilibili-api 提供 ac_time_value 刷新）
    if cd.get("ac_time_value") and os.path.isdir(LIB):
        try:
            sys.path.insert(0, LIB)
            from bilibili_api import Credential
            import asyncio
            c = Credential(sessdata=cd["sessdata"], bili_jct=cd.get("bili_jct"),
                           buvid3=cd.get("buvid3"), dedeuserid=cd.get("dedeuserid"),
                           ac_time_value=cd["ac_time_value"])
            if asyncio.run(c.check_refresh()):
                asyncio.run(c.refresh())
                save_cred(dict(cd, sessdata=c.sessdata, bili_jct=c.bili_jct,
                               ac_time_value=c.ac_time_value))
                out("🔄 cookie 已自动续期并保存")
            else:
                out("（当前无需续期）")
        except Exception as e:
            out("（续期跳过: %r）" % (e,))
    return 0


def cmd_login():
    png = os.path.join(OUT, "qr_login.png")
    os.makedirs(OUT, exist_ok=True)
    j = api("https://passport.bilibili.com/x/passport-login/web/qrcode/generate")
    if j.get("code") != 0:
        out("生成二维码失败: %s" % j); return 1
    qr_url, key = j["data"]["url"], j["data"]["qrcode_key"]
    q = ("https://api.qrserver.com/v1/create-qr-code/?size=460x460&margin=10&data="
         + urllib.parse.quote(qr_url, safe=""))
    try:
        req = urllib.request.Request(q, headers=UA)
        open(png, "wb").write(urllib.request.urlopen(req, timeout=25).read())
        out("二维码图片: " + png)
    except Exception as e:
        out("二维码渲染失败 %r" % (e,))
    out("请用 B站手机 App 扫码，并在手机上点【确认登录】（3 分钟内）...")
    deadline, last = time.time() + 300, None
    while time.time() < deadline:
        try:
            h = dict(UA)
            req = urllib.request.Request(
                "https://passport.bilibili.com/x/passport-login/web/qrcode/poll?qrcode_key=" + key,
                headers=h)
            r = urllib.request.urlopen(req, timeout=20)
            j3 = json.loads(r.read().decode("utf-8"))
            inner = j3.get("data") or {}
            code = inner.get("code")
            if code != last:
                out("  状态 %s %s" % (code, inner.get("message")))
                last = code
            if code == 0:
                jar = {}
                for ck in (r.headers.get_all("Set-Cookie") or []):
                    first = ck.split(";", 1)[0]
                    if "=" in first:
                        k, v = first.split("=", 1)
                        jar[k.strip()] = v.strip()
                for k, v in urllib.parse.parse_qsl(urllib.parse.urlparse(inner.get("url") or "").query):
                    jar.setdefault(k, v)
                cd = {"sessdata": jar.get("SESSDATA"), "bili_jct": jar.get("bili_jct"),
                      "buvid3": jar.get("buvid3"), "buvid4": jar.get("buvid4"),
                      "dedeuserid": jar.get("DedeUserID"),
                      "ac_time_value": jar.get("ac_time_value")}
                if not cd["sessdata"]:
                    out("❌ 未拿到 SESSDATA，收到: " + ", ".join(jar.keys()))
                    return 2
                save_cred(cd)
                out("✅ 凭据已保存（sessdata.txt / bili_cred.json / cookies.txt）")
                return cmd_check()
            if code == 86038:
                out("❌ 二维码已过期，请重新运行"); return 3
            time.sleep(2)
        except Exception as e:
            out("  轮询异常 %r" % (e,)); time.sleep(3)
    out("超时"); return 4


def main():
    args = sys.argv[1:]
    if not args:
        out(__doc__); return 1
    if args[0] in ("login", "--login"):
        return cmd_login()
    if args[0] in ("check", "--check"):
        return cmd_check()

    cd, src = load_cred_dict()
    if cd:
        out("凭据: " + src)
    else:
        out("⚠️ 无凭据（匿名只能拿 UP 主手动上传的 CC 字幕，AI 字幕拿不到）")

    targets = []
    if args[0] == "--series":
        lst = list_series(args[1], cd)
        out("合集 %s 共 %d 集" % (args[1], len(lst)))
        targets = [b for b, _ in lst]
    elif args[0] == "--mid":
        lst = list_mid(int(args[1]) if len(args) > 1 else MID_DEFAULT, cd)
        out("UP 主共 %d 个投稿" % len(lst))
        targets = [b for b, _ in lst]
    else:
        for a in args:
            b = bvid_of(a)
            if b:
                targets.append(b)
            else:
                out("⚠️ 无法识别 BV 号: " + a)

    if not targets:
        out("没有可处理的目标"); return 2

    total = 0
    for b in targets:
        try:
            total += fetch_one(b, cd)
        except Exception as e:
            out("  ❌ 异常 %r" % (e,))
        time.sleep(0.5)

    out("")
    out("完成，共写入 %d 条字幕轨" % total)
    if total == 0 and not cd:
        out("提示: 执行 python bin/bsub.py login 获取登录态后可拿 AI 字幕")
    return 0 if total else 2


if __name__ == "__main__":
    sys.exit(main())
