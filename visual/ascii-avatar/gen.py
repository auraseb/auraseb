#!/usr/bin/env python3
"""ASCII avatar banner for github.com/auraseb.

Redraws the avatar (a figure mid leap inside a looping ribbon of light) as
colour ASCII: the figure is sampled from avatar.png, the light ribbon is drawn
as a bundle of curves so it can sweep across the whole banner. A bright pulse
travels along the ribbon and swaps its glyphs; background specks twinkle.

Python 3 stdlib only. Usage:
    python3 gen.py [--avatar avatar.png] [--out .]
Writes dark.svg and light.svg.
"""
import argparse, math, os, random, struct, zlib

W, H = 840, 296
DY = 10                       # vertical offset of the whole drawing
CW, CH = 4.8, 7.0             # character cell
COLS, ROWS = int(W / CW), int(H / CH)
FONT = 7.9
PERIOD = 8.0                  # seconds for one pulse lap
NPH = 240
NQ = 90                       # shimmer phase buckets
SHIMMER = 6.0                     # phase buckets along the ribbon

# figure placement: banner = source * S + (OX, OY)
S, OX, OY = 1.02, 372.0, -46.0 + DY
FIG_LO, FIG_HI = 0.5, 0.72        # mean darkness that counts as figure
FEET_Y = 298                      # source rows below this are the cast shadow, not the figure


# ---------------------------------------------------------------- png
def read_png(path):
    data = open(path, 'rb').read()
    assert data[:8] == b'\x89PNG\r\n\x1a\n'
    pos, idat, w = 8, b'', None
    while pos < len(data):
        ln, typ = struct.unpack('>I4s', data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + ln]
        if typ == b'IHDR':
            w, h, depth, ctype, _, _, inter = struct.unpack('>IIBBBBB', body)
            assert depth == 8 and ctype in (2, 6) and inter == 0
            bpp = 3 if ctype == 2 else 4
        elif typ == b'IDAT':
            idat += body
        pos += 12 + ln
    raw = zlib.decompress(idat)
    stride = w * bpp
    out, prev, i = [], bytearray(stride), 0
    for _ in range(h):
        f = raw[i]; line = bytearray(raw[i + 1:i + 1 + stride]); i += 1 + stride
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0
            b = prev[x]
            c = prev[x - bpp] if x >= bpp else 0
            if f == 1: line[x] = (line[x] + a) & 255
            elif f == 2: line[x] = (line[x] + b) & 255
            elif f == 3: line[x] = (line[x] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c; pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                line[x] = (line[x] + pr) & 255
        out.append([(line[x] / 255, line[x + 1] / 255, line[x + 2] / 255) for x in range(0, stride, bpp)])
        prev = line
    return out


def lum(c):
    return 0.3 * c[0] + 0.55 * c[1] + 0.15 * c[2]


def solve(M, v):
    n = len(v); M = [row[:] + [v[i]] for i, row in enumerate(M)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c])); M[c], M[p] = M[p], M[c]
        for r in range(n):
            if r != c:
                k = M[r][c] / M[c][c]
                M[r] = [a - k * b for a, b in zip(M[r], M[c])]
    return [M[i][n] / M[i][i] for i in range(n)]


def fit_background(img):
    """Robust smooth fit of the pink to violet backdrop (luminance only)."""
    h, w = len(img), len(img[0])
    basis = lambda x, y: (1, x, y, x * x, x * y, y * y, x ** 3, y ** 3)
    pts = [(x / w, y / h, lum(img[y][x])) for y in range(0, h, 3) for x in range(0, w, 3)]
    keep = pts
    for _ in range(6):
        A = [[0.0] * 8 for _ in range(8)]; b = [0.0] * 8
        for x, y, l in keep:
            f = basis(x, y)
            for i in range(8):
                b[i] += f[i] * l
                for j in range(8):
                    A[i][j] += f[i] * f[j]
        coef = solve(A, b)
        model = lambda x, y: sum(c * f for c, f in zip(coef, basis(x, y)))
        res = sorted(abs(l - model(x, y)) for x, y, l in keep)
        thr = max(res[int(len(res) * 0.7)], 0.02)
        keep = [p for p in pts if abs(p[2] - model(p[0], p[1])) < thr]
    return lambda x, y: model(x / w, y / h)


