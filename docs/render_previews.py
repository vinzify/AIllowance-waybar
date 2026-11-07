#!/usr/bin/env python3
"""Render the real Pango outputs with invented data; optional docs-only dependencies."""
import importlib.util
import os
from pathlib import Path
import sys
import time

import cairo
import gi
gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Pango, PangoCairo

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from samples import NOW, codex_sample, gemini_sample

os.environ['TZ'] = 'UTC'
time.tzset()


def load(file):
    spec = importlib.util.spec_from_file_location(file, ROOT / 'scripts' / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


codex = load('codex-usage-render.py').render(codex_sample(), NOW)
gemini = load('antigravity-usage.py').render(gemini_sample(), NOW)


def color(context, value):
    context.set_source_rgb(*[int(value[i:i+2], 16)/255 for i in (1, 3, 5)])


def text(context, markup, x, y, size=12, width=None):
    layout = PangoCairo.create_layout(context)
    layout.set_font_description(Pango.FontDescription(f'JetBrains Mono {size}'))
    layout.set_markup(markup, -1)
    if width:
        layout.set_width(width * Pango.SCALE)
        layout.set_wrap(Pango.WrapMode.WORD_CHAR)
    layout.set_spacing(3 * Pango.SCALE)
    color(context, '#eeeaf6')
    context.move_to(x, y)
    PangoCairo.show_layout(context, layout)
    return layout.get_pixel_size()


def panel(context, x, y, w, h):
    color(context, '#15111e')
    context.rectangle(x, y, w, h)
    context.fill_preserve()
    color(context, '#383043')
    context.set_line_width(1)
    context.stroke()


def canvas(w, h):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    context = cairo.Context(surface)
    color(context, '#0e0b15')
    context.paint()
    return surface, context


def main():
    surface, context = canvas(1400, 250)
    text(context, '<b>AIllowance</b> <span foreground="#a5a7b5">/ Waybar</span>', 32, 22, 22)
    text(context, 'Your AI allowance, at a glance.', 32, 72, 13)
    panel(context, 24, 116, 1352, 47)
    width, _ = text(context, codex['text'], 40, 129, 11)
    text(context, gemini['text'], 58 + width, 129, 11)
    text(context, '<span foreground="#78dfa5">Healthy &gt;40%</span>   '
         '<span foreground="#ffd078">Watch &gt;15–40%</span>   '
         '<span foreground="#ff858f">Low ≤15%</span>   '
         '<span foreground="#a5a7b5">Grey: stale / unknown</span>', 32, 185, 11)
    text(context, '<span foreground="#a5a7b5">Illustration rendered from the actual modules · invented sample data</span>', 32, 220, 9)
    surface.write_to_png(str(ROOT / 'docs/preview.png'))

    # Measure first so the exported tooltip panels never cut off content.
    _, left_height = text(context, codex['tooltip'], 0, 0, 11, 600)
    _, right_height = text(context, gemini['tooltip'], 0, 0, 11, 600)
    height = max(left_height, right_height) + 140
    surface, context = canvas(1400, height)
    text(context, '<b>Details when you hover.</b>', 32, 24, 21)
    for x, output, content_height in [(24, codex, left_height), (716, gemini, right_height)]:
        panel(context, x, 83, 660, content_height + 32)
        text(context, output['tooltip'], x + 20, 99, 11, 620)
    text(context, '<span foreground="#a5a7b5">Invented sample data · times shown in UTC · appearance follows your Waybar theme</span>', 32, height - 26, 9)
    surface.write_to_png(str(ROOT / 'docs/tooltips.png'))
    print('Rendered docs/preview.png and docs/tooltips.png from sample module output.')


if __name__ == '__main__':
    main()
