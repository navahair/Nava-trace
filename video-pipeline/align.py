"""Word-level timing for the known script against the HeyGen voice track.

1st choice: faster-whisper word timestamps (if installed and its model is reachable),
snapped onto the script words so captions keep the exact spelling.
Fallback: ffmpeg silencedetect speech regions + syllable-weighted spreading.
"""
import difflib
import re
import subprocess


def tokenize(text):
    return re.findall(r"[\w'’$%+\-./]+[.,!?;:]*", text)


def _bare(w):
    return re.sub(r"[^\w]", "", w.lower())


def _syllables(w):
    w = _bare(w)
    if not w:
        return 1
    if w.isdigit():
        return max(1, len(w))
    n = len(re.findall(r"[aeiouy]+", w))
    if w.endswith("e") and n > 1:
        n -= 1
    return max(1, n)


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def speech_regions(path, noise="-35dB", min_sil=0.18):
    log = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-af",
                          f"silencedetect=noise={noise}:d={min_sil}", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    total = duration(path)
    sil, start = [], None
    for line in log.splitlines():
        m = re.search(r"silence_start: ([\d.]+)", line)
        if m:
            start = float(m.group(1))
        m = re.search(r"silence_end: ([\d.]+)", line)
        if m and start is not None:
            sil.append((start, float(m.group(1))))
            start = None
    if start is not None:
        sil.append((start, total))
    regions, t = [], 0.0
    for s, e in sil:
        if s > t + 0.05:
            regions.append((t, s))
        t = e
    if total > t + 0.05:
        regions.append((t, total))
    return regions or [(0.0, total)]


def _spread(words, regions):
    weights = [_syllables(w) for w in words]
    total_w = sum(weights)
    speech = sum(e - s for s, e in regions)

    def at(x):  # speech-time -> wall-clock time
        for s, e in regions:
            if x <= e - s:
                return s + x
            x -= e - s
        return regions[-1][1]

    out, acc = [], 0.0
    for w, wt in zip(words, weights):
        a = acc / total_w * speech
        acc += wt
        b = acc / total_w * speech
        out.append((at(a + 1e-3), at(b - 1e-3)))
    return out


def _whisper_words(audio):
    from faster_whisper import WhisperModel  # optional dependency
    model = WhisperModel("base.en", device="cpu", compute_type="int8")
    segs, _ = model.transcribe(audio, word_timestamps=True, language="en")
    return [(w.word.strip(), w.start, w.end) for s in segs for w in s.words]


def align(words, audio):
    """words: list of script tokens. Returns list of (start, end) per word."""
    try:
        heard = _whisper_words(audio)
    except Exception:
        heard = None
    if heard:
        a = [_bare(w) for w in words]
        b = [_bare(w) for w, _, _ in heard]
        times = [None] * len(words)
        for blk in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
            for k in range(blk.size):
                times[blk.a + k] = heard[blk.b + k][1:]
        if sum(t is not None for t in times) >= 0.6 * len(words):
            return _fill_gaps(times, duration(audio))
    return _spread(words, speech_regions(audio))


def _fill_gaps(times, total):
    n, i = len(times), 0
    while i < n:
        if times[i] is not None:
            i += 1
            continue
        j = i
        while j < n and times[j] is None:
            j += 1
        lo = times[i - 1][1] if i > 0 else 0.0
        hi = times[j][0] if j < n else total
        step = (hi - lo) / (j - i)
        for k in range(i, j):
            times[k] = (lo + step * (k - i), lo + step * (k - i + 1))
        i = j
    return times
