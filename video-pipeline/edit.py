"""Final cut: HeyGen avatar (full frame) + factory B-roll cutaways (muted) +
word-by-word captions + ducked background music. Output 1080x1920 30fps H.264.
"""
import os
import re
import subprocess

from align import align, duration, tokenize

W, H, FPS = 1080, 1920, 30
HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "assets", "fonts")

GOLD = "&H0037C8F5&"   # ASS colours are &HAABBGGRR
WHITE = "&H00FFFFFF&"


def _ass_time(t):
    t = max(0.0, t)
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _esc(s):
    return s.replace("\\", "").replace("{", "(").replace("}", ")")


def word_timeline(plan, audio):
    words, seg_of = [], []
    for i, seg in enumerate(plan["segments"]):
        toks = tokenize(seg["text"])
        words += toks
        seg_of += [i] * len(toks)
    times = align(words, audio)
    return words, seg_of, times


def segment_windows(plan, seg_of, times, total):
    n = len(plan["segments"])
    first = {}
    last = {}
    for k, s in enumerate(seg_of):
        first.setdefault(s, times[k][0])
        last[s] = times[k][1]
    win = []
    for i in range(n):
        a = first[i] - 0.08 if i else 0.0
        b = first[i + 1] - 0.08 if i + 1 < n else total
        win.append((max(0.0, a), min(total, b)))
    return win


def captions_ass(plan, words, seg_of, times, path, max_words=3):
    emph = {re.sub(r"[^\w]", "", e.lower()) for s in plan["segments"] for e in s.get("emphasis", [])}
    chunks, cur = [], []
    for k, w in enumerate(words):
        if cur and (len(cur) == max_words or seg_of[k] != seg_of[cur[-1]]):
            chunks.append(cur)
            cur = []
        cur.append(k)
        if re.search(r"[.,!?;:]$", w):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)

    lines = []
    for c_i, ch in enumerate(chunks):
        c_end = times[ch[-1]][1]
        if c_i + 1 < len(chunks):
            nxt = times[chunks[c_i + 1][0]][0]
            c_end = nxt if nxt - c_end < 0.35 else c_end + 0.15
        for j, k in enumerate(ch):
            a = times[k][0] if j else times[ch[0]][0]
            b = times[ch[j + 1]][0] if j + 1 < len(ch) else c_end
            parts = []
            for kk in ch:
                txt = _esc(re.sub(r"[.,;:]$", "", words[kk]).upper())
                is_emph = re.sub(r"[^\w]", "", words[kk].lower()) in emph
                if kk == k:
                    parts.append(f"{{\\c{GOLD}\\fscx112\\fscy112}}{txt}{{\\c{WHITE}\\fscx100\\fscy100}}")
                elif is_emph:
                    parts.append(f"{{\\c{GOLD}}}{txt}{{\\c{WHITE}}}")
                else:
                    parts.append(txt)
            pop = "{\\fscx88\\fscy88\\t(0,90,\\fscx100\\fscy100)}" if j == 0 else ""
            lines.append(f"Dialogue: 0,{_ass_time(a)},{_ass_time(b)},Cap,,0,0,0,,{pop}{' '.join(parts)}")

    hook = plan.get("on_screen_hook")
    if hook:
        hook_end = min(3.2, times[-1][1])
        lines.append(f"Dialogue: 1,{_ass_time(0)},{_ass_time(hook_end)},Hook,,0,0,0,,"
                     f"{{\\fad(120,200)}}{_esc(hook)}")

    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Anton,124,{WHITE},{WHITE},&H00000000,&H64000000,0,0,0,0,100,100,1,0,1,9,4,2,60,60,600,1
Style: Hook,Anton,96,&H00111111,&H00111111,&H0037C8F5,&H0037C8F5,0,0,0,0,100,100,1,0,3,22,0,8,80,80,240,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(head + "\n".join(lines) + "\n")


def prepare(plan, avatar, workdir):
    """Extract the voice, time every script word, derive per-segment windows."""
    os.makedirs(workdir, exist_ok=True)
    audio = os.path.join(workdir, "voice.wav")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", avatar, "-vn", "-ac", "1", "-ar", "48000", audio], check=True)
    total = duration(avatar)
    words, seg_of, times = word_timeline(plan, audio)
    wins = segment_windows(plan, seg_of, times, total)
    return {"words": words, "seg_of": seg_of, "times": times, "windows": wins, "total": total}


def render(plan, avatar, pieces, music, out, workdir, prep):
    """pieces: list of dicts {path, src_start, at, dur} — B-roll placed at timeline time `at`."""
    words, seg_of, times, wins, total = (prep[k] for k in ("words", "seg_of", "times", "windows", "total"))
    ass = os.path.join(workdir, "captions.ass")
    captions_ass(plan, words, seg_of, times, ass)

    # avatar punch-in on alternate avatar-only segments (jump-cut feel)
    zoom_terms = [f"between(t,{a:.3f},{b:.3f})" for i, (a, b) in enumerate(wins)
                  if not plan["segments"][i].get("broll") and i % 2 == 1]
    zexpr = "+".join(zoom_terms) if zoom_terms else "0"
    zw = f"'if(gt({zexpr},0),{int(W * 1.12) // 2 * 2},{W})'"
    zh = f"'if(gt({zexpr},0),{int(H * 1.12) // 2 * 2},{H})'"

    cmd = ["ffmpeg", "-y", "-v", "error", "-i", avatar]
    for p in pieces:
        cmd += ["-ss", f"{p['src_start']:.3f}", "-t", f"{p['dur'] + 0.1:.3f}", "-i", p["path"]]
    music_idx = None
    if music:
        music_idx = len(pieces) + 1
        cmd += ["-stream_loop", "-1", "-i", music]

    fg = [f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},"
          f"scale=w={zw}:h={zh}:eval=frame,crop={W}:{H}:(iw-{W})/2:(ih-{H})/2,setsar=1[base]"]
    last = "base"
    for i, p in enumerate(pieces, start=1):
        frames = int(p["dur"] * FPS) + 3
        fg.append(f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},"
                  f"zoompan=z='1+0.06*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={FPS},"
                  f"eq=contrast=1.05:saturation=1.08,setsar=1,setpts=PTS-STARTPTS+{p['at']:.3f}/TB[b{i}]")
        fg.append(f"[{last}][b{i}]overlay=0:0:eof_action=pass:"
                  f"enable='between(t,{p['at']:.3f},{p['at'] + p['dur']:.3f})'[v{i}]")
        last = f"v{i}"
    fg.append(f"[{last}]subtitles='{ass}':fontsdir='{FONTS}',format=yuv420p[vout]")

    fg.append("[0:a]aresample=48000,loudnorm=I=-15:TP=-1.5:LRA=9,asplit=2[voice][key]")
    if music_idx:
        fade_out = max(0.0, total - 1.5)
        fg.append(f"[{music_idx}:a]aresample=48000,atrim=0:{total:.3f},volume=0.22,"
                  f"afade=t=in:d=0.6,afade=t=out:st={fade_out:.3f}:d=1.5[mus]")
        fg.append("[mus][key]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=350[duck]")
        fg.append("[voice][duck]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5[aout]")
    else:
        fg.append("[key]anullsink;[voice]loudnorm=I=-14:TP=-1.5[aout]")

    cmd += ["-filter_complex", ";".join(fg), "-map", "[vout]", "-map", "[aout]",
            "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out]
    subprocess.run(cmd, check=True)
