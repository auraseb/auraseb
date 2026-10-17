#!/usr/bin/env python3
"""Ticker: the contribution count, edge to edge, over one slow line of brand marks.

Reads the live contribution count from github.com/users/<user>/contributions and the brands from
the orgs where the user has opened issues or PRs (GitHub search), writes light.svg and dark.svg.
Pure SVG, CSS animation only, so it renders through GitHub's image proxy.

Marks are the brands' own monochrome marks, all set in ink: vector paths from Simple Icons
where one exists, otherwise the mark keyed out of the org's GitHub avatar (marks/<org>.png,
white on black, used as a luminance mask). No tile, no background, one weight.
"""
import base64, json, math, os, pathlib, re, ssl, subprocess, urllib.request

HERE = pathlib.Path(__file__).resolve().parent
USER = os.environ.get("TICKER_USER", "auraseb")
MARKS = json.loads((HERE / "marks" / "marks.json").read_text())
METRICS = json.loads((HERE / "metrics.json").read_text())  # SF Pro tnum, wght 800, opsz 96, per em

# org login (lowercase) -> mark key, in display order (biggest names first)
ORG_MARKS = [
    ("apple", "apple"), ("openai", "openai"), ("nasa", "nasa"), ("teslamotors", "tesla"),
    ("anthropics", "anthropic"), ("neuralink", "neuralink"), ("aws", "amazonwebservices"),
    ("cloudflare", "cloudflare"), ("vercel", "vercel"), ("nytimes", "newyorktimes"), ("bloomberg", "bloomberg"),
    ("figma", "figma"), ("swiftlang", "swift"), ("mozilla", "mozilla"), ("tailwindlabs", "tailwindcss"),
    ("datadog", "datadog"), ("esa", "esa"), ("oven-sh", "bun"), ("internetarchive", "internetarchive"),
    ("maplibre", "maplibre"), ("owid", "owid"), ("electricitymaps", "electricitymaps"), ("open-meteo", "open-meteo"),
    ("planetlabs", "planet"), ("kiwix", "kiwix"), ("green-software-foundation", "gsf"), ("boavizta", "boavizta"),
]


def active_orgs():
    out = subprocess.run(["gh", "api", "-X", "GET", "search/issues", "-f", f"q=author:{USER} -user:{USER}",
                          "-f", "per_page=100", "--paginate", "--jq", ".items[].repository_url"],
                         capture_output=True, text=True, check=True).stdout.split()
    return {u.split("/repos/")[1].split("/")[0].lower() for u in out}


ACTIVE = active_orgs()
BRANDS = [key for org, key in ORG_MARKS if org in ACTIVE and key in MARKS]

W = 840
THEMES = {
    "light": {"ground": "#FFFFFF", "ink": "#191A1C"},
    "dark": {"ground": "#0D1117", "ink": "#F0F3F6"},
}
SANS = "-apple-system, BlinkMacSystemFont, 'SF Pro Display', Inter, 'Segoe UI', Helvetica, Arial, sans-serif"

NUM_W8, NUM_TRACK = 800, -0.03
TOP = 6            # breathing room above the digit overshoot
GAP = 84           # baseline to the top of the mark row
MARK = 58          # optical size: a square mark is MARK x MARK, wider marks trade height for width
MARK_GAP = 68      # equal white space between marks
BOTTOM = 8
SPEED = 24         # px per second
FADE = 96          # ground colored fade at both strip edges


def total_contributions():
    req = urllib.request.Request(f"https://github.com/users/{USER}/contributions", headers={"User-Agent": "ticker"})
    try:
        ctx = ssl.create_default_context(cafile="/etc/ssl/cert.pem") if os.path.exists("/etc/ssl/cert.pem") else None
        page = urllib.request.urlopen(req, timeout=30, context=ctx).read().decode()
    except Exception:
        page = urllib.request.urlopen(req, timeout=30).read().decode()
    return int(re.search(r"([0-9,]+)\s+contributions?\s+in the last year", page).group(1).replace(",", ""))


def number_layout(num):
    """Font size that makes the ink run exactly edge to edge, plus x offset and advance."""
    pen, first_lsb, last_right = 0.0, None, 0.0
    for ch in num:
        adv, x0, x1, _, _ = METRICS[ch]
        if first_lsb is None:
            first_lsb = x0
        last_right = pen + x1
        pen += adv + NUM_TRACK
    ink = last_right - first_lsb            # em
    size = W / ink
    return size, -first_lsb * size, pen * size


