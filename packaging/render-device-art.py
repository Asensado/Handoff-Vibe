#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Asensado
"""Render original, logo-free device illustrations. No manufacturer photos."""
from pathlib import Path
import json
import subprocess

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / 'assets/illustrations'
ART.mkdir(parents=True, exist_ok=True)
DEFS = '''<defs><linearGradient id="body" x1="0" x2="1" y1="0" y2="1"><stop stop-color="#fafbfc"/><stop offset=".5" stop-color="#e8edf1"/><stop offset="1" stop-color="#9eabb8"/></linearGradient><linearGradient id="dark" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#566779"/><stop offset="1" stop-color="#1c2938"/></linearGradient></defs>'''


def stem(pro=False, short=False):
    length = 95 if short else 150
    tip = '<ellipse cx="52" cy="45" rx="26" ry="21" fill="#eef2f5" stroke="#aab7c2" stroke-width="3"/>' if pro else ''
    return f'''<g transform="rotate(-13 64 100)"><rect x="67" y="54" width="32" height="{length}" rx="16" fill="url(#body)" stroke="#9ba9b6" stroke-width="3"/>{tip}<ellipse cx="77" cy="40" rx="48" ry="34" fill="url(#body)" stroke="#aab6c0" stroke-width="3"/><ellipse cx="47" cy="37" rx="14" ry="20" fill="#293848"/><path d="M93 24l15 6" stroke="#758b9f" stroke-width="5" stroke-linecap="round"/></g>'''


def sport(hook=False, wing=False):
    extra = '<path d="M99 57C135-22 28-32 9 24c-10 27 0 69 14 89" fill="none" stroke="url(#dark)" stroke-width="22" stroke-linecap="round"/>' if hook else ''
    extra += '<path d="M85 48C130 8 119-14 94 1L60 38z" fill="url(#dark)" stroke="#72879b" stroke-width="3"/>' if wing else ''
    return f'''{extra}<ellipse cx="30" cy="83" rx="28" ry="20" fill="#242f3e"/><rect x="34" y="37" width="75" height="93" rx="35" fill="url(#dark)" stroke="#7f91a3" stroke-width="3"/><path d="M56 71h31M56 80h31M56 89h31" stroke="#a2b4c4" stroke-width="3" stroke-linecap="round"/>'''


def headset(round_cups=False):
    cups = '<ellipse cx="138" cy="308" rx="49" ry="75"/><ellipse cx="374" cy="308" rx="49" ry="75"/>' if round_cups else '<rect x="82" y="235" width="112" height="160" rx="43"/><rect x="318" y="235" width="112" height="160" rx="43"/>'
    return f'''<path d="M125 275V196c0-148 262-148 262 0v79" fill="none" stroke="#61758a" stroke-width="29" stroke-linecap="round"/><path d="M126 220v-24c0-144 260-144 260 0v24" fill="none" stroke="url(#body)" stroke-width="17" stroke-linecap="round"/><g fill="url(#body)" stroke="#8193a4" stroke-width="4">{cups}</g><path d="M110 267v98M402 267v98" stroke="#a9b8c5" stroke-width="8" stroke-linecap="round"/>'''


models = {
    'airpods2': ('AirPods 2', stem()),
    'airpods3': ('AirPods 3', stem(short=True)),
    'airpods4': ('AirPods 4', stem(short=True)),
    'airpodspro': ('AirPods Pro', stem(pro=True, short=True)),
    'airpodspro2': ('AirPods Pro 2', stem(pro=True, short=True)),
    'beatsfitpro': ('Beats Fit Pro', sport(wing=True)),
    'powerbeatsfit': ('Powerbeats Fit', sport(wing=True)),
    'powerbeatspro': ('Powerbeats Pro', sport(hook=True)),
    'powerbeatspro2': ('Powerbeats Pro 2', sport(hook=True)),
    'airpodsmax': ('AirPods Max', headset()),
    'solopro': ('Beats Solo Pro', headset(round_cups=True)),
}
manifest = []
for key, (name, shape) in models.items():
    if key not in ('airpodsmax', 'solopro'):
        shape = f'<g transform="translate(65 130) scale(1.35)">{shape}</g><g transform="translate(445 110) scale(-1.35 1.35)">{shape}</g>'
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512"><!-- SPDX-License-Identifier: GPL-3.0-or-later; Copyright 2026 Asensado. Original generic illustration, not a manufacturer photograph. --><title>{name}: original device illustration</title>{DEFS}{shape}</svg>'''
    path = ART / (key + '.svg')
    path.write_text(svg)
    subprocess.run(['rsvg-convert', '-o', str(ROOT / 'assets' / (key + '.png')), str(path)], check=True)
    manifest.append(dict(model=key, source='illustrations/' + key + '.svg', creator='Asensado', license='GPL-3.0-or-later', kind='original illustration'))
(ROOT / 'assets/sources.json').write_text(json.dumps(manifest, indent=2) + '\n')
