#!/usr/bin/env python3
"""Render account snapshots without inventing missing or reset quota values."""
import datetime as dt
import decimal
import html
import json
import os
import sys
import time
from allowance_style import chip, heading, tooltip_markup


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = decimal.Decimal(str(value))
        return result if result.is_finite() else None
    except decimal.InvalidOperation:
        return None


def compact(value):
    n = number(value)
    if n is None:
        return 'unavailable'
    for size, suffix in [(10**9, 'B'), (10**6, 'M'), (10**3, 'k')]:
        if abs(n) >= size:
            return f'{n / size:.1f}{suffix}'
    return f'{n:,.2f}'.rstrip('0').rstrip('.') if n % 1 else f'{n:,.0f}'


def exact(value):
    n = number(value)
    return format(n, ',f').rstrip('0').rstrip('.') if n is not None and n % 1 else (f'{n:,.0f}' if n is not None else 'unavailable')


def when(value):
    n = number(value)
    if n is None or n <= 0:
        return 'unavailable'
    try:
        return dt.datetime.fromtimestamp(float(n)).astimezone().strftime('%d %b %Y, %H:%M %Z')
    except (ValueError, OverflowError, OSError):
        return 'unavailable'


def window_label(value):
    n = number(value)
    if n is None or n <= 0:
        return 'Limit', 'Usage'
    if n == 10080:
        return 'W', 'Weekly'
    if n % 1440 == 0:
        return f'{n / 1440:.0f}d', f'{n / 1440:.0f}-day'
    if n % 60 == 0:
        return f'{n / 60:.0f}h', f'{n / 60:.0f}-hour'
    return f'{n:g}m', f'{n:g}-minute'