# ---------------------------------------------------------------- figure
def figure_cells(img):
    """Per cell: coverage (0..1) and light (0..1) of the leaping figure."""
    h, w = len(img), len(img[0])
    bgl = fit_background(img)
    cells = {}
    for r in range(ROWS):
        for c in range(COLS):
            x0, x1 = (c * CW - OX) / S, ((c + 1) * CW - OX) / S
            y0, y1 = (r * CH - OY) / S, ((r + 1) * CH - OY) / S
            if x1 < 170 or x0 > 392 or y1 < 62 or y0 > FEET_Y:
                continue
            n = 0; dsum = 0.0; ls = 0.0; ln = 0; rgb = [0.0, 0.0, 0.0]
            for sy in range(6):
                for sx in range(4):
                    x = int(x0 + (sx + 0.5) * (x1 - x0) / 4); y = int(y0 + (sy + 0.5) * (y1 - y0) / 6)
                    if not (0 <= x < w and 0 <= y < h) or y > FEET_Y:
                        continue
                    l = lum(img[y][x]); dk = (bgl(x, y) - l) / 0.5
                    n += 1; dsum += dk
                    if dk > 0.42:
                        ls += l; ln += 1
                        for q in range(3): rgb[q] += img[y][x][q]
            if not n or not ln:
                continue
            md = dsum / n
            cv = min(1, max(0, (md - FIG_LO) / (FIG_HI - FIG_LO)))
            if cv <= 0:
                continue
            light = min(1, max(0, (ls / ln - 0.15) / 0.42))
            cells[(r, c)] = (cv, light, tuple(q / ln for q in rgb))
    ls_ = sorted(v[1] for v in cells.values())
    lo, hi = ls_[int(len(ls_) * .05)], ls_[int(len(ls_) * .97)]
    return {k: (cv, min(1, max(0, (l - lo) / (hi - lo))), rgb) for k, (cv, l, rgb) in cells.items()}


# ---------------------------------------------------------------- ribbon
# spine of the light ribbon in banner px: (x, y, half width). The right part
# follows the avatar's loop around the figure, the left part is the trail
# carried on across the banner; the lower strand passes the figure's legs.
SPINE = [(-120, 150, 66), (0, 138, 64), (190, 112, 60), (380, 84, 52), (540, 55, 38),
         (630, 38, 27), (700, 42, 19), (745, 65, 15), (760, 102, 13), (748, 152, 13),
         (714, 196, 13), (660, 234, 14), (595, 266, 18), (525, 300, 24), (455, 336, 30),
         (400, 362, 32)]
HATCH = 14.0                      # px period of the fine lines inside the ribbon


def catmull(pts, n=120):
    out = []
    P = [pts[0]] + pts + [pts[-1]]
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for k in range(n):
            t = k / n; t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * (2 * p1[j] + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2
                                    + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3) for j in range(len(p1))))
    out.append(tuple(pts[-1]))
    return out


def smooth(t):
    t = min(1, max(0, t))
    return t * t * (3 - 2 * t)


def fade_at(x):
    """Trail strength by x: full near the figure, a faint tail at the left edge."""
    return 0.16 + 0.84 * smooth((x + 20) / 470)


