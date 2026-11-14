"""EmoEarth orchestra: turns the colours of the temperature map into a synthesized orchestra.

Each colour of the Worldview colour bar drives one section of the orchestra. The more of that colour
there is on the globe on a given day (compared with how much there usually is), the louder that
section plays, so you can hear the planet's colour change as the instrumentation changes.

  Violins          melody   = northern hemisphere temperature (always playing)
  Violas           harmony  = sustained chord bed (always playing)
  Cellos & Basses  bass     = southern hemisphere temperature          (blue)
  Celesta, Harp, Clarinet, Flute, French Horns, Trumpets & Timpani     (purple ... red)

The warming / cooling trend chooses C major or C minor. A key change is announced by a pivot on the
dominant chord (G, shared by both keys), a timpani roll and a horn swell, then the new key's tonic.
Every day also gets an emotion (Serene, Joyful, Triumphant, Melancholy, Tense, Urgent) which shapes
the articulation: legato, tremolo, arpeggio speed, fanfares and drums.

The ocean layer (style "ocean") uses its own instruments for the same seven roles, soft and slow:
  Solo cello melody, string pad, Glass Harmonica, Double Basses (with bass clarinet), Vibraphone, Oboe,
  Pan Flute, Choir ("ooh") and Steel Pan & Drum (an ocean drum), over a swell of distant waves.

Everything is synthesized with numpy (wavetables, additive partials, plucked and bell models and a
convolution hall reverb): no samples, no MIDI.
"""
import numpy as np

SR = 44100

MAJOR = [0, 2, 4, 5, 7, 9, 11]
MINOR = [0, 2, 3, 5, 7, 8, 10]
HARMONIC_MINOR = [0, 2, 3, 5, 7, 8, 11]       # raised 7th, used for the dominant (V) chord in minor

# colour band (coldest -> hottest)  ->  (section name, base level)
# The base level is how loud a section plays even when its colour is rare, so the orchestra never goes silent.
SECTIONS = [
    ("Celesta", 0.15),                # purple : the coldest ice, glassy bells
    ("Cellos & Basses", 0.60),        # blue   : deep cold, the foundation
    ("Harp", 0.25),                   # cyan   : cool, flowing arpeggios
    ("Clarinet", 0.20),               # green  : mild, the inner voice
    ("Flute", 0.15),                  # yellow : warm, doubles the melody high up
    ("French Horns", 0.20),           # orange : warmer, broad sustained chords
    ("Trumpets & Timpani", 0.08),     # red    : hottest, fanfares and drums
]
INSTRUMENTS = [s[0] for s in SECTIONS]

# ocean layer: the same seven roles (cold blue ... warm red on NASA's sea temperature colour bar), other instruments
OCEAN_SECTIONS = [
    ("Glass Harmonica", 0.15),        # coldest blue  : glassy, eerie bells (deep polar water)
    ("Double Basses", 0.60),          # cold blue     : the deep foundation (bowed basses + bass clarinet)
    ("Vibraphone", 0.25),             # teal          : shimmering arpeggios, like light on water
    ("Oboe", 0.20),                   # green         : the singing inner voice
    ("Pan Flute", 0.15),              # yellow-green  : breathy, doubles the melody high up
    ("Choir", 0.20),                  # yellow-orange : soft "ooh" chords, the sea's voices
    ("Steel Pan & Drum", 0.08),       # red           : warm tropical seas (steel pan; ocean drum on key changes)
]
OCEAN_INSTRUMENTS = [s[0] for s in OCEAN_SECTIONS]
BASE_LEVEL = np.array([s[1] for s in SECTIONS])

EMOTIONS = ["Serene", "Joyful", "Triumphant", "Melancholy", "Tense", "Urgent"]
PROGRESSION = [0, 5, 3, 4]           # I - vi - IV - V   (i - VI - iv - V in minor), one chord per bar
BEATS_PER_BAR = 4                    # one beat = one day


# ---------------------------------------------------------------- emotion
def emotions(is_major, warmth, arousal, calm=0.45, high=0.75):
    """valence: major/minor plus how warm it is. arousal: speed of change plus heat (red)."""
    out = []
    for m, w, a in zip(is_major, warmth, arousal):
        valence = (0.6 if m else -0.6) + (w - 0.5) * 0.8
        if valence >= 0:
            out.append("Triumphant" if a > high else "Joyful" if a > calm else "Serene")
        else:
            out.append("Urgent" if a > high else "Tense" if a > calm else "Melancholy")
    return out


