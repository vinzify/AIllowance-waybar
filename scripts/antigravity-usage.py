#!/usr/bin/env python3
"""Waybar quota display using Antigravity's read-only CLI command reports."""
import datetime as dt
import fcntl
import html
import json
import math
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from allowance_style import chip, heading, tooltip_markup

SCRIPT = Path(__file__).resolve()
CACHE = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache'))) / 'aillowance/antigravity-usage.json'
CLI = Path(os.environ.get('AILLOWANCE_AGY_BIN') or shutil.which('agy') or str(Path.home() / '.local/bin/agy'))
REFRESH_SECONDS = 300
STALE_SECONDS = 900


def read_cache():
    try:
        result = json.loads(CACHE.read_text())
        return result if isinstance(result, dict) else {}
    except (OSError, ValueError):
        return {}


def save_cache(data):
    with tempfile.NamedTemporaryFile(mode='w', dir=CACHE.parent, prefix='.antigravity-', delete=False) as f:
        json.dump(data, f)
        name = f.name
    os.chmod(name, 0o600)
    os.replace(name, CACHE)


def run_cli(arguments, env, cwd):
    with subprocess.Popen([str(CLI), *arguments], cwd=cwd, env=env,
                          stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, start_new_session=True) as proc:
        try:
            out, _ = proc.communicate(timeout=40)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            raise ValueError('timeout')
        if proc.returncode or len(out) > 1024 * 1024:
            raise ValueError('command failed')
        return out


def command_report(command, env, cwd):
    result = json.loads(run_cli(['-p', '/' + command, '--output-format', 'json',
                                 '--log-file', str(Path(cwd) / 'cli.log')], env, cwd))
    if (result.get('status') != 'SUCCESS' or result.get('num_turns') != 0
            or result.get('conversation_id') or result.get('command', {}).get('name') != command):
        raise ValueError('not a read-only command report')
    return result['command']['data']


def normalize_groups(data):
    groups = []
    for group in data.get('groups', []):
        if group.get('disabled') is True or group.get('enabled') is False:
            continue
        buckets = []
        for bucket in group.get('buckets', []):
            if bucket.get('disabled') is True or bucket.get('enabled') is False:
                continue
            value = bucket.get('remaining_fraction')
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                value = None
            buckets.append({'name': str(bucket.get('name') or 'Quota'),
                            'window': str(bucket.get('window') or ''),
                            'remaining': value, 'reset': bucket.get('reset_time')})
        if buckets:
            groups.append({'name': str(group.get('name') or 'Models'),
                           'description': str(group.get('description') or ''), 'buckets': buckets})
    if not groups or not any(b['remaining'] is not None for g in groups for b in g['buckets']):
        raise ValueError('no measured quota')
    return groups