def mark_box(key):
    x, y, w, h = MARKS[key]["bbox"]
    a = w / h
    mh = MARK / math.sqrt(a)                # equal area, so wordmarks and glyphs weigh the same
    mh = min(mh, MARK * 1.08)
    return mh * a, mh


def mark_def(key, ink):
    m = MARKS[key]
    x, y, w, h = m["bbox"]
    mw, mh = mark_box(key)
    if "path" in m:
        s = mh / h
        return (f'<g id="m-{key}"><path fill="{ink}" transform="scale({s:.4f}) translate({-x:.3f} {-y:.3f})" '
                f'd="{m["path"]}"/></g>')
    raw = (HERE / "marks" / m["png"]).read_bytes()
    uri = f"data:image/png;base64,{base64.b64encode(raw).decode()}"
    return (f'<mask id="k-{key}" maskUnits="userSpaceOnUse" x="0" y="0" width="{mw:.2f}" height="{mh:.2f}">'
            f'<image href="{uri}" width="{mw:.2f}" height="{mh:.2f}"/></mask>'
            f'<g id="m-{key}"><rect width="{mw:.2f}" height="{mh:.2f}" fill="{ink}" mask="url(#k-{key})"/></g>')


def build(theme):
    t = THEMES[theme]
    num = f"{total_contributions():,}"
    size, num_x, num_adv = number_layout(num)
    cap = max(METRICS[c][4] for c in num if c.isdigit()) * size
    base = round(TOP + cap)
    row_mid = base + GAP + MARK / 2
    H = round(row_mid + MARK / 2 + BOTTOM)

    items, x = [], 0.0
    for key in BRANDS or []:
        mw, mh = mark_box(key)
        items.append(f'<use href="#m-{key}" x="{x:.2f}" y="{row_mid - mh / 2:.2f}"/>')
        x += mw + MARK_GAP
    run = "".join(items)
    width = x or 1.0
    copies = math.ceil(W / width) + 1 if items else 0
    lead = FADE + 8  # first mark sits fully clear of the left fade in the opening (and reduced motion) frame

    css = (
        f".n{{font-family:{SANS};font-size:{size:.2f}px;font-weight:{NUM_W8};letter-spacing:{NUM_TRACK}em;"
        f"fill:{t['ink']};font-variant-numeric:tabular-nums;font-feature-settings:'tnum'}}"
        f"@keyframes s{{from{{transform:translateX(0)}}to{{transform:translateX(-{width:.2f}px)}}}}"
        f".s{{animation:s {width / SPEED:.1f}s linear infinite}}"
        "@media (prefers-reduced-motion:reduce){.s{animation:none}}"
    )
    fade = (
        f'<linearGradient id="fl"><stop offset="0" stop-color="{t["ground"]}"/>'
        f'<stop offset="1" stop-color="{t["ground"]}" stop-opacity="0"/></linearGradient>'
        f'<linearGradient id="fr"><stop offset="0" stop-color="{t["ground"]}" stop-opacity="0"/>'
        f'<stop offset="1" stop-color="{t["ground"]}"/></linearGradient>'
    )
    band_y = base + 20
    defs = "".join(mark_def(k, t["ink"]) for k in BRANDS) + fade
    strip = "".join(f'<g transform="translate({i * width:.2f} 0)">{run}</g>' for i in range(-1, copies))

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{num} contributions">
<style>{css}</style>
<defs>{defs}</defs>
<rect width="{W}" height="{H}" fill="{t["ground"]}"/>
<g transform="translate({lead} 0)"><g class="s">{strip}</g></g>
<rect x="0" y="{band_y}" width="{FADE}" height="{H - band_y}" fill="url(#fl)"/>
<rect x="{W - FADE}" y="{band_y}" width="{FADE}" height="{H - band_y}" fill="url(#fr)"/>
<text class="n" x="{num_x:.2f}" y="{base}" textLength="{num_adv:.2f}" lengthAdjust="spacing">{num}</text>
</svg>
'''
    (HERE / f"{theme}.svg").write_text(svg)
    return H


if __name__ == "__main__":
    for th in THEMES:
        h = build(th)
    print(f"height {h}")
