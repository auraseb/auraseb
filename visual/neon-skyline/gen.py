#!/usr/bin/env python3
"""Neon Skyline: draws the last year of GitHub contributions as a night city.

Each week is a building (height follows the week's contributions), its windows
light up by the days that had contributions, and weeks with merged brand PRs
carry a pulsing beacon with a searchlight. Writes light.svg and dark.svg.

Python 3 stdlib only.
  GH_TOKEN=... python3 gen.py [--user auraseb] [--out DIR]
                              [--merges merges.json] [--calendar cal.json]
--merges   JSON list of ISO dates (merge times) used for the roof beacons.
--calendar a saved GraphQL response, to draw without calling the API.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
import os
import urllib.request

W, H = 840, 280
BASE = 206          # street level / horizon
ROAD = 5            # height of the waterfront road
WATER = BASE + ROAD  # mirror line of the reflection
MIN_H, MAX_H = 13.0, 150.0
DX, DY = 4.6, 3.2    # isometric depth of every building (right and up)

QUERY = ('query($login:String!){ user(login:$login){ contributionsCollection{ '
         'contributionCalendar{ weeks{ contributionDays{ date contributionCount } } } } } }')

THEMES = {
    'dark': dict(
        card='#07040f', border='#ffffff14',
        sky=[('0', '#06030d'), ('0.45', '#100726'), ('0.82', '#2a0c47'), ('1', '#4a1257')],
        glow='#ff3ea5', glow_op=0.42, glow2='#8b5cf6', glow2_op=0.30,
        orb=[('0', '#ffffff'), ('0.35', '#ffd9f0'), ('0.75', '#ff8fd0'), ('1', '#c65bff')],
        orb_at=(148, 74, 24), halo='#ff6ec7', halo_op=0.30, stars=95,
        far='#211040', far_op=1.0, far_win='#7b4fc4', far_win_op=0.35,
        mid=('#1d0e38', '#110822'), mid_win='#9c7ae0', mid_win_op=0.45, haze='#ff3ea5', haze_op=0.16, ripple=0.35, bloom=0.95,
        front=('#2b1352', '#120822'), side='#170a2c', roof='#4b2384',
        crown=('#341762', '#1a0b33'),
        unlit='#2c1a4f', unlit_op=0.85,
        lv=['#8a68d6', '#c3a0ff', '#ff86cc', '#fff1fa'],
        rim_lo='#8b5cf6', rim_hi='#ff3ea5', rim_op=0.95,
        road='#0c0618', water=[('0', '#1d0a33'), ('1', '#07040f')],
        trail_tail=['#ff4fb0', '#b48cff', '#ff7ac6', '#d9b8ff'], trail_head='#ffffff',
        beam='#ffb3e0', beam_op=0.30, beacon='#ff3ea5', beacon_core='#ffffff',
        sweep='#ffc8ec', sweep_op=0.26, refl_op=0.55, refl_blur=(1.1, 0.6), refl_win=(0, 1, 2, 3), shimmer='#ff8fd0',
    ),
    'light': dict(
        card='#efe4fb', border='#2a114524',
        sky=[('0', '#b9a6ee'), ('0.4', '#dcbcf0'), ('0.75', '#ffb6d4'), ('1', '#ffc2a8')],
        glow='#ff5fb4', glow_op=0.38, glow2='#a979ff', glow2_op=0.22,
        orb=[('0', '#fff6ee'), ('0.4', '#ffc4dc'), ('0.8', '#ff7fb8'), ('1', '#ff5aa6')],
        orb_at=(150, 150, 30), halo='#ffd0e6', halo_op=0.55, stars=22,
        far='#b78fdb', far_op=1.0, far_win='#fff3fa', far_win_op=0.55,
        mid=('#8a63bd', '#6c479d'), mid_win='#ffe3f3', mid_win_op=0.55, haze='#ffc2e1', haze_op=0.45, ripple=0.8, bloom=0.7,
        front=('#562a82', '#26103f'), side='#1d0b33', roof='#7a45b3',
        crown=('#57298a', '#2c1249'),
        unlit='#3a2160', unlit_op=0.9,
        lv=['#b48ae6', '#e2b8ff', '#ff9fd4', '#fff4fb'],
        rim_lo='#a06bff', rim_hi='#ff4fae', rim_op=0.9,
        road='#2a1243', water=[('0', '#cbb3ee'), ('1', '#eadff9')],
        trail_tail=['#ff4fb0', '#9b6bff', '#ff7ac6', '#c08cff'], trail_head='#ffffff',
        beam='#ff8fc8', beam_op=0.30, beacon='#ff2f9a', beacon_core='#ffffff',
        sweep='#ffffff', sweep_op=0.22, refl_op=0.28, refl_blur=(1.6, 1.3), refl_win=(3,), shimmer='#ffffff',
    ),
}


def h01(*parts):
    """Deterministic pseudo random number in [0, 1) from any key."""
    d = hashlib.sha1('|'.join(str(p) for p in parts).encode()).hexdigest()
    return int(d[:8], 16) / 0xFFFFFFFF


def mix(a, b, t):
    a = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return '#' + ''.join('%02x' % round(x + (y - x) * t) for x, y in zip(a, b))


def f(x):
    s = ('%.2f' % x).rstrip('0').rstrip('.')
    return '0' if s == '-0' else s


def fetch_calendar(user, token):
    body = json.dumps({'query': QUERY, 'variables': {'login': user}}).encode()
    req = urllib.request.Request('https://api.github.com/graphql', data=body, headers={
        'Authorization': 'bearer ' + token, 'User-Agent': 'neon-skyline'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def weeks_from(resp):
    weeks = resp['data']['user']['contributionsCollection']['contributionCalendar']['weeks']
    out = []
    for wk in weeks:
        days = [(d['date'], d['contributionCount']) for d in wk['contributionDays']]
        out.append(days)
    return out


def merge_counts(weeks, merges):
    starts = [dt.date.fromisoformat(w[0][0]) for w in weeks]
    counts = [0] * len(weeks)
    for m in merges:
        d = dt.date.fromisoformat(m[:10])
        for i in range(len(starts) - 1, -1, -1):
            if d >= starts[i]:
                if (d - starts[i]).days < 7:
                    counts[i] += 1
                break
    return counts


def layout(weeks):
    totals = [sum(c for _, c in w) for w in weeks]
    top = max(max(totals), 1)
    n = len(weeks)
    margin_l, margin_r = 20, 44
    slot = (W - margin_l - margin_r) / n
    nz = sorted(c for w in weeks for _, c in w if c > 0)

    def q(p):
        return nz[min(len(nz) - 1, int(p * len(nz)))] if nz else 1
    cuts = (q(0.25), q(0.5), q(0.75))

    def level(c):
        if c <= 0:
            return -1
        return sum(c > x for x in cuts)

    blds = []
    for i, w in enumerate(weeks):
        key = w[0][0]
        t = math.sqrt(totals[i] / top)
        if totals[i]:
            hgt = MIN_H + (MAX_H - MIN_H) * t
        else:
            hgt = 7.5 + 4.5 * h01(key, 'z')   # quiet weeks: always lower than any active week
        width = min(slot - 2.6, 9.6 + 2.8 * h01(key, 'w'))
        x = margin_l + i * slot + (slot - width - 2.6) * 0.5
        back = h01(key, 'b') < 0.34 and i < n - 2
        blds.append(dict(i=i, key=key, x=x, w=width, h=hgt, t=t, back=back,
                         days=[level(c) for _, c in w]))
    return blds


def building_svg(b, th, out_front, out_lit, out_glow, out_rim, out_unlit):
    """Append svg strings for one building into the given lists."""
    sx = 0.55 if b['back'] else 0.0
    x = b['x'] + DX * sx
    base = BASE - DY * sx
    w, hgt = b['w'], b['h']
    y = base - hgt
    crown = hgt > 92
    ch = hgt * 0.17 if crown else 0
    ci = 1.8 if crown else 0
    rim = mix(th['rim_lo'], th['rim_hi'], min(1, b['t'] * 1.15))
    gid = 'g%s' % ('t' if crown else 'n')

    parts = []
    # side face and roof of the main block
    yb = y + ch
    parts.append('<path d="M%s %sl%s -%sV%sl-%s %sz" fill="%s"/>' % (
        f(x + w), f(yb), f(DX), f(DY), f(base - DY), f(DX), f(DY), th['side']))
    parts.append('<rect x="%s" y="%s" width="%s" height="%s" fill="url(#front)"/>' % (
        f(x), f(yb), f(w), f(base - yb)))
    if crown:
        cx, cw = x + ci, w - 2 * ci
        parts.append('<path d="M%s %sl%s -%sh%sl-%s %sz" fill="%s"/>' % (
            f(x), f(yb), f(DX), f(DY), f(w), f(DX), f(DY), th['roof']))
        parts.append('<path d="M%s %sl%s -%sV%sl-%s %sz" fill="%s"/>' % (
            f(cx + cw), f(y), f(DX), f(DY), f(yb - DY), f(DX), f(DY), th['side']))
        parts.append('<rect x="%s" y="%s" width="%s" height="%s" fill="url(#crown)"/>' % (
            f(cx), f(y), f(cw), f(ch)))
        rx, rw = cx, cw
    else:
        rx, rw = x, w
    parts.append('<path d="M%s %sl%s -%sh%sl-%s %sz" fill="%s"/>' % (
        f(rx), f(y), f(DX), f(DY), f(rw), f(DX), f(DY), th['roof']))
    out_front.append(''.join(parts))

    # neon rim on the roof edge plus a fading corner line
    rim_d = 'M%s %sh%sl%s -%s' % (f(rx), f(y), f(rw), f(DX), f(DY))
    if b['t'] > 0.05:
        out_rim.append('<path d="%s" stroke="%s"/>' % (rim_d, rim))
        out_rim.append('<rect x="%s" y="%s" width=".8" height="%s" fill="url(#edge)" '
                       'style="color:%s"/>' % (f(rx + rw - 0.8), f(y), f(min(hgt, 60)), rim))
    else:
        out_rim.append('<path d="%s" stroke="%s" stroke-opacity=".45"/>' % (rim_d, rim))

    # windows: floors bottom to top split in seven bands, Sunday at the bottom
    pitch, wh = 4.4, 2.3
    cols = 2 if w >= 10.4 else 1
    ww = 2.4
    gap = (w - cols * ww) / (cols + 1)
    top_win = yb + 3.2
    floors = max(1, int((base - 3.0 - top_win) / pitch))
    for fl in range(floors):
        wy = base - 3.0 - (fl + 1) * pitch + (pitch - wh)
        day = min(6, int(fl * 7 / floors))
        lv = b['days'][day] if day < len(b['days']) else -1
        for c in range(cols):
            wx = x + gap + c * (ww + gap)
            r = h01(b['key'], fl, c)
            rect = '<rect x="%s" y="%s" width="%s" height="%s"/>' % (f(wx), f(wy), f(ww), f(wh))
            if lv >= 0 and r > 0.12:
                tw = 0
                if r > 0.80:
                    tw = 1 + int(h01(b['key'], fl, c, 'tw') * 5)
                out_lit.append((lv, tw, rect))
                if lv >= 1:
                    out_glow.append((lv, rect))
            else:
                out_unlit.append(rect)
    if crown and b['t'] > 0.4:
        # a lit band under the crown
        out_lit.append((2, 0, '<rect x="%s" y="%s" width="%s" height=".8"/>' % (
            f(rx + 1.6), f(y + 2.6), f(rw - 3.2))))
    return dict(x=x, w=w, y=y, rx=rx, rw=rw, base=base)


def render(weeks, merges, theme):
    th = THEMES[theme]
    blds = layout(weeks)
    mc = merge_counts(weeks, merges)
    o = []
    a = o.append
    a('<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
      'width="%d" height="%d" viewBox="0 0 %d %d" fill="none">' % (W, H, W, H))

    # ---------- styles ----------
    a('<style>'
      '.tw1{animation:tw 4.3s ease-in-out infinite}'
      '.tw2{animation:tw 6.1s ease-in-out -2.2s infinite}'
      '.tw3{animation:tw 7.7s ease-in-out -5.1s infinite}'
      '.tw4{animation:tw2 9.4s steps(1,end) -3.3s infinite}'
      '.tw5{animation:tw2 12.6s steps(1,end) -8.8s infinite}'
      '@keyframes tw{0%,100%{opacity:1}50%{opacity:.28}}'
      '@keyframes tw2{0%,100%{opacity:1}38%{opacity:.08}71%{opacity:1}}'
      '.st{animation:st 5.5s ease-in-out infinite}'
      '.st2{animation:st 8.2s ease-in-out -3s infinite}'
      '@keyframes st{0%,100%{opacity:.9}50%{opacity:.2}}'
      '.pulse{transform-box:fill-box;transform-origin:center;animation:pulse 2.4s ease-out infinite}'
      '@keyframes pulse{0%{transform:scale(.45);opacity:.95}70%{opacity:0}100%{transform:scale(2.3);opacity:0}}'
      '.core{animation:core 2.4s ease-in-out infinite}'
      '@keyframes core{0%,100%{opacity:1}55%{opacity:.55}}'
      '.beam{animation:beam 14s ease-in-out infinite}'
      '.beam2{animation:beam 17s ease-in-out -6s infinite reverse}'
      '@keyframes beam{0%,100%{transform:rotate(-14deg)}50%{transform:rotate(16deg)}}'
      '.sweep{animation:sweep 11s cubic-bezier(.45,0,.55,1) infinite}'
      '@keyframes sweep{0%{transform:translateX(-260px)}62%,100%{transform:translateX(1000px)}}'
      '.lane{animation:lane 5.6s linear infinite}'
      '.lane.b{animation-duration:7.9s}'
      '.lane.c{animation-duration:4.4s}'
      '.lane.d{animation-duration:9.8s}'
            '@keyframes lane{from{stroke-dashoffset:0}to{stroke-dashoffset:-300}}'
      '.shim{animation:shim 6s ease-in-out infinite}'
      '.shim.b{animation-duration:8.5s;animation-delay:-4s}'
      '@keyframes shim{0%,100%{opacity:.15;transform:translateX(0)}50%{opacity:.7;transform:translateX(5px)}}'
      '.wob{animation:wob 7s ease-in-out infinite}'
      '@keyframes wob{0%,100%{transform:translateX(0)}50%{transform:translateX(1.2px)}}'
      '@media (prefers-reduced-motion:reduce){*{animation:none!important}.sweep{opacity:0}.shim{opacity:.4}'
      '.beam{transform:rotate(-9deg)}.beam2{transform:rotate(11deg)}.pulse{opacity:.6}}'
      '</style>')

    # ---------- defs ----------
    a('<defs>')
    a('<clipPath id="card"><rect width="%d" height="%d" rx="14"/></clipPath>' % (W, H))
    a('<linearGradient id="sky" x1="0" y1="0" x2="0" y2="%d" gradientUnits="userSpaceOnUse">' % BASE)
    for s, c in th['sky']:
        a('<stop offset="%s" stop-color="%s"/>' % (s, c))
    a('</linearGradient>')
    a('<radialGradient id="hglow" cx="0.5" cy="1" r="0.5" gradientTransform="matrix(1 0 0 .32 0 .68)">'
      '<stop offset="0" stop-color="%s" stop-opacity="%s"/>'
      '<stop offset="1" stop-color="%s" stop-opacity="0"/></radialGradient>' % (th['glow'], th['glow_op'], th['glow']))
    a('<radialGradient id="hglow2" cx="0.5" cy="0.5" r="0.5">'
      '<stop offset="0" stop-color="%s" stop-opacity="%s"/>'
      '<stop offset="1" stop-color="%s" stop-opacity="0"/></radialGradient>' % (th['glow2'], th['glow2_op'], th['glow2']))
    a('<radialGradient id="orb" cx="0.42" cy="0.38" r="0.62">')
    for s, c in th['orb']:
        a('<stop offset="%s" stop-color="%s"/>' % (s, c))
    a('</radialGradient>')
    a('<radialGradient id="halo"><stop offset="0" stop-color="%s" stop-opacity="%s"/>'
      '<stop offset="1" stop-color="%s" stop-opacity="0"/></radialGradient>' % (th['halo'], th['halo_op'], th['halo']))
    a('<linearGradient id="front" x1="0" y1="0" x2="0" y2="1">'
      '<stop offset="0" stop-color="%s"/><stop offset="1" stop-color="%s"/></linearGradient>' % th['front'])
    a('<linearGradient id="midg" x1="0" y1="0" x2="0" y2="1">'
      '<stop offset="0" stop-color="%s"/><stop offset="1" stop-color="%s"/></linearGradient>' % th['mid'])
    a('<linearGradient id="midside" x1="0" y1="0" x2="0" y2="1">'
      '<stop offset="0" stop-color="%s"/><stop offset="1" stop-color="%s"/></linearGradient>' % (th['mid'][1], th['mid'][1]))
    a('<linearGradient id="crown" x1="0" y1="0" x2="0" y2="1">'
      '<stop offset="0" stop-color="%s"/><stop offset="1" stop-color="%s"/></linearGradient>' % th['crown'])
    a('<linearGradient id="edge" x1="0" y1="0" x2="0" y2="1">'
      '<stop offset="0" stop-color="currentColor" stop-opacity=".9"/>'
      '<stop offset="1" stop-color="currentColor" stop-opacity="0"/></linearGradient>')
    a('<linearGradient id="haze" x1="0" y1="0" x2="0" y2="1">'
      '<stop offset="0" stop-color="%s" stop-opacity="0"/>'
      '<stop offset="1" stop-color="%s" stop-opacity="%s"/></linearGradient>' % (th['haze'], th['haze'], th['haze_op']))
    a('<linearGradient id="water" x1="0" y1="0" x2="0" y2="1">')
    for s, c in th['water']:
        a('<stop offset="%s" stop-color="%s"/>' % (s, c))
    a('</linearGradient>')
    a('<linearGradient id="beamg" x1="0" y1="1" x2="0" y2="0">'
      '<stop offset="0" stop-color="%s" stop-opacity="%s"/>'
      '<stop offset="1" stop-color="%s" stop-opacity="0"/></linearGradient>' % (th['beam'], th['beam_op'], th['beam']))
    a('<radialGradient id="bhalo"><stop offset="0" stop-color="%s" stop-opacity=".9"/>'
      '<stop offset="1" stop-color="%s" stop-opacity="0"/></radialGradient>' % (th['beacon'], th['beacon']))
    a('<linearGradient id="sweepg" x1="0" y1="0" x2="1" y2="0">'
      '<stop offset="0" stop-color="%s" stop-opacity="0"/>'
      '<stop offset=".5" stop-color="%s" stop-opacity="%s"/>'
      '<stop offset="1" stop-color="%s" stop-opacity="0"/></linearGradient>' % (
          th['sweep'], th['sweep'], th['sweep_op'], th['sweep']))
    a('<linearGradient id="fade" x1="0" y1="%d" x2="0" y2="%d" gradientUnits="userSpaceOnUse">'
      '<stop offset="0" stop-color="#fff" stop-opacity="1"/>'
      '<stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>' % (WATER, H))
    a('<pattern id="ripple" width="12" height="3" patternUnits="userSpaceOnUse">'
      '<rect width="12" height="1.7" fill="#fff"/><rect y="1.7" width="7" height="1.3" fill="#fff" fill-opacity="%s"/></pattern>' % th['ripple'])
    a('<mask id="reflm" maskUnits="userSpaceOnUse" x="0" y="%d" width="%d" height="%d">'
      '<rect x="0" y="%d" width="%d" height="%d" fill="url(#ripple)"/></mask>' % (WATER, W, H - WATER, WATER, W, H - WATER))
    a('<mask id="fadem" maskUnits="userSpaceOnUse" x="0" y="%d" width="%d" height="%d">'
      '<rect x="0" y="%d" width="%d" height="%d" fill="url(#fade)"/></mask>' % (WATER, W, H - WATER, WATER, W, H - WATER))
    a('<filter id="beamblur" x="-50%" y="-10%" width="200%" height="120%"><feGaussianBlur stdDeviation="2.4"/></filter>')
    a('<filter id="blur3" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="3"/></filter>')
    a('<filter id="blur1" x="-20%" y="-50%" width="140%" height="200%"><feGaussianBlur stdDeviation="1.1"/></filter>')
    a('<filter id="rblur" x="-5%%" y="-5%%" width="110%%" height="110%%"><feGaussianBlur stdDeviation="%s %s"/></filter>' % th['refl_blur'])
    a('<filter id="soft" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="6"/></filter>')

    # ---------- city geometry (built once, reused for the reflection) ----------
    front, lit, glow, rim, unlit = [], [], [], [], []
    geo = {}
    order = [b for b in blds if b['back']] + [b for b in blds if not b['back']]
    for b in order:
        geo[b['i']] = building_svg(b, th, front, lit, glow, rim, unlit)

    a('<g id="bodies">%s</g>' % ''.join(front))
    a('<g id="unlit" fill="%s" fill-opacity="%s">%s</g>' % (th['unlit'], th['unlit_op'], ''.join(unlit)))
    for lv in range(4):
        rects = ''.join(r for l, t, r in lit if l == lv)
        a('<g id="L%d">%s</g>' % (lv, rects))
    a('<g id="rims" fill="none" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round">%s</g>' % ''.join(rim))
    # clip of all fronts for the light sweep
    a('<clipPath id="fronts">')
    for b in blds:
        g = geo[b['i']]
        a('<rect x="%s" y="%s" width="%s" height="%s"/>' % (f(g['x']), f(g['y']), f(g['w'] + DX), f(g['base'] - g['y'])))
    a('</clipPath>')
    a('</defs>')

    a('<g clip-path="url(#card)">')
    # sky
    a('<rect width="%d" height="%d" fill="%s"/>' % (W, H, th['card']))
    a('<rect width="%d" height="%d" fill="url(#sky)"/>' % (W, BASE))
    # stars
    if th['stars']:
        st = []
        for k in range(th['stars']):
            sx = h01('sx', k) * W
            sy = 6 + h01('sy', k) ** 1.6 * (140 if theme == 'dark' else 60)
            r = 0.35 + h01('sr', k) ** 3 * 0.9
            cls = ''
            if h01('sc', k) > 0.72:
                cls = ' class="%s"' % ('st' if k % 2 else 'st2')
            col = '#ffffff' if h01('scol', k) > 0.4 else '#e3c8ff'
            st.append('<circle cx="%s" cy="%s" r="%s" fill="%s"%s/>' % (f(sx), f(sy), f(r), col, cls))
        a('<g opacity=".9">%s</g>' % ''.join(st))
    # glows on the horizon
    a('<rect x="-40" y="%d" width="%d" height="%d" fill="url(#hglow)"/>' % (BASE - 150, W + 80, 170))
    a('<ellipse cx="640" cy="%d" rx="250" ry="120" fill="url(#hglow2)"/>' % (BASE - 70))
    # orb
    ox, oy, orr = th['orb_at']
    a('<circle cx="%d" cy="%d" r="%d" fill="url(#halo)"/>' % (ox, oy, orr * 4))
    a('<circle cx="%d" cy="%d" r="%d" fill="url(#orb)"/>' % (ox, oy, orr))

    # far skyline, procedural and seeded so it is stable between runs
    far, farw = [], []
    xx = -4.0
    k = 0
    while xx < W:
        bw = 9 + h01('fw', k) * 16
        hh = 18 + h01('fh', k) ** 1.4 * 62
        if 560 < xx < 800:
            hh *= 1.25
        if xx < ox + orr and xx + bw > ox - orr:
            # keep the sun's column low so it sets behind a level roofline, not a tower
            hh = min(hh, BASE - 3 - (oy + orr * 0.3))
        far.append('<rect x="%s" y="%s" width="%s" height="%s"/>' % (f(xx), f(BASE - 3 - hh), f(bw + 0.4), f(hh + 3)))
        if h01('fs', k) > 0.6:
            far.append('<rect x="%s" y="%s" width="1" height="7"/>' % (f(xx + bw * 0.5), f(BASE - 10 - hh)))
        for j in range(int(hh / 6)):
            if h01('fwn', k, j) > 0.78:
                farw.append('<rect x="%s" y="%s" width="1.4" height="1.4"/>' % (
                    f(xx + 2 + h01('fwx', k, j) * (bw - 4)), f(BASE - 6 - j * 6)))
        xx += bw - 1.5
        k += 1
    a('<g fill="%s" fill-opacity="%s">%s</g>' % (th['far'], th['far_op'], ''.join(far)))
    a('<g fill="%s" fill-opacity="%s">%s</g>' % (th['far_win'], th['far_win_op'], ''.join(farw)))
    a('<rect y="%d" width="%d" height="%d" fill="url(#haze)"/>' % (BASE - 70, W, 70))

    # mid layer: unnamed towers set back behind the data row so the gaps read as city
    mid, midw = [], []
    for j in range(len(blds) - 1):
        b0, b1 = blds[j], blds[j + 1]
        top = max(b0['h'], b1['h'])
        if top < 24:
            continue
        mh = top * (0.5 + 0.38 * h01(b0['key'], 'mh'))
        mw = 7 + 5 * h01(b0['key'], 'mw')
        mx = (b0['x'] + b0['w'] + b1['x']) / 2 - mw / 2 + DX * 1.3
        mb = BASE - DY * 1.3
        my = mb - mh
        mid.append('<path d="M%s %sl%s -%sV%sl-%s %sz" fill="url(#midside)"/>' % (
            f(mx + mw), f(my), f(DX), f(DY), f(mb - DY), f(DX), f(DY)))
        mid.append('<rect x="%s" y="%s" width="%s" height="%s" fill="url(#midg)"/>' % (f(mx), f(my), f(mw), f(mh)))
        for fl in range(int((mh - 6) / 4.4)):
            if h01(b0['key'], 'mwn', fl) > 0.8:
                midw.append('<rect x="%s" y="%s" width="1.6" height="1.6"/>' % (
                    f(mx + 1.5 + h01(b0['key'], 'mwx', fl) * (mw - 4.5)), f(mb - 5 - fl * 4.4)))
    a('<g>%s</g>' % ''.join(mid))
    a('<g fill="%s" fill-opacity="%s">%s</g>' % (th['mid_win'], th['mid_win_op'], ''.join(midw)))

    # searchlight beams behind the beacon towers
    beacons = []
    for b in blds:
        if mc[b['i']]:
            g = geo[b['i']]
            bx = g['rx'] + g['rw'] / 2 + DX / 2
            by = g['y'] - DY / 2 - 15
            beacons.append((bx, by, mc[b['i']], g))
    for n, (bx, by, cnt, g) in enumerate(beacons):
        cls = 'beam' if n % 2 == 0 else 'beam2'
        spread = 34 + min(cnt, 20)
        a('<g class="%s" style="transform-origin:%spx %spx"><path filter="url(#beamblur)" d="M%s %sL%s %sL%s %sL%s %sZ" fill="url(#beamg)"/></g>' % (
            cls, f(bx), f(by), f(bx - 1.5), f(by), f(bx - spread), f(by - 240), f(bx + spread), f(by - 240), f(bx + 1.5), f(by)))

    # soft bloom of the lit windows (static, so it is rasterised once)
    gl = ''.join(r for l, r in glow)
    a('<g filter="url(#blur3)" opacity="%s"><g fill="%s">%s</g>'
      '<use href="#rims" xlink:href="#rims"/></g>' % (th['bloom'], th['lv'][2], gl))

    # the city itself
    a('<use href="#bodies" xlink:href="#bodies"/>')
    a('<use href="#unlit" xlink:href="#unlit"/>')
    for lv in range(4):
        col = th['lv'][lv]
        steady = ''.join(r for l, t, r in lit if l == lv and t == 0)
        a('<g fill="%s">%s</g>' % (col, steady))
        for t in range(1, 6):
            rs = ''.join(r for l, tt, r in lit if l == lv and tt == t)
            if rs:
                a('<g class="tw%d" fill="%s">%s</g>' % (t, col, rs))
    a('<use href="#rims" xlink:href="#rims" opacity="%s"/>' % th['rim_op'])
    # light sweep across the facades
    a('<g clip-path="url(#fronts)"><g transform="skewX(-18)"><rect class="sweep" x="0" y="20" width="150" height="%d" '
      'fill="url(#sweepg)"/></g></g>' % (BASE - 20))

    # beacons
    for bx, by, cnt, g in beacons:
        top = g['y'] - DY / 2
        a('<path d="M%s %sV%s" stroke="%s" stroke-width=".9"/>' % (f(bx), f(top), f(by + 2), th['roof']))
        r = 5 + min(cnt, 25) * 0.25
        a('<circle class="pulse" cx="%s" cy="%s" r="%s" fill="url(#bhalo)"/>' % (f(bx), f(by), f(r)))
        a('<circle cx="%s" cy="%s" r="%s" fill="url(#bhalo)" opacity=".7"/>' % (f(bx), f(by), f(r * 0.7)))
        a('<circle class="core" cx="%s" cy="%s" r="1.7" fill="%s"/>' % (f(bx), f(by), th['beacon_core']))

    # waterfront road with long exposure light trails
    a('<rect y="%d" width="%d" height="%d" fill="%s"/>' % (BASE, W, ROAD, th['road']))
    a('<rect y="%d" width="%d" height="%d" fill="url(#water)"/>' % (WATER, W, H - WATER))

    # reflection
    a('<g mask="url(#fadem)" opacity="%s"><g mask="url(#reflm)"><g class="wob">'
      '<g transform="translate(0 %d) scale(1 -1)" filter="url(#rblur)">' % (th['refl_op'], 2 * WATER - 2))
    a('<use href="#bodies" xlink:href="#bodies"/>')
    for lv in th['refl_win']:
        a('<use href="#L%d" xlink:href="#L%d" fill="%s"/>' % (lv, lv, th['lv'][lv]))
    a('<use href="#rims" xlink:href="#rims"/>')
    a('</g></g></g></g>')
    # horizon glow on the water
    a('<ellipse cx="620" cy="%d" rx="300" ry="20" fill="url(#hglow2)" opacity=".8"/>' % (WATER + 6))
    # the orb's glow broken up on the water
    orbr = []
    for k in range(9):
        yy = WATER + 6 + k * 7 + h01('oy', k) * 3
        ln = (orr * 1.5) * (1 - k / 11) * (0.6 + 0.4 * h01('ol', k))
        orbr.append('<rect class="shim%s" x="%s" y="%s" width="%s" height="1.3" rx=".65"/>' % (
            ' b' if k % 2 else '', f(ox - ln / 2), f(yy), f(ln)))
    a('<g fill="%s">%s</g>' % (th['halo'], ''.join(orbr)))
    # water shimmer
    sh = []
    for k in range(46):
        sx = h01('wx', k) * W
        sy = WATER + 4 + h01('wy', k) ** 1.3 * (H - WATER - 10)
        ln = 6 + h01('wl', k) * 22
        cls = 'shim' + (' b' if k % 2 else '')
        sh.append('<rect class="%s" x="%s" y="%s" width="%s" height=".8" rx=".4"/>' % (cls, f(sx), f(sy), f(ln)))
    a('<g fill="%s">%s</g>' % (th['shimmer'], ''.join(sh)))

    # road trails: a dim tail with a bright head, looping with period 300
    lanes = [(BASE + 1.3, 'a', 0, False, 0.0), (BASE + 2.4, 'c', 1, True, -1.7),
             (BASE + 3.4, 'b', 2, False, -3.1), (BASE + 4.2, 'd', 3, True, -6.2)]
    tr = []
    for y, cls, ci, rev, delay in lanes:
        # path direction decides travel direction; reversed lanes run right to left
        d = 'M%d %sH%d' % ((W + 10, f(y), -10) if rev else (-10, f(y), W + 10))
        st = ' style="animation-delay:%ss"' % delay if delay else ''
        tr.append('<path class="lane %s"%s d="%s" stroke="%s" stroke-width="1.1" stroke-dasharray="70 230" '
                  'stroke-linecap="round" opacity=".8"/>' % (cls, st, d, th['trail_tail'][ci]))
        tr.append('<path class="lane %s"%s d="%s" stroke="%s" stroke-width="1.3" stroke-dasharray="0 66 4 230" '
                  'stroke-linecap="round"/>' % (cls, st, d, th['trail_head']))
    a('<g filter="url(#blur1)" opacity=".9">%s</g>' % ''.join(tr))
    a('<g>%s</g>' % ''.join(tr))
    # thin neon waterline
    a('<rect y="%s" width="%d" height=".7" fill="%s" opacity=".55"/>' % (f(WATER - 0.35), W, th['rim_hi']))
    a('</g>')
    a('<rect x=".5" y=".5" width="%d" height="%d" rx="13.5" stroke="%s"/>' % (W - 1, H - 1, th['border']))
    a('</svg>')
    return ''.join(o)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='auraseb')
    ap.add_argument('--out', default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument('--merges', help='JSON list of ISO merge dates')
    ap.add_argument('--calendar', help='saved GraphQL response JSON')
    a = ap.parse_args()
    if a.calendar:
        with open(a.calendar) as fh:
            resp = json.load(fh)
    else:
        token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
        if not token:
            raise SystemExit('GH_TOKEN is not set')
        resp = fetch_calendar(a.user, token)
    weeks = weeks_from(resp)
    merges = []
    if a.merges:
        with open(a.merges) as fh:
            merges = json.load(fh)
    for theme in ('dark', 'light'):
        svg = render(weeks, merges, theme)
        with open(os.path.join(a.out, theme + '.svg'), 'w') as fh:
            fh.write(svg)
        print(theme, len(svg.encode()), 'bytes')


if __name__ == '__main__':
    main()
