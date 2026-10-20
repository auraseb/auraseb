#!/usr/bin/env python3
"""Light-trail calendar: the last year of auraseb contributions drawn as
long-exposure neon ribbons, one per weekday (Sun at top), one column per week.
Ribbon width, glow and brightness follow each day's count; brand merge days
get a star flare; a comet of light runs along the trails on a loop.

Python 3 stdlib only.
  GH_TOKEN=... python3 gen.py [--merges merges.json] [--calendar cal.json] [--out DIR]
Writes light.svg and dark.svg into --out (default: this folder).
  --merges    JSON list of ISO timestamps (PR mergedAt). Optional.
  --calendar  cached GraphQL response, for offline runs. Optional.
  --tz        timezone used to bucket merges into calendar days.
"""
import argparse, datetime, json, math, os, urllib.request

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

LOGIN = "auraseb"
W, H = 840, 280
X0, X1 = 30.0, 750.0   # first and last week column
K = 13                 # fibres per ribbon
PERIOD = 9.0           # seconds per pulse loop
TRAVEL = 0.70          # share of the loop the comet spends crossing
COMET = 260.0          # comet length in px

QUERY = ('query { user(login:"%s") { contributionsCollection { contributionCalendar '
         '{ weeks { contributionDays { date contributionCount } } } } } }' % LOGIN)

THEMES = {
    "dark": dict(
        bg0="#0b0714", bg1="#060409", bloom="#6a2bd9", bloom2="#ff3fb8", bloom_op=0.85,
        border="#24162f",
        ramp=[(0.0, (104, 72, 196), 0.34), (0.30, (146, 92, 255), 0.70),
              (0.55, (214, 74, 240), 0.92), (0.80, (255, 86, 196), 1.0),
              (1.0, (255, 214, 244), 1.0)],
        glow_op=0.42, wide_op=0.34, edge_w=0.7, inner_w=0.5, core_w=0.9,
        edge_op=0.42, core_op=1.0, floor_op=0.22,
        comet="#ffffff", comet_op=0.95, comet_floor=0.1,
        head_r="7", flare_core="#ffffff", flare_glow="#ff5fd2", flare_ray="#ffd9f6", ray_core="#ffffff",
    ),
    "light": dict(
        bg0="#ffffff", bg1="#fcfaff", bloom="#e4d4ff", bloom2="#ffd3ec", bloom_op=0.22,
        border="#ece4f4",
        ramp=[(0.0, (150, 128, 214), 0.55), (0.30, (109, 40, 217), 0.85),
              (0.55, (168, 26, 200), 0.95), (0.80, (219, 20, 130), 1.0),
              (1.0, (190, 8, 92), 1.0)],
        glow_op=0.2, wide_op=0.07, edge_w=0.7, inner_w=0.5, core_w=0.95,
        edge_op=0.5, core_op=1.0, floor_op=0.3,
        comet="#ff1a8c", comet_op=0.9, comet_floor=0.25,
        head_r="5", flare_core="#ffffff", flare_glow="#ff1a8c", flare_ray="#e0158f", ray_core="#9d0061",
    ),
}