# ---------------------------------------------------------------- synthesis
def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def _table(amps, size=4096):
    x = np.arange(size) * (2 * np.pi / size)
    w = np.zeros(size)
    for h, a in enumerate(amps, 1):
        w += a * np.sin(h * x)
    return w / (np.abs(w).max() + 1e-9)


T = {
    "violin":   _table([1.0 / h for h in range(1, 14)]),
    "viola":    _table([1.0 / h ** 1.5 for h in range(1, 9)]),
    "cello":    _table([1.0 / h ** 1.1 for h in range(1, 12)]),
    "flute":    _table([1, .38, .14, .06, .025]),
    "clarinet": _table([1, .04, .5, .03, .3, .02, .18, .02, .1, .01, .06]),
    "horn":     _table([1.0 / h ** 2.2 for h in range(1, 9)]),
    "trumpet":  _table([1, .95, .85, .7, .55, .42, .3, .2, .13, .08, .05, .03]),
    "oboe":     _table([.55, 1, .85, .7, .5, .38, .28, .2, .13, .08, .05]),
    "choir":    _table([0.4738, 0.0989, 0.0277, 0.4519, 0.0154, 0.0033, 0.0029, 0.0029, 0.0244, 0.1173, 0.0552, 0.0039, 0.0015, 0.0014, 0.0013, 0.0013]),     # an "ooh" vowel (formants near 300, 870 and 2240 Hz)
    "bassclar": _table([1, .02, .45, .02, .22, .01, .1, .01, .05]),
}
_rng = np.random.default_rng(7)


def _osc(table, freq, n, vib_rate=0.0, vib_cents=0.0, detune=0.0, phase=0.0):
    t = np.arange(n) / SR
    if vib_cents:
        ramp = np.clip((t - 0.12) / 0.3, 0, 1)            # vibrato fades in after the attack, like a player
        cents = detune + vib_cents * ramp * np.sin(2 * np.pi * vib_rate * t + phase * 3)
        cyc = np.cumsum(freq * 2 ** (cents / 1200)) / SR + phase
    else:
        cyc = freq * 2 ** (detune / 1200) * t + phase
    idx = (cyc % 1.0) * len(table)
    i0 = idx.astype(np.int64)
    fr = idx - i0
    return table[i0 % len(table)] * (1 - fr) + table[(i0 + 1) % len(table)] * fr


def _env(n, dur, attack, release):
    t = np.arange(n) / SR
    return np.minimum(t / max(attack, 1e-3), 1.0) * np.where(t < dur, 1.0, np.clip(1 - (t - dur) / release, 0, 1))


def ensemble(table, freq, dur, voices=1, spread=0.0, attack=0.05, release=0.3,
             vib_rate=5.0, vib_cents=0.0, tremolo=0.0, swell=False):
    """A section of `voices` slightly detuned players with vibrato (sounds like a group, not one oscillator)."""
    n = int(SR * (dur + release))
    w = np.zeros(n)
    for v in range(voices):
        d = spread * (v - (voices - 1) / 2)
        w += _osc(table, freq, n, vib_rate * (1 + 0.06 * v), vib_cents, d, phase=0.37 * v)
    w /= voices
    env = _env(n, dur, attack, release)
    if swell:                                             # crescendo through the note (key changes)
        env *= np.clip(0.3 + 0.7 * np.arange(n) / (SR * max(dur, 0.1)), 0, 1)
    if tremolo:
        env *= 0.55 + 0.45 * np.abs(np.sin(np.pi * tremolo * np.arange(n) / SR))
    return w * env


def flute(freq, dur):
    w = ensemble(T["flute"], freq, dur, 1, 0, 0.06, 0.2, 5.0, 12)
    breath = np.convolve(_rng.standard_normal(len(w)), np.ones(6) / 6, mode="same")
    return w + 0.05 * breath * _env(len(w), dur, 0.03, 0.2)


def harp(freq, ring=1.6):
    n = int(SR * ring)
    t = np.arange(n) / SR
    w = np.zeros(n)
    for h in range(1, 9):
        if freq * h > SR * 0.45:
            break
        w += (1 / h ** 1.6) * np.sin(2 * np.pi * freq * h * t) * np.exp(-(1.0 + 0.9 * h) * t)
    return w * np.minimum(t / 0.004, 1)