def render(data, now=None):
    now = time.time() if now is None else now
    fetched = number(data.get('fetchedAtEpoch'))
    if not fetched and data.get('fetchedAt'):
        try:
            fetched = number(dt.datetime.fromisoformat(data['fetchedAt'].replace('Z', '+00:00')).timestamp())
        except ValueError:
            pass
    age = max(0, now - float(fetched)) if fetched else None
    stale = age is None or age >= int(os.environ.get('CODEX_USAGE_STALE_SECONDS', '900'))
    fallback = data.get('source') not in (None, 'app-server')
    response = data.get('rateLimits') or {}
    buckets = response.get('rateLimitsByLimitId') or {}
    if not buckets and isinstance(response.get('rateLimits'), dict):
        b = response['rateLimits']
        buckets = {b.get('limitId') or 'codex': b}
    parts, lines, remaining_values = [], [], []
    pending = False
    plan = None
    reported = False
    for key, b in sorted(buckets.items(), key=lambda item: (item[0] != 'codex', item[0])):
        if not isinstance(b, dict):
            continue
        title = 'Codex' if key == 'codex' else (b.get('limitName') or key)
        label = 'Codex' if key == 'codex' else ('Spark' if 'spark' in title.lower() else title)
        plan = plan or b.get('planType')
        lines.append(title)
        values = []
        bucket_remaining = []
        bucket_unknown = False
        windows = [b[w] for w in ('primary', 'secondary') if isinstance(b.get(w), dict)]
        for w in sorted(windows, key=lambda w: number(w.get('windowDurationMins')) or 0):
            short, long = window_label(w.get('windowDurationMins'))
            short = 'Week' if short == 'W' else short
            used, reset = number(w.get('usedPercent')), number(w.get('resetsAt'))
            expired = reset is not None and reset > 0 and reset <= now
            if expired:
                pending = True
                values.append(chip(f'{short} ?'))
                bucket_unknown = True
                lines.append(f'  {long}: awaiting a fresh value after reset')
            elif used is None:
                values.append(chip(f'{short} ?'))
                bucket_unknown = True
                lines.append(f'  {long}: remaining allowance unavailable')
            else:
                remaining = max(decimal.Decimal(0), min(decimal.Decimal(100), 100 - used))
                remaining_values.append(remaining)
                reported = True
                display = '<1%' if 0 < remaining < 1 else f'{int(remaining)}%'
                values.append(chip(f'{short} {display}', remaining, uncertain=stale or fallback))
                bucket_remaining.append(remaining)
                lines.append(f'  {long}: {int(remaining)}% remaining')
            lines.append(f'  {"Previous reset" if expired else "Resets"}: {when(reset)}')
        credits = b.get('credits') or {}
        balance = number(credits.get('balance'))
        if credits.get('unlimited'):
            values.append(chip('∞ credits', balance=1, uncertain=stale or fallback))
            lines.append('  Credits: unlimited')
            reported = True
        elif balance is not None:
            values.append(chip(f'{compact(balance)} credits', balance=balance, uncertain=stale or fallback))
            lines.append(f'  Credits: {exact(balance)}')
            reported = True
        elif credits.get('hasCredits'):
            lines.append('  Credits available; balance unavailable')
        individual = b.get('individualLimit') or {}
        rem = number(individual.get('remainingPercent'))
        if rem is not None:
            values.append(chip(f'Spend {int(rem)}%', rem, uncertain=stale or fallback))
            bucket_remaining.append(rem)
            lines.append(f'  Spend allowance: {exact(rem)}% remaining')
            lines.append(f'  Spend reset: {when(individual.get("resetsAt"))}')
            remaining_values.append(rem)
            reported = True
        if b.get('spendControlReached') or b.get('rateLimitReachedType'):
            lines.append(f'  Limit reached: {b.get("rateLimitReachedType") or "spend control"}')
            remaining_values.append(decimal.Decimal(0))
            bucket_remaining.append(0)
        parts.append(heading(label, min(bucket_remaining, default=None), uncertain=stale or fallback or bucket_unknown) + '  ' + (' '.join(values) or chip('unavailable')))
        lines.append('')
    resets = response.get('rateLimitResetCredits') or {}
    count = number(resets.get('availableCount'))
    if count is not None:
        parts.append(chip(f'{count:.0f} ' + ('reset' if count == 1 else 'resets'), balance=count, uncertain=stale or fallback))
        lines.append(f'Rate-limit resets available: {count:.0f}')
        for credit in resets.get('credits') or []:
            title = credit.get('title') or 'Rate-limit reset'
            expiry = credit.get('expiresAt')
            lines.append(f'  {title}' + (f'; expires {when(expiry)}' if expiry else ''))
        lines.append('')
    else:
        lines.extend(['Rate-limit reset count unavailable', ''])
    usage = data.get('usage')
    if isinstance(usage, dict):
        summary = usage.get('summary') or {}
        lines.append('Account activity (service-reported; not a bill)')
        for key, label in [('lifetimeTokens', 'Lifetime'), ('peakDailyTokens', 'Peak day')]:
            value = summary.get(key)
            lines.append(f'  {label}: {compact(value)}' + (' tokens' if number(value) is not None else ''))
        daily = usage.get('dailyUsageBuckets')
        valid_days = sorted([d for d in daily or [] if d.get('startDate') and number(d.get('tokens')) is not None], key=lambda d: d['startDate'])[-7:]
        if valid_days:
            total = sum(number(d['tokens']) for d in valid_days)
            lines.append(f'  Recent {len(valid_days)} reported ' + ('day' if len(valid_days) == 1 else 'days') + f': {compact(total)} tokens')
            lines.append(f'  Reported dates: {valid_days[0]["startDate"]} → {valid_days[-1]["startDate"]}')
        else:
            lines.append('  Daily activity unavailable')
        for key, label in [('currentStreakDays', 'Current streak'), ('longestStreakDays', 'Longest streak')]:
            value = number(summary.get(key))
            lines.append(f'  {label}: ' + (f'{value:.0f} days' if value is not None else 'unavailable'))
        duration = number(summary.get('longestRunningTurnSec'))
        lines.append('  Longest turn: ' + (f'{int(duration) // 3600}h {int(duration) % 3600 // 60}m' if duration is not None else 'unavailable'))
        lines.append('')
    else:
        lines.extend(['Account activity unavailable', ''])
    minimum = min(remaining_values, default=100)
    severity = 'hot' if minimum <= 15 else ('warn' if minimum <= 40 or stale or fallback or pending or not reported else 'ok')
    lines.append(f'Plan: {str(plan).replace("_", " ").title() if plan else "unavailable"}')
    age_text = 'unknown age' if age is None else ('just now' if age < 60 else f'{int(age // 60)} min ago')
    lines.append(f'Checked: {when(fetched)} ({age_text})')
    lines.append('Source: Codex account service' if not fallback else 'Source: cached fallback; account data may be missing')
    lines.append('Refreshes every 5 minutes; activity reporting may lag.')
    if stale:
        lines.append('STALE: last known values; live refresh has not succeeded recently.')
    if pending:
        lines.append('A reset time passed; no new allowance is assumed.')
    text = ' '.join(parts) or (heading('Codex') + ' ' + chip('unavailable'))
    if stale:
        text += ' ~'
    if fallback:
        text += ' *'
    return {'text': ' ' + text + ' ', 'class': severity, 'tooltip': tooltip_markup(lines, uncertain=stale or fallback)}


if __name__ == '__main__':
    try:
        print(json.dumps(render(json.load(sys.stdin))))
    except (ValueError, TypeError, KeyError, AttributeError, decimal.InvalidOperation):
        print(json.dumps({'text': ' ' + heading('Codex') + ' ' + chip('unavailable') + ' ', 'class': 'warn', 'tooltip': 'Codex account data unavailable or invalid; waiting for refresh.'}))
