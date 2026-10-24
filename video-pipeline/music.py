"""Fallback background bed, synthesised locally (royalty-free by construction).
Used only when the mood folder in 5_NHẠC NỀN on Drive has no track.
"""
import wave

import numpy as np

SR = 44100
# mood: (bpm, progression as MIDI roots, minor?, drums?)
MOODS = {
    "A": (112, [57, 53, 48, 55], True, True),    # upbeat
    "B": (78, [48, 55, 57, 53], False, False),   # storytelling
    "C": (90, [50, 46, 41, 48], True, False),    # cinematic
    "D": (84, [53, 50, 46, 48], False, True),    # lo-fi teaching
}


def _hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def _tone(freq, n, harmonics=(1, .5, .25, .12)):
    t = np.arange(n) / SR
    return sum(a * np.sin(2 * np.pi * freq * (i + 1) * t) for i, a in enumerate(harmonics))


def _env(n, a=0.02, r=0.3):
    e = np.ones(n)
    na, nr = int(a * SR), int(r * SR)
    e[:na] = np.linspace(0, 1, na)
    e[-nr:] *= np.linspace(1, 0, nr)
    return e


def make(mood, seconds, path, seed=7):
    bpm, prog, minor, drums = MOODS.get(mood, MOODS["D"])
    rng = np.random.default_rng(seed)
    beat = 60 / bpm
    bar = int(4 * beat * SR)
    total = int(seconds * SR) + bar
    out = np.zeros(total)
    third = 3 if minor else 4
    k = 0
    for start in range(0, total, bar):
        root = prog[k % len(prog)]
        k += 1
        n = min(bar, total - start)
        pad = sum(_tone(_hz(root + iv), n, (1, .3, .1)) for iv in (0, third, 7, 12)) * 0.05
        out[start:start + n] += pad * _env(n, 0.4, 0.6)
        out[start:start + n] += _tone(_hz(root - 12), n, (1, .2)) * 0.08 * _env(n, 0.05, 0.4)
        step = int(beat / 2 * SR)  # eighth-note arpeggio
        for j, s in enumerate(range(start, start + n - step, step)):
            note = root + 12 + (0, third, 7, 12, 7, third, 0, 7)[j % 8]
            out[s:s + step] += _tone(_hz(note), step, (1, .15)) * 0.035 * _env(step, 0.005, 0.2)
        if drums:
            for b in range(4):
                s = start + int(b * beat * SR)
                if s >= total:
                    break
                kn = min(int(0.25 * SR), total - s)
                t = np.arange(kn) / SR
                out[s:s + kn] += np.sin(2 * np.pi * (50 + 90 * np.exp(-t * 25)) * t) * np.exp(-t * 14) * 0.35
                h = s + int(beat / 2 * SR)
                hn = min(int(0.05 * SR), total - h)
                if hn > 0:
                    out[h:h + hn] += rng.standard_normal(hn) * np.exp(-np.arange(hn) / SR * 80) * 0.05
    out = out[:int(seconds * SR)]
    out = np.tanh(out * 1.4) / np.max(np.abs(out) + 1e-9)
    pcm = (out * 0.8 * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return path