def celesta(freq, ring=2.2):
    n = int(SR * ring)
    t = np.arange(n) / SR
    w = np.zeros(n)
    for ratio, a, d in [(1, 1.0, 1.8), (2, 0.35, 3.5), (3.0, 0.12, 6.0), (4.16, 0.07, 9.0)]:
        if freq * ratio < SR * 0.45:
            w += a * np.sin(2 * np.pi * freq * ratio * t) * np.exp(-d * t)
    return w * np.minimum(t / 0.002, 1)


def timpani(freq, ring=2.4):
    n = int(SR * ring)
    t = np.arange(n) / SR
    w = np.zeros(n)
    for ratio, a, d in [(1, 1.0, 2.2), (1.5, 0.55, 3.0), (1.98, 0.35, 4.0), (2.44, 0.2, 5.5)]:
        w += a * np.sin(2 * np.pi * freq * ratio * t) * np.exp(-d * t)
    hit = np.convolve(_rng.standard_normal(n) * np.exp(-t * 40), np.ones(12) / 12, mode="same")
    return (w + 0.8 * hit) * np.minimum(t / 0.003, 1) * 0.7


def glass_harmonica(freq, ring=3.4):
    """Rubbed glass: pure tone with a slow attack and a gentle beating between two close pitches."""
    n = int(SR * ring)
    t = np.arange(n) / SR
    w = (np.sin(2 * np.pi * freq * t) + np.sin(2 * np.pi * (freq + 1.3) * t) + 0.18 * np.sin(4 * np.pi * freq * t)) / 2.2
    return w * np.minimum(t / 0.18, 1) * np.exp(-1.1 * t)


def vibraphone(freq, ring=2.8):
    """Metal bars with the motor's slow tremolo."""
    n = int(SR * ring)
    t = np.arange(n) / SR
    w = np.zeros(n)
    for ratio, a, d in [(1, 1.0, 1.0), (4.0, 0.25, 3.0), (10.0, 0.05, 8.0)]:
        if freq * ratio < SR * 0.45:
            w += a * np.sin(2 * np.pi * freq * ratio * t) * np.exp(-d * t)
    return w * np.minimum(t / 0.003, 1) * (0.72 + 0.28 * np.sin(2 * np.pi * 5.2 * t))


def pan_flute(freq, dur):
    w = ensemble(T["flute"], freq, dur, 1, 0, 0.09, 0.35, 4.0, 8)
    breath = np.convolve(_rng.standard_normal(len(w)), np.ones(5) / 5, mode="same")
    return w + 0.13 * breath * _env(len(w), dur, 0.05, 0.3)


def steel_pan(freq, ring=1.5):
    n = int(SR * ring)
    t = np.arange(n) / SR
    w = np.zeros(n)
    for ratio, a, d in [(1, 1.0, 2.4), (2.0, 0.55, 3.2), (3.0, 0.22, 4.5), (4.02, 0.1, 6.5)]:
        if freq * ratio < SR * 0.45:
            w += a * np.sin(2 * np.pi * freq * ratio * t) * np.exp(-d * t)
    return w * np.minimum(t / 0.002, 1)


def ocean_drum(dur):
    """Beads rolling inside a frame drum: a soft wash of filtered noise that rises and falls."""
    n = int(SR * dur)
    t = np.arange(n) / SR
    noise = np.convolve(_rng.standard_normal(n), np.ones(18) / 18, mode="same")
    return noise * np.sin(np.pi * t / dur) ** 2 * 0.8


# ---------------------------------------------------------------- mixing
class Mixer:
    def __init__(self, seconds):
        self.L = np.zeros(int(seconds * SR))
        self.R = np.zeros_like(self.L)

    def add(self, w, start, gain, pan):
        """pan: 0 = left, 0.5 = centre, 1 = right (seating of a classical orchestra)."""
        if gain < 1e-4:
            return
        s = int(start * SR)
        e = min(s + len(w), len(self.L))
        if e <= s:
            return
        w = w[: e - s] * gain
        self.L[s:e] += w * np.cos(pan * np.pi / 2)
        self.R[s:e] += w * np.sin(pan * np.pi / 2)


def _fftconv(x, h, block=1 << 16):
    m = len(h)
    nfft = 1 << int(np.ceil(np.log2(block + m - 1)))
    H = np.fft.rfft(h, nfft)
    y = np.zeros(len(x) + m - 1)
    for s in range(0, len(x), block):
        seg = x[s:s + block]
        if not seg.any():
            continue
        out = np.fft.irfft(np.fft.rfft(seg, nfft) * H, nfft)[:len(seg) + m - 1]
        y[s:s + len(out)] += out
    return y[:len(x)]