# ---------------------------------------------------------------- data
def fetch_calendar(path=None):
    if path:
        data = json.load(open(path))
    else:
        req = urllib.request.Request(
            "https://api.github.com/graphql",
            data=json.dumps({"query": QUERY}).encode(),
            headers={"Authorization": "bearer " + os.environ["GH_TOKEN"],
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)
    weeks = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    grid = []  # grid[week][weekday Sun=0] = (date, count)
    for wk in weeks:
        col = {}
        for d in wk["contributionDays"]:
            dt = datetime.date.fromisoformat(d["date"])
            col[(dt.weekday() + 1) % 7] = (d["date"], d["contributionCount"])
        grid.append(col)
    return grid


def load_merges(path, tz="America/New_York"):
    if not path or not os.path.exists(path):
        return {}
    zone = ZoneInfo(tz) if ZoneInfo else None
    out = {}
    for ts in json.load(open(path)):
        dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if zone:
            dt = dt.astimezone(zone)
        key = dt.date().isoformat()
        out[key] = out.get(key, 0) + 1
    return out


# ---------------------------------------------------------------- geometry
def f(v):
    s = "%.1f" % v
    return "0" if s in ("0.0", "-0.0") else (s[:-2] if s.endswith(".0") else s)


def smoothstep(u):
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


def spacing(u):
    # rows draw together toward the left, like trails receding into distance
    return 15.0 + 14.0 * (0.7 * smoothstep(u) + 0.3 * u)


def center_y(u):
    # the bundle sweeps up from lower left, the way the avatar's trail rises
    return H / 2 + 12 * max(0.0, 1 - u) ** 1.6 - 4 * math.sin(u * math.pi)


def drift(r, u):
    # quiet early trails weave gently, like lights drifting in a long exposure
    return 4.5 * max(0.0, 1 - u) ** 2 * math.sin(u * 13.0 + r * 0.9)


def catmull(pts):
    d = ["M%s %s" % (f(pts[0][0]), f(pts[0][1]))]
    for i in range(len(pts) - 1):
        p0 = pts[i - 1] if i > 0 else pts[i]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[i + 2] if i + 2 < len(pts) else p2
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d.append("C%s %s %s %s %s %s" % (f(c1[0]), f(c1[1]), f(c2[0]), f(c2[1]), f(p2[0]), f(p2[1])))
    return "".join(d)


def ramp(theme, s):
    stops = theme["ramp"]
    for (a, ca, oa), (b, cb, ob) in zip(stops, stops[1:]):
        if s <= b:
            t = (s - a) / (b - a) if b > a else 0
            c = tuple(round(ca[i] + (cb[i] - ca[i]) * t) for i in range(3))
            return "#%02x%02x%02x" % c, oa + (ob - oa) * t
    return "#%02x%02x%02x" % stops[-1][1], stops[-1][2]


# ---------------------------------------------------------------- build
def build(grid, merges, theme_name):
    th = THEMES[theme_name]
    n = len(grid)
    step = (X1 - X0) / (n - 1)
    xs = [X0 + i * step for i in range(n)]
    counts = sorted(c for col in grid for (_, c) in col.values())
    cap = max(counts[int(len(counts) * 0.985)] if counts else 1, 20)

    def u_of(x):
        return (x - X0) / (X1 - X0)

    def level(c):
        return min(1.0, math.log1p(c) / math.log1p(cap))

    defs, wide, glow, strands, comets, flares = [], [], [], [], [], []
    heads = []
    for r in range(7):
        idx = [i for i in range(n) if r in grid[i]]
        raw = [level(grid[i][r][1]) for i in idx]
        sm = []
        for j, v in enumerate(raw):
            a = raw[j - 1] if j > 0 else v
            b = raw[j + 1] if j + 1 < len(raw) else v
            sm.append(max(v * 0.72, 0.25 * a + 0.5 * v + 0.25 * b))
        px = [xs[i] for i in idx]
        # capped below half the row pitch so busy rows blaze without fusing
        half = [1.1 + sm[j] * 0.40 * spacing(u_of(px[j])) for j in range(len(px))]
        # the trail head tapers into a point of light just past today
        hx, hh, hs = px[-1], half[-1], sm[-1]
        for q, k in enumerate((0.9, 0.7, 0.45, 0.22, 0.07, 0.0)):
            px.append(hx + step * 0.75 * (q + 1))
            half.append(max(0.3, hh * k))
            sm.append(hs)
        ys = [center_y(u_of(x)) + (r - 3) * spacing(u_of(x)) + drift(r, u_of(x)) for x in px]

        # colour gradient: brightness follows the count
        st = []
        for j in range(len(px)):
            col, op = ramp(th, sm[j])
            st.append('<stop offset="%.4f" stop-color="%s" stop-opacity="%.2f"/>' % (u_of(px[j]), col, op))
        defs.append('<linearGradient id="g%d" gradientUnits="userSpaceOnUse" x1="%s" y1="0" x2="%s" y2="0">%s</linearGradient>'
                    % (r, f(X0), f(X1), "".join(st)))
        # comet intensity mask: bright over busy stretches, faint over wisps
        st = []
        for j in range(len(px)):
            st.append('<stop offset="%.4f" stop-color="#fff" stop-opacity="%.2f"/>'
                      % (u_of(px[j]), th["comet_floor"] + (1 - th["comet_floor"]) * sm[j]))
        defs.append('<linearGradient id="i%d" gradientUnits="userSpaceOnUse" x1="%s" y1="0" x2="%s" y2="0">%s</linearGradient>'
                    % (r, f(X0), f(X1), "".join(st)))
        defs.append('<mask id="k%d" maskUnits="userSpaceOnUse" x="0" y="0" width="%d" height="%d">'
                    '<rect width="%d" height="%d" fill="url(#i%d)"/></mask>' % (r, W, H, W, H, r))
        # comet gradient, slid along x by SMIL (runs inside GitHub's image proxy)
        begin = r * 0.38
        defs.append(
            '<linearGradient id="c%d" gradientUnits="userSpaceOnUse" x1="%s" y1="0" x2="0" y2="0">'
            '<stop offset="0" stop-color="%s" stop-opacity="0"/>'
            '<stop offset=".7" stop-color="%s" stop-opacity=".35"/>'
            '<stop offset=".96" stop-color="%s" stop-opacity="1"/>'
            '<stop offset="1" stop-color="%s" stop-opacity="0"/>'
            '<animateTransform attributeName="gradientTransform" type="translate" '
            'values="%s 0;%s 0;%s 0" keyTimes="0;%.2f;1" dur="%.1fs" begin="%.2fs" repeatCount="indefinite"/>'
            '</linearGradient>'
            % (r, f(-COMET), th["comet"], th["comet"], th["comet"], th["comet"],
               f(X0 - 10), f(W + COMET + 10), f(W + COMET + 10), TRAVEL, PERIOD, begin))

        # glow band
        up = [(px[j], ys[j] - half[j] * 1.2) for j in range(len(px))]
        lo = [(px[j], ys[j] + half[j] * 1.2) for j in reversed(range(len(px)))]
        band = catmull(up) + "L" + catmull(lo)[1:] + "Z"
        glow.append('<path class="br b%d" d="%s" fill="url(#g%d)"/>' % (r, band, r))
        wide.append('<path d="%s" fill="url(#g%d)"/>' % (band, r))

        # fibres
        sp, cp = [], []
        for k in range(K):
            t = -1 + 2 * k / (K - 1)
            d = catmull([(px[j], ys[j] + t * half[j]) for j in range(len(px))])
            # long-exposure profile: hot core, fibres fading toward soft edges
            a = math.exp(-(t / 0.5) ** 2)
            edge = abs(t) > 0.99
            w = th["edge_w"] if edge else th["inner_w"] + (th["core_w"] - th["inner_w"]) * a
            op = th["edge_op"] if edge else th["floor_op"] + (th["core_op"] - th["floor_op"]) * a
            sp.append('<path d="%s" stroke-width="%s" stroke-opacity="%.2f"/>' % (d, f(w), op))
            if k % 3 == 0:
                cp.append('<path d="%s" stroke-width="%s"/>' % (d, f(w + 0.5)))
        strands.append('<g stroke="url(#g%d)">%s</g>' % (r, "".join(sp)))
        comets.append('<g mask="url(#k%d)" stroke="url(#c%d)">%s</g>' % (r, r, "".join(cp)))
        heads.append((idx, px, ys, begin))

    # star flares on brand merge days, lit as the comet passes
    mx = max(merges.values()) if merges else 1
    span = (W + COMET + 10) - (X0 - 10)
    for r in range(7):
        idx, px, ys, begin = heads[r]
        hj = len(idx) + 5  # tip of the taper: where the light source sits
        flares.append('<circle class="hd" cx="%s" cy="%s" r="%s" fill="url(#fg)"/>'
                      '<circle cx="%s" cy="%s" r="1.1" fill="%s"/>'
                      % (f(px[hj]), f(ys[hj]), th["head_r"], f(px[hj]), f(ys[hj]), th["flare_core"]))
        for j, i in enumerate(idx):
            m = merges.get(grid[i][r][0], 0)
            if not m:
                continue
            size = 11 + 11 * math.sqrt(m / mx)
            x, y = px[j], ys[j]
            # comet head reaches x when translate == x
            t_hit = begin + (x - (X0 - 10)) / span * TRAVEL * PERIOD
            # negative phase offset: same timing, but no unanimated first frame
            delay = (t_hit - 0.06 * PERIOD) % PERIOD - PERIOD
            vmax = 0.5 * spacing(u_of(x))  # vertical ray stays inside its own row

            def ray(length, width, rot):
                return ('<path d="M0 -%s L%s 0 L0 %s L-%s 0Z" fill="url(#fr)" transform="rotate(%d)"/>'
                        % (f(length), f(width), f(length), f(width), rot))
            flares.append(
                '<g transform="translate(%s %s)"><g class="fl" style="animation-delay:%.2fs">'
                '<circle r="%s" fill="url(#fg)"/>%s%s%s%s<circle r="%s" fill="%s"/></g></g>'
                % (f(x), f(y), delay, f(size * 1.25),
                   ray(size * 2.3, size * 0.085, 90), ray(min(size * 1.1, vmax), size * 0.085, 0),
                   ray(size * 0.7, size * 0.055, 45), ray(size * 0.7, size * 0.055, -45),
                   f(max(2.0, size * 0.16)), th["flare_core"]))

    css = (
        ".hd{opacity:.7}.br{animation:breathe 6s ease-in-out infinite alternate}"
        "@keyframes breathe{0%{opacity:.6}100%{opacity:1}}"
        + "".join(".b%d{animation-delay:-%.1fs}" % (r, r * 0.85) for r in range(7))
        + ".fl{transform-box:fill-box;transform-origin:center;animation:flare %.1fs ease-out infinite}"
          "@keyframes flare{0%%{opacity:.88;transform:scale(1)}"
          "6%%{opacity:1;transform:scale(1.6) rotate(8deg)}"
          "26%%{opacity:.9;transform:scale(1.05)}100%%{opacity:.88;transform:scale(1)}}" % PERIOD
        + "@media (prefers-reduced-motion: reduce){.cm{display:none}"
          ".br{animation:none;opacity:.85}.fl{animation:none;opacity:1;transform:none}}"
    )

    g = th
    o = []
    o.append('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" fill="none">' % (W, H, W, H))
    o.append("<style>%s</style>" % css)
    o.append("<defs>")
    o.append('<clipPath id="card"><rect width="%d" height="%d" rx="14"/></clipPath>' % (W, H))
    o.append('<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="%s"/>'
             '<stop offset="1" stop-color="%s"/></linearGradient>' % (g["bg0"], g["bg1"]))
    o.append('<radialGradient id="bl" gradientUnits="userSpaceOnUse" cx="700" cy="140" r="520" '
             'gradientTransform="translate(700 140) scale(1 .5) translate(-700 -140)">'
             '<stop offset="0" stop-color="%s" stop-opacity=".42"/><stop offset=".45" stop-color="%s" stop-opacity=".16"/>'
             '<stop offset="1" stop-color="%s" stop-opacity="0"/></radialGradient>' % (g["bloom2"], g["bloom"], g["bloom"]))
    o.append('<radialGradient id="fg"><stop offset="0" stop-color="%s" stop-opacity=".9"/>'
             '<stop offset=".3" stop-color="%s" stop-opacity=".4"/><stop offset="1" stop-color="%s" stop-opacity="0"/></radialGradient>'
             % (g["flare_glow"], g["flare_glow"], g["flare_glow"]))
    o.append('<radialGradient id="fr"><stop offset="0" stop-color="%s"/><stop offset=".5" stop-color="%s" stop-opacity=".8"/>'
             '<stop offset="1" stop-color="%s" stop-opacity="0"/></radialGradient>'
             % (g["ray_core"], g["flare_ray"], g["flare_ray"]))
    o.append('<filter id="soft" x="-5%" y="-40%" width="110%" height="180%"><feGaussianBlur stdDeviation="3.5"/></filter>')
    o.append('<filter id="wide" x="-10%" y="-60%" width="120%" height="220%"><feGaussianBlur stdDeviation="14"/></filter>')
    o.append('<filter id="cg" x="-5%" y="-60%" width="110%" height="220%"><feGaussianBlur stdDeviation="2" result="b"/>'
             '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>')
    o.append('<linearGradient id="fade" gradientUnits="userSpaceOnUse" x1="%s" y1="0" x2="%s" y2="0">'
             '<stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#fff"/></linearGradient>'
             % (f(X0 - 4), f(X0 + 70)))
    o.append('<mask id="m" maskUnits="userSpaceOnUse" x="0" y="0" width="%d" height="%d">'
             '<rect width="%d" height="%d" fill="url(#fade)"/></mask>' % (W, H, W, H))
    o.extend(defs)
    o.append("</defs>")
    o.append('<g clip-path="url(#card)">')
    o.append('<rect width="%d" height="%d" fill="url(#bg)"/>' % (W, H))
    o.append('<rect width="%d" height="%d" fill="url(#bl)" opacity="%.2f"/>' % (W, H, g["bloom_op"]))
    o.append('<g mask="url(#m)">')
    o.append('<g filter="url(#wide)" opacity="%.2f">%s</g>' % (g["wide_op"], "".join(wide)))
    o.append('<g filter="url(#soft)" opacity="%.2f">%s</g>' % (g["glow_op"], "".join(glow)))
    o.append('<g fill="none" stroke-linecap="round">%s</g>' % "".join(strands))
    o.append('<g class="cm" fill="none" stroke-linecap="round" filter="url(#cg)" opacity="%.2f">%s</g>'
             % (g["comet_op"], "".join(comets)))
    o.append("</g>")
    o.append("".join(flares))
    o.append("</g>")
    o.append('<rect x=".5" y=".5" width="%d" height="%d" rx="13.5" stroke="%s"/>' % (W - 1, H - 1, g["border"]))
    o.append("</svg>")
    return "\n".join(o)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--merges")
    ap.add_argument("--calendar")
    ap.add_argument("--tz", default="America/New_York")
    ap.add_argument("--out", default=os.path.dirname(os.path.abspath(__file__)))
    a = ap.parse_args()
    grid = fetch_calendar(a.calendar)
    merges = load_merges(a.merges, a.tz)
    for name in ("light", "dark"):
        svg = build(grid, merges, name)
        p = os.path.join(a.out, name + ".svg")
        with open(p, "w") as fh:
            fh.write(svg)
        print(p, len(svg.encode()), "bytes")


if __name__ == "__main__":
    main()
