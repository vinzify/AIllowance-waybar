"""Shared Pango styling for compact, independently coloured Waybar allowances."""
import html
import re

PALETTE = {
    'ok': ('#78dfa5', '#19352c'),
    'warn': ('#ffd078', '#3c3020'),
    'hot': ('#ff858f', '#40232d'),
    'unknown': ('#a5a7b5', '#292934'),
    'balance': ('#cbb5ff', '#302641'),
}


def level(percent):
    if percent is None:
        return 'unknown'
    return 'hot' if percent <= 15 else ('warn' if percent <= 40 else 'ok')


def chip(text, percent=None, *, balance=None, uncertain=False):
    state = level(percent)
    if balance is not None:
        state = 'balance' if balance > 0 else 'hot'
    if uncertain:
        state = 'unknown'
    fg, bg = PALETTE[state]
    return f'<span foreground="{fg}" background="{bg}"> {html.escape(str(text))} </span>'


def heading(name, percent=None, uncertain=False):
    state = 'unknown' if uncertain else level(percent)
    dot = {'ok': '🟢', 'warn': '🟡', 'hot': '🔴', 'unknown': '⚪'}[state]
    return f'{dot} <span foreground="#eeeaf6" weight="bold">{html.escape(name)}</span>'


LEGEND = ('Percentages show remaining allowance. Green >40% · amber >15–40% · red ≤15%.\n'
          'Grey = stale or unavailable. Credits/resets: lavender >0, red =0; no percentage total reported.')


def tooltip_markup(lines, sections=(), uncertain=False):
    """Style escaped service text, with short sections and readable values."""
    result = []
    for index, raw in enumerate(lines):
        line = raw.strip()
        escaped = html.escape(line)
        if index == 0:
            result.append(f'<span size="large" weight="bold" foreground="#eeeaf6">{escaped}</span>')
            result.append('<span foreground="#a5a7b5">Remaining allowance</span>')
        elif not line:
            if result and result[-1] != '':
                result.append('')
        elif line in sections or line.startswith('Account activity ('):
            title = 'ACCOUNT ACTIVITY' if line.startswith('Account activity (') else line.upper()
            result.append(f'<span weight="bold" foreground="#cbb5ff">{html.escape(title)}</span>')
            if line.startswith('Account activity ('):
                result.append('<span size="small" foreground="#a5a7b5">Service-reported tokens · not a bill</span>')
        elif line.startswith('Rate-limit resets available:'):
            result.append('<span weight="bold" foreground="#cbb5ff">RESET CREDITS</span>')
            result.append(f'Available  <b>{html.escape(line.split(":", 1)[1].strip())}</b>')
        elif line.startswith('AI credits:'):
            result.append('<span weight="bold" foreground="#cbb5ff">CREDITS</span>')
            result.append(f'Balance  <b>{html.escape(line.split(":", 1)[1].strip())}</b>')
        elif line.startswith(('Source:', 'Refreshes', 'Bar percentages', '5h / Week', 'Plan:', 'Checked:')):
            result.append(f'<span size="small" foreground="#a5a7b5">{escaped}</span>')
        elif ': ' in line:
            label, value = line.split(': ', 1)
            value = value.strip()
            match = re.search(r'(\d+(?:\.\d+)?)% remaining', value)
            color = PALETTE[level(float(match.group(1)))][0] if match else '#eeeaf6'
            if uncertain or 'unavailable' in value or 'awaiting' in value:
                color = PALETTE['unknown'][0]
            result.append(f'<span foreground="#a5a7b5">{html.escape(label)}</span>  '
                          f'<span foreground="{color}">{html.escape(value)}</span>')
        else:
            result.append(f'<span foreground="#eeeaf6">{escaped}</span>')
    result.extend(['', '<span size="small" foreground="#a5a7b5">Percentages = remaining · grey = stale / unknown</span>'])
    return '\n'.join(result)