def hall(L, R, seconds=2.4, wet=0.35):
    """Concert-hall reverb: convolution with a decaying noise impulse response (different per ear = wide)."""
    rng = np.random.default_rng(11)
    n = int(SR * seconds)
    t = np.arange(n) / SR
    src = (L + R) * 0.5
    out = []
    for dry in (L, R):
        ir = np.convolve(rng.standard_normal(n) * np.exp(-6.9 * t / seconds), np.ones(4) / 4, mode="same")
        ir = np.concatenate([np.zeros(int(0.02 * SR)), ir])
        ir /= np.sqrt((ir ** 2).sum())
        out.append(dry + wet * _fftconv(src, ir))
    return out


# ---------------------------------------------------------------- the score
def compose(onset, beat, total, vol, nn, ns, r, is_major, level, emotion, log=print, style="orchestra"):
    """Return a float32 stereo array. Inputs are per day (= per beat):
    onset/beat seconds, vol 0..1 (crescendo/decrescendo), nn/ns 0..1 north/south warmth,
    r 0..1 speed of change, is_major bool, level n x 7 section loudness, emotion labels.
    style "orchestra" (the ice layer) or "gentle": soft and flowing for the ocean layer: always legato, no
    tremolo, runs, fanfares or drum hits, slow harp, a longer hall, quieter overall and a soft sea swell."""
    ocean = style == "ocean"                               # ocean instruments, played gently
    gentle = style in ("gentle", "ocean")
    n = len(onset)
    mix = Mixer(total + 5)

    # harmony: one chord per bar; a key change pivots on V (shared by C major and C minor), then the new tonic
    chord = np.zeros(n, int)
    change = np.zeros(n, bool)
    forced_until = -1
    for i in range(n):
        bar = i // BEATS_PER_BAR
        deg = PROGRESSION[bar % len(PROGRESSION)]
        if i > 0 and is_major[i] != is_major[i - 1]:
            change[i] = True
            deg = 4
            forced_until = max((bar + 1) * BEATS_PER_BAR, i + 2)
        elif i < forced_until:
            deg = 0
        chord[i] = deg

    def scale(i):
        if is_major[i]:
            return MAJOR
        return HARMONIC_MINOR if chord[i] == 4 else MINOR

    def midi(base, d, sc):
        return base + 12 * (d // 7) + sc[d % 7]

    def in_chord(d, i):
        return (d - chord[i]) % 7 in (0, 2, 4)

    def snap(d, i):
        return min((x for x in range(d - 3, d + 4) if in_chord(x, i)), key=lambda x: (abs(x - d), x))

    def two_beats(i):
        return beat[i] + (beat[i + 1] if i + 1 < n else beat[i])

    # ---- sustained sections: violas (always) and French horns, held for as long as the chord lasts
    starts = [0] + [i for i in range(1, n) if chord[i] != chord[i - 1] or is_major[i] != is_major[i - 1]]
    for k, s in enumerate(starts):
        e = starts[k + 1] if k + 1 < len(starts) else n
        st = onset[s]
        dur = (onset[e] if e < n else total) - st
        sc, c, v = scale(s), chord[s], float(vol[s:e].mean())
        lv = level[s:e].mean(axis=0)
        trem = 7.0 if emotion[s] in ("Tense", "Urgent") else 0.0
        for j, d in enumerate((c, c + 2, c + 4)):
            mix.add(ensemble(T["viola"], hz(midi(48, d, sc)), dur, 2 if ocean else 3, 12, 0.45, 0.8, 5.0, 8, trem),
                    st, 0.12 * v, 0.42 + 0.06 * j)
        g = 0.24 * v * lv[5] * (1.6 if change[s] else 1.0)
        if ocean:                                          # choir "ooh" instead of French horns
            for d in (c, c + 2, c + 4):
                mix.add(ensemble(T["choir"], hz(midi(60, d, sc)), dur, 2, 11, 0.9, 1.2, 4.6, 12,
                                 swell=bool(change[s])), st, g * 0.7, 0.36 + 0.07 * (d - c) / 2)
        else:
            for d in (c, c + 4):
                mix.add(ensemble(T["horn"], hz(midi(48, d, sc)), dur, 2, 6, 0.6 if change[s] else 0.25, 0.6,
                                 swell=bool(change[s])), st, g, 0.3)

    # ---- beat by beat
    prev = None
    for i in range(n):
        sc, pos, st, b, v, lv, emo = scale(i), i % BEATS_PER_BAR, onset[i], beat[i], vol[i], level[i], emotion[i]
        legato = gentle or emo in ("Serene", "Melancholy")
        tense = not gentle and emo in ("Tense", "Urgent")
        bright = not gentle and emo in ("Joyful", "Triumphant")

        # violins: melody from the northern hemisphere (warmer = higher), chord tones on strong beats
        idx = int(round(nn[i] * 14))
        if pos % 2 == 0:
            idx = snap(idx, i)
        m = midi(60, idx, sc)
        trem = 9.0 if tense else 0.0
        if prev is not None and r[i] > 0.65 and idx != prev and not legato:
            mid = (prev + idx) // 2                                   # quick run on days of sharp change
            mix.add(ensemble(T["violin"], hz(midi(60, mid, sc)), b * 0.45, 3, 9, 0.02, 0.15, 5.5, 12, trem),
                    st, 0.42 * v, 0.3)
            mix.add(ensemble(T["violin"], hz(m), b * 0.5, 3, 9, 0.02, 0.18, 5.5, 12, trem), st + b * 0.5, 0.45 * v, 0.3)
        else:
            length = b * (1.08 if legato else 0.8 if tense else 0.95)
            if ocean:                                      # a warm solo cello sings the melody, an octave lower
                mix.add(ensemble(T["cello"], hz(m - 12), b * 1.12, 2, 5, 0.14, 0.45, 5.0, 12), st, 0.5 * v, 0.34)
            else:
                mix.add(ensemble(T["violin"], hz(m), length, 3, 9, 0.1 if legato else 0.04, 0.32 if legato else 0.18,
                                 5.5, 14, trem), st, 0.45 * v, 0.3)
        # flute (yellow) doubles the melody an octave up
        if ocean:
            mix.add(pan_flute(hz(m + 12), b * 1.05), st, 0.28 * v * lv[4], 0.5)
        else:
            mix.add(flute(hz(m + 12), b * (1.0 if legato else 0.85)), st, 0.3 * v * lv[4], 0.5)
        prev = idx

        if pos % 2 == 0:
            # clarinet (green): countermelody, a chord tone at least a third below the melody
            cd = max(x for x in range(idx - 6, idx - 1) if in_chord(x, i))
            mix.add(ensemble(T["oboe" if ocean else "clarinet"], hz(midi(60, cd, sc)), two_beats(i) * 0.95, 1, 0,
                             0.09 if ocean else 0.06, 0.3 if ocean else 0.25, 4.5, 10 if ocean else 6),
                    st, (0.26 if ocean else 0.34) * v * lv[3], 0.55)
            # cellos & basses (blue): bass from the southern hemisphere, the chord root on the downbeat
            bidx = int(round(ns[i] * 7))
            bd = chord[i] + 7 * int(round((bidx - chord[i]) / 7)) if pos == 0 else snap(bidx, i)
            f = hz(midi(36, bd, sc))
            mix.add(ensemble(T["cello"], f, two_beats(i) * 0.95, 2, 7, 0.06, 0.35, 5.0, 8), st, 0.3 * v * lv[1], 0.7)
            if ocean:                                      # bass clarinet an octave up instead of cellos
                mix.add(ensemble(T["bassclar"], f * 2, two_beats(i) * 0.95, 1, 0, 0.1, 0.4, 4.0, 5), st, 0.2 * v * lv[1], 0.64)
            else:
                mix.add(ensemble(T["cello"], f * 2, two_beats(i) * 0.95, 2, 7, 0.06, 0.35, 5.0, 10), st, 0.24 * v * lv[1], 0.64)
            # celesta (purple): an icy bell an octave above the melody
            if ocean:
                mix.add(glass_harmonica(hz(m + 12)), st, 0.13 * v * lv[0], 0.75)
            else:
                mix.add(celesta(hz(m + 12)), st, (0.12 if gentle else 0.2) * v * lv[0], 0.75)

        # harp (cyan): arpeggio of the chord, rising in major and falling in minor, faster when aroused
        count = 2 if gentle else 4 if (bright or tense) else 3 if emo == "Serene" else 2
        tones = [chord[i] + o for o in (0, 2, 4, 7, 9, 11)]
        if not is_major[i]:
            tones = tones[::-1]
        for k in range(count):
            if ocean:
                mix.add(vibraphone(hz(midi(60, tones[k], sc))), st + k * b / count, 0.16 * v * lv[2], 0.18)
            else:
                mix.add(harp(hz(midi(48, tones[k], sc)), 2.6 if gentle else 1.6), st + k * b / count,
                        (0.22 if gentle else 0.28) * v * lv[2], 0.18)

        # trumpets & timpani (red): fanfares and drums on the downbeat, a roll on every key change
        red = lv[6]
        if ocean:                                    # warm seas: a soft steel pan; key changes: an ocean drum wash
            if pos == 0 and red > 0.3:
                for k, d in enumerate((chord[i] + 7, chord[i] + 9, chord[i] + 11)):
                    mix.add(steel_pan(hz(midi(60, d, sc))), st + k * b / 3, 0.14 * v * max(red, 0.4), 0.62)
            if change[i]:
                mix.add(ocean_drum(b * 3.0), max(0.0, st - b * 1.5), 0.3 * v + 0.05, 0.5)
            if i % 40 == 0:
                log(f"  orchestra: day {i + 1}/{n}")
            continue
        if gentle:                                   # soft style: only a quiet low drum swell on key changes
            if change[i]:
                hits = max(4, int(b / 0.09))
                for k in range(hits):
                    mix.add(timpani(hz(midi(36, 4, sc)), 3.0), st + k * b / hits, 0.03 + 0.1 * v * k / hits, 0.5)
            if i % 40 == 0:
                log(f"  orchestra: day {i + 1}/{n}")
            continue
        root = midi(36, chord[i], sc)
        if change[i]:
            hits = max(4, int(b / 0.055))
            for k in range(hits):
                mix.add(timpani(hz(midi(36, 4, sc))), st + k * b / hits, 0.08 + 0.4 * v * k / hits, 0.5)
        elif i > 0 and change[i - 1]:
            mix.add(timpani(hz(midi(36, 0, sc))), st, 0.6 * v, 0.5)
        elif pos == 0 and (red > 0.3 or emo in ("Triumphant", "Urgent", "Tense")):
            mix.add(timpani(hz(root)), st, 0.45 * v * max(red, 0.5), 0.5)
        if pos == 2 and emo in ("Urgent", "Tense"):
            mix.add(timpani(hz(root)), st, 0.3 * v * max(red, 0.5), 0.5)
        if pos == 0 and (red > 0.35 or emo in ("Triumphant", "Urgent")):
            g = 0.28 * v * max(red, 0.45)
            if emo == "Urgent":
                notes = [(0, 0.0, 0.28), (0, 1 / 3, 0.28), (0, 2 / 3, 0.28)]
            else:
                notes = [(0, 0.0, 0.25), (4, 1 / 3, 0.25), (7, 2 / 3, 0.9)]
            for d, at, ln in notes:
                mix.add(ensemble(T["trumpet"], hz(midi(60, chord[i] + d, sc)), b * ln, 2, 4, 0.025, 0.15, 5.5, 6),
                        st + b * at, g, 0.62)

        if i % 40 == 0:
            log(f"  orchestra: day {i + 1}/{n}")

    log("  orchestra: hall reverb ...")
    if gentle:                                   # the sea: slow swells of soft filtered noise under the music
        nS = len(mix.L)
        rng = np.random.default_rng(7)
        t = np.arange(nS) / SR
        for ch, ph in ((mix.L, 0.0), (mix.R, 1.3)):
            noise = np.convolve(rng.standard_normal(nS), np.ones(48) / 48, mode="same")
            swell = 0.5 + 0.5 * np.sin(2 * np.pi * t / 9.0 + ph) * np.sin(2 * np.pi * t / 23.0 + ph / 2)
            ch += 0.05 * noise * np.clip(swell, 0, 1) ** 2
        L, R = hall(mix.L, mix.R, seconds=3.8, wet=0.55)
    else:
        L, R = hall(mix.L, mix.R)
    stereo = np.stack([L, R], axis=1)
    stereo /= np.percentile(np.abs(stereo), 99.97) + 1e-9
    stereo = np.tanh(stereo * 1.2) * (0.6 if gentle else 0.95)  # gentle limiter keeps peaks musical; soft style is quieter
    return stereo.astype(np.float32), change