def refresh():
    CACHE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_fd = os.open(CACHE.with_suffix('.lock'), os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(lock_fd, 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        old = read_cache()
        old['attemptedAt'] = time.time()
        save_cache(old)
        try:
            with tempfile.TemporaryDirectory(prefix='waybar-antigravity-') as temporary:
                # Passive polling must never open a browser for an expired login.
                for name in ('xdg-open', 'open', 'sensible-browser'):
                    blocker = Path(temporary) / name
                    blocker.write_text('#!/bin/sh\nexit 1\n')
                    blocker.chmod(0o700)
                env = os.environ.copy()
                env.update(AGY_CLI_DISABLE_AUTO_UPDATE='true', BROWSER=temporary + '/xdg-open',
                           PATH=temporary + ':' + env.get('PATH', '/usr/bin:/bin'))
                version = run_cli(['--version'], env, temporary).decode().strip()
                match = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)(?:[-+].*)?', version)
                if not match or tuple(map(int, match.groups())) < (1, 1, 11):
                    raise ValueError('CLI lacks read-only usage reports')
                groups = normalize_groups(command_report('usage', env, temporary))
                fetched = time.time()
                credits = None
                try:
                    value = command_report('credits', env, temporary).get('remaining_credits')
                    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0:
                        credits = value
                except (OSError, ValueError, KeyError, TypeError):
                    pass
                save_cache({'fetchedAt': fetched, 'attemptedAt': old['attemptedAt'],
                            'groups': groups, 'credits': credits, 'cliVersion': version,
                            'source': 'agy read-only command reports', 'error': None})
        except (OSError, ValueError, KeyError, TypeError):
            old['error'] = 'Unable to refresh. Open agy to check your sign-in, then click here to retry.'
            save_cache(old)


def reset_timestamp(value):
    try:
        return dt.datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
    except (ValueError, TypeError, AttributeError, OverflowError):
        return None


def date_text(timestamp):
    if timestamp is None:
        return 'unavailable'
    return dt.datetime.fromtimestamp(timestamp).astimezone().strftime('%d %b %Y, %H:%M %Z')


def render(data, now=None):
    now = time.time() if now is None else now
    if not data.get('groups'):
        return {'text': ' ' + heading('Gemini') + ' ' + chip('unavailable') + ' ', 'class': 'warn', 'tooltip': 'Antigravity / Gemini\n' +
                (data.get('error') or 'Fetching your quota…') + '\nClick to refresh.'}
    fetched = data.get('fetchedAt') or 0
    age = max(0, now - fetched)
    stale = not fetched or age >= STALE_SECONDS
    lines = ['Gemini / Antigravity', '']
    parts, gemini_values, other_values = [], [], []
    pending = False
    unknown = False
    for group in data['groups']:
        name = group['name']
        is_gemini = 'gemini' in name.lower()
        is_argon = 'argon' in name.lower()
        shared = name.lower() == 'gemini models'
        lines.append(name)
        for bucket in sorted(group['buckets'], key=lambda b: (b['window'] != '5h', b['window'])):
            value = bucket['remaining']
            reset = reset_timestamp(bucket.get('reset'))
            expired = reset is not None and now >= reset
            window = {'5h': '5h', 'weekly': 'Week'}.get(bucket['window'], '?')
            if expired or value is None:
                compact = '?'
                detail = 'awaiting fresh quota after reset' if expired else 'unavailable'
                pending |= expired
                unknown |= value is None
            else:
                percentage = value * 100
                compact = '<1%' if 0 < percentage < .5 else f'{math.floor(percentage + .5)}%'
                detail = f'{percentage:.1f}'.rstrip('0').rstrip('.') + '% remaining'
                (gemini_values if is_gemini else other_values).append(percentage)
            lines.append(f'  {window}: {detail}')
            lines.append(f'  {"Previous reset" if expired else "Resets"}: {date_text(reset)}')
            if is_gemini:
                prefix = window if shared else ('Argon' if is_argon and bucket['window'] == 'weekly' else name + ' ' + window)
                parts.append(chip(prefix + ' ' + compact, None if expired or value is None else percentage, uncertain=stale or bool(data.get('error'))))
        lines.append('')
    if data.get('credits') is not None:
        lines.extend([f'AI credits: {data["credits"]:g}', ''])
        credits = data['credits']
        parts.append(chip((f'{credits / 1000:.1f}k' if credits >= 1000 else f'{credits:g}') + ' credits', balance=credits, uncertain=stale or bool(data.get('error'))))
    else:
        lines.extend(['AI credit balance unavailable', ''])
    values = gemini_values or other_values
    minimum = min(values, default=100)
    severity = 'hot' if minimum <= 15 else ('warn' if minimum <= 40 or stale or pending or unknown or data.get('error') else 'ok')
    lines.append('Checked: ' + date_text(fetched) + (' (just now)' if age < 60 else f' ({int(age // 60)} min ago)'))
    lines.append('Source: Antigravity CLI /usage and /credits')
    lines.append('Refreshes every 5 minutes. Click to refresh now.')
    lines.append('5h / Week = shared Gemini · Argon = separate weekly quota.')
    lines.append('Bar percentages are rounded; tooltip shows one decimal.')
    if stale:
        lines.append('STALE: these are last known values, not a fresh account check.')
    if data.get('error'):
        lines.append(data['error'])
    text = heading('Gemini', min(gemini_values, default=None), uncertain=stale or pending or unknown or bool(data.get('error'))) + '  ' + (' '.join(parts) if parts else chip('unavailable'))
    if stale:
        text += ' ~'
    if data.get('error'):
        text += ' !'
    return {'text': ' ' + text + ' ', 'class': severity,
            'tooltip': tooltip_markup(lines, sections=[g['name'] for g in data['groups']], uncertain=stale or bool(data.get('error')))}


def main():
    if '--refresh' in sys.argv:
        refresh()
        return
    data = read_cache()
    now = time.time()
    if now - data.get('fetchedAt', 0) >= REFRESH_SECONDS and now - data.get('attemptedAt', 0) >= 60:
        subprocess.Popen([sys.executable, str(SCRIPT), '--refresh'], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    print(json.dumps(render(data, now)))


if __name__ == '__main__':
    main()