def ribbon_cells():
    """Every character cell inside the ribbon, with its offset from the spine.

    Per cell: s (0..1 along the ribbon), o (px offset across it), hw (half
    width), ang (tangent angle), edge (None or sub cell position of the
    ribbon's bright rim that crosses this cell)."""
    spine = catmull([(x, y + DY, w) for x, y, w in SPINE], 90)
    L = [0.0]
    for p, q in zip(spine, spine[1:]):
        L.append(L[-1] + math.hypot(q[0] - p[0], q[1] - p[1]))
    total = L[-1]
    best = {}
    for i, (x, y, hw) in enumerate(spine):
        j, i0 = min(i + 1, len(spine) - 1), max(i - 1, 0)
        tx, ty = spine[j][0] - spine[i0][0], spine[j][1] - spine[i0][1]
        tl = math.hypot(tx, ty) or 1
        tx, ty = tx / tl, ty / tl
        nx, ny = -ty, tx
        steps = int((2 * hw + 10) / 1.5) + 2
        for k in range(steps + 1):
            o = -hw - 5 + (2 * hw + 10) * k / steps
            px, py = x + nx * o, y + ny * o
            c, r = int(px // CW), int(py // CH)
            if not (0 <= c < COLS and 0 <= r < ROWS):
                continue
            cx, cy = (c + .5) * CW, (r + .5) * CH
            d = math.hypot(px - cx, py - cy)
            if (r, c) not in best or d < best[(r, c)][0]:
                oc = o + (cx - px) * nx + (cy - py) * ny
                best[(r, c)] = (d, oc, hw, L[i] / total, math.atan2(ty, tx), nx, ny)
    out = {}
    for (r, c), (_, oc, hw, s, ang, nx, ny) in best.items():
        e = 0.5 * (abs(nx) * CW + abs(ny) * CH)        # half cell extent across
        if abs(oc) > hw + e:
            continue
        edge = None
        for side in (-1, 1):
            dd = side * hw - oc                         # rim offset from cell centre
            if abs(dd) <= e and (edge is None or abs(dd) < abs(edge[0])):
                edge = (dd, 0.5 + dd * ny / CH)
        if edge is None and abs(oc) > hw:
            continue
        out[(r, c)] = dict(s=s, o=oc, hw=hw, ang=ang, edge=edge and edge[1],
                           fade=fade_at((c + .5) * CW))
    return out


def dither(r, c):
    """Stable pseudo random 0..1 per cell, used to dissolve the trail's tail."""
    h = (r * 73856093) ^ (c * 19349663)
    h = (h ^ (h >> 13)) * 1274126177 & 0xffffffff
    return (h & 0xffff) / 65535


def orient(ang):
    d = math.degrees(ang) % 180
    if d < 28 or d > 152: return '-'
    if d < 68: return '\\'
    if d < 112: return '|'
    return '/'


def rim_glyph(ang, yf):
    k = orient(ang)
    if k != '-':
        return k
    if yf < 0.3: return '¯'
    if yf > 0.7: return '_'
    return '─'


BODY = {'-': '.-=', '\\': '.\\\\', '|': '.:|', '/': './/'}
HEAVY = {'-': '=', '─': '━', '_': '=', '¯': '=', '\\': '\\', '|': '┃', '/': '/',
         '.': '-', ':': '|', '=': '≡'}


# ---------------------------------------------------------------- colour
def hexc(c):
    return '#%02x%02x%02x' % tuple(max(0, min(255, int(round(v)))) for v in c)


def mix(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def h2c(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


THEMES = {
    'dark': dict(
        ground=('#0b0912', '#120a17'), stroke='#ffffff14',
        rib=[h2c('#6d5cff'), h2c('#a35cff'), h2c('#e04bff'), h2c('#ff4fd2'), h2c('#ff6fb8')],
        hot=h2c('#ffe8fb'),
        fig=[h2c('#6f5fb0'), h2c('#a993e8'), h2c('#e2d6ff'), h2c('#ffffff')],
        pulse=[h2c('#ff8fe0'), h2c('#fff2fc')],
        speck=[h2c('#5a4a9e'), h2c('#9b4fa8')],
    ),
    'light': dict(
        ground=('#fcfaff', '#fff8fd'), stroke='#2a124014',
        rib=[h2c('#5b4cf0'), h2c('#8a3df0'), h2c('#c22fe0'), h2c('#e01fa8'), h2c('#ea2f8a')],
        hot=h2c('#5a0f6e'),
        fig=[h2c('#b9a6dc'), h2c('#7a5fb0'), h2c('#402670'), h2c('#1c0f33')],
        pulse=[h2c('#e62aa8'), h2c('#9b0f9a')],
        speck=[h2c('#c4b5ee'), h2c('#efb3df')],
    ),
}

RAMP_FIG = '.:;!+*o%#&@'          # no letters or digits, so no run reads as a word


def ramp_pick(v, ramp):
    v = min(0.999, max(0, v))
    return ramp[int(v * len(ramp))]


# ---------------------------------------------------------------- build
def build(theme, fig, rib, seed=7):
    T = THEMES[theme]
    rnd = random.Random(seed)
    classes = {}     # colour -> class name

    def cls(col):
        hx = hexc(col)
        if hx not in classes:
            classes[hx] = 'k%d' % len(classes)
        return classes[hx]

    base, pulse, specks = {}, {}, {}
    # ribbon
    bg = (14, 10, 22) if theme == 'dark' else (252, 249, 255)
    q5 = lambda col: tuple(round(q / 6) * 6 for q in col)
    for (r, c), d in rib.items():
        if (r, c) in fig and fig[(r, c)][0] > 0.3:
            continue
        x = (c + .5) * CW
        t = min(1, max(0, (x - 60) / 700))                 # hue runs violet -> pink with x
        seg = t * (len(T['rib']) - 1); i0 = min(int(seg), len(T['rib']) - 2)
        col = mix(T['rib'][i0], T['rib'][i0 + 1], seg - i0)
        f = d['fade']
        ph = int(d['s'] * NPH) % NPH
        if d['edge'] is not None:
            g = rim_glyph(d['ang'], d['edge'])
            v = 0.35 + 0.65 * f
            col = mix(col, T['hot'], (0.55 if theme == 'dark' else 0.2) * f)
            col = q5(mix(bg, col, v))
            base[(r, c)] = (g, cls(col), 'b p%d' % ph)
            pcol = mix(T['pulse'][0], T['pulse'][1], 0.3 + 0.7 * f)
            pulse[(r, c)] = (HEAVY.get(g, g), cls(q5(mix(bg, pcol, 0.3 + 0.7 * f))), 'h p%d' % ph)
            continue
        dist = d['hw'] - abs(d['o'])                     # px to the nearest rim
        glow = math.exp(-dist / 5.0)
        stripe = 0.5 + 0.5 * math.cos(2 * math.pi * d['o'] / HATCH)
        v = 0.12 + 0.4 * stripe + 0.5 * glow
        if dither(r, c) > 0.35 + 0.65 * f + 0.4 * glow:   # tail dissolves, rims last
            continue
        ramp = BODY[orient(d['ang'])]
        g = ramp[min(len(ramp) - 1, int(v * 1.25 * len(ramp)))]
        a_ = (0.95 if theme == 'dark' else 0.8) * v * f + 0.04
        col = q5(mix(bg, col, min(1, a_)))
        if stripe > 0.75 and f > 0.3:                    # bright hatch lines carry the pulse
            base[(r, c)] = (g, cls(col), 'b p%d' % ph)
            pulse[(r, c)] = (HEAVY.get(g, g), cls(q5(mix(bg, T['pulse'][0], 0.15 + 0.75 * f))), 'h p%d' % ph)
        else:
            base[(r, c)] = (g, cls(col), 'sh q%d' % int(d['s'] * NQ))
    # figure
    for (r, c), (cv, light, rgb) in fig.items():
        lt = light ** 0.75
        q = lt if theme == 'dark' else 1 - lt
        v = (0.28 + 0.72 * q) * (0.5 + 0.5 * cv)
        g = RAMP_FIG[min(len(RAMP_FIG) - 1, int(v * len(RAMP_FIG)))]
        F = T['fig']
        seg = q * (len(F) - 1); i0 = min(int(seg), len(F) - 2)
        col = mix(F[i0], F[i0 + 1], seg - i0)
        # borrow the photo's own tint (pink rim light, violet shadow)
        m = max(rgb) or 1
        tint = tuple(255 * ch / m for ch in rgb)
        if theme == 'light':
            tint = tuple(ch * 0.35 for ch in tint)
        col = mix(col, tint, 0.3)
        col = tuple(round(v_ / 6) * 6 for v_ in col)
        base[(r, c)] = (g, cls(col), '')
        pulse.pop((r, c), None)
    # background specks: sparse stars, denser near the ribbon (scattered light)
    for r in range(ROWS):
        for c in range(COLS):
            if (r, c) in base:
                continue
            near = any((r + dr, c + dc) in rib for dr in (-1, 0, 1) for dc in (-2, -1, 0, 1, 2))
            p = (0.07 if near else 0.012) * (1 if theme == 'dark' else 0.5)
            if rnd.random() < p:
                t = c / COLS
                col = mix(T['speck'][0], T['speck'][1], t)
                specks[(r, c)] = ('.' if rnd.random() < 0.8 else '\'', cls(col), 't%d' % rnd.randint(0, 3))

    def emit(cells, extra):
        out = []
        for r in range(ROWS):
            row = sorted((c, v) for (rr, c), v in cells.items() if rr == r)
            if not row:
                continue
            parts, cur, xs, chars = [], None, [], []
            for c, v in row:
                key = (v[1], extra(v))
                if key != cur and xs:
                    parts.append((cur, xs, chars)); xs, chars = [], []
                cur = key; xs.append(round(c * CW, 1)); chars.append(v[0])
            if xs:
                parts.append((cur, xs, chars))
            spans = []
            for (k, ex), xs, chars in parts:
                txt = ''.join(chars).replace('&', '&amp;').replace('<', '&lt;')
                cl = k + (' ' + ex if ex else '')
                spans.append('<tspan class="%s" x="%s">%s</tspan>' % (cl, ' '.join('%g' % v for v in xs), txt))
            out.append('<text y="%g">%s</text>' % (round(r * CH + CH - 1.2, 1), ''.join(spans)))
        return '\n'.join(out)

    body_specks = emit(specks, lambda v: v[2])
    body_base = emit(base, lambda v: v[2])
    body_pulse = emit(pulse, lambda v: v[2])

    css = []
    css.append("text{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,'DejaVu Sans Mono','Liberation Mono',monospace;"
               "font-size:%.1fpx;font-weight:700;white-space:pre}" % FONT)
    for hx, k in classes.items():
        css.append('.%s{fill:%s}' % (k, hx))
    css.append('.b{animation:bo %.1fs linear infinite}' % PERIOD)
    css.append('.h{fill-opacity:0;animation:hi %.1fs linear infinite}' % PERIOD)
    for p in range(NPH):
        css.append('.p%d{animation-delay:%.2fs}' % (p, -PERIOD + p / NPH * PERIOD * 0.78))
    css.append('@keyframes hi{0%{fill-opacity:0}2%{fill-opacity:1}14%{fill-opacity:0}100%{fill-opacity:0}}')
    css.append('@keyframes bo{0%{fill-opacity:1}2%{fill-opacity:0}14%{fill-opacity:1}100%{fill-opacity:1}}')
    css.append('.sh{animation:sh %.1fs ease-in-out infinite}' % SHIMMER)
    for q in range(NQ):
        css.append('.q%d{animation-delay:%.2fs}' % (q, -q / NQ * SHIMMER * 2.5 % SHIMMER))
    css.append('@keyframes sh{0%,100%{fill-opacity:1}50%{fill-opacity:.42}}')
    for i, (dur, lo) in enumerate([(3.1, .15), (4.3, .25), (5.7, .1), (7.9, .3)]):
        css.append('.t%d{animation:tw%d %.1fs ease-in-out infinite %.1fs}' % (i, i, dur, -i * 1.3))
        css.append('@keyframes tw%d{0%%,100%%{fill-opacity:.9}50%%{fill-opacity:%.2f}}' % (i, lo))
    css.append('@media (prefers-reduced-motion:reduce){.b,.h,.sh,.t0,.t1,.t2,.t3{animation:none}}')

    g0, g1 = T['ground']
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="ASCII drawing of a figure leaping through a ribbon of light">
<style>{''.join(css)}</style>
<defs><linearGradient id="g" x1="0" x2="1" y1="0" y2="0"><stop offset="0" stop-color="{g0}"/><stop offset="1" stop-color="{g1}"/></linearGradient></defs>
<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="14" fill="url(#g)" stroke="{T['stroke']}"/>
<g>
{body_specks}
</g>
<g>
{body_base}
</g>
<g>
{body_pulse}
</g>
</svg>
'''
    return svg


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument('--avatar', default=os.path.join(here, 'avatar.png'))
    ap.add_argument('--out', default=here)
    a = ap.parse_args()
    img = read_png(a.avatar)
    fig = figure_cells(img)
    rib = ribbon_cells()
    for theme in ('dark', 'light'):
        p = os.path.join(a.out, theme + '.svg')
        open(p, 'w').write(build(theme, fig, rib))
        print(p, os.path.getsize(p))


if __name__ == '__main__':
    main()
