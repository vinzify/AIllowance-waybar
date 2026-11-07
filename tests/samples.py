"""Invented data for offline tests and public previews. No account exports."""
import datetime as dt

NOW = dt.datetime(2030, 1, 1, 12, tzinfo=dt.timezone.utc).timestamp()


def codex_sample():
    return {
        'source': 'app-server', 'fetchedAtEpoch': NOW,
        'rateLimits': {
            'rateLimits': {'limitId': 'codex', 'planType': 'pro',
                          'primary': {'windowDurationMins': 10080, 'usedPercent': 88, 'resetsAt': NOW + 86400},
                          'credits': {'balance': 1250}},
            'rateLimitResetCredits': {'availableCount': 2, 'credits': [
                {'title': 'Full reset', 'expiresAt': NOW + 30 * 86400}]}},
        'usage': {'summary': {'lifetimeTokens': 1250000, 'peakDailyTokens': 45000,
                             'currentStreakDays': 5, 'longestStreakDays': 12,
                             'longestRunningTurnSec': 3900},
                  'dailyUsageBuckets': [{'startDate': '2029-12-31', 'tokens': 24000}]}}


def gemini_sample():
    def bucket(window, remaining, hours):
        return {'name': window, 'window': window, 'remaining': remaining,
                'reset': dt.datetime.fromtimestamp(NOW + hours * 3600, dt.timezone.utc).isoformat()}
    return {'fetchedAt': NOW, 'credits': 20, 'groups': [
        {'name': 'Gemini Models', 'buckets': [bucket('5h', 1, 4), bucket('weekly', .76, 144)]},
        {'name': 'Claude and GPT models', 'buckets': [bucket('5h', 1, 4), bucket('weekly', 1, 144)]},
        {'name': 'Gemini 4 Argon', 'buckets': [bucket('weekly', .32, 144)]}]}
