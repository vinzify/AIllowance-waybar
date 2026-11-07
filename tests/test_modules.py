import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from allowance_style import chip
from samples import NOW, codex_sample, gemini_sample


def load(filename):
    spec = importlib.util.spec_from_file_location(filename, ROOT / 'scripts' / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


codex = load('codex-usage-render.py')
gemini = load('antigravity-usage.py')


def plain(markup):
    return ''.join(ET.fromstring('<root>' + markup + '</root>').itertext())


class RenderingTests(unittest.TestCase):
    def test_sample_output_and_markup(self):
        for module, data, expected in [(codex, codex_sample(), 'Week 12%'),
                                       (gemini, gemini_sample(), 'Argon 32%')]:
            output = module.render(data, NOW)
            self.assertIn(expected, plain(output['text']))
            self.assertIn('Remaining allowance', plain(output['tooltip']))

    def test_thresholds(self):
        for value, color in [(0, '#ff858f'), (15, '#ff858f'), (15.1, '#ffd078'),
                             (40, '#ffd078'), (40.1, '#78dfa5'), (100, '#78dfa5'), (None, '#a5a7b5')]:
            self.assertIn(color, chip('quota', value))

    def test_credits_zero_and_unknown(self):
        self.assertIn('#ff858f', chip('0 credits', balance=0))
        self.assertIn('#a5a7b5', chip('? credits'))
        self.assertIn('#cbb5ff', chip('1 credit', balance=1))

    def test_stale_is_grey(self):
        for module, data in [(codex, codex_sample()), (gemini, gemini_sample())]:
            output = module.render(data, NOW + 1000)
            self.assertIn('⚪', output['text'])
            self.assertIn('#a5a7b5', output['text'])
            self.assertIn('STALE', plain(output['tooltip']))

    def test_expired_quota_is_not_reset_to_full(self):
        data = codex_sample()
        data['rateLimits']['rateLimits']['primary']['resetsAt'] = NOW - 1
        self.assertIn('Week ?', plain(codex.render(data, NOW)['text']))
        data = gemini_sample()
        data['groups'][0]['buckets'][0]['reset'] = '2000-01-01T00:00:00Z'
        self.assertIn('5h ?', plain(gemini.render(data, NOW)['text']))

    def test_markup_escaped(self):
        self.assertEqual(plain(chip('<quota> & value', 5)), ' <quota> & value ')
        data = gemini_sample()
        data['groups'][0]['name'] = 'Gemini <b> & test'
        self.assertIn('Gemini &lt;b&gt; &amp; test', gemini.render(data, NOW)['text'])

    def test_tiny_quota_does_not_look_empty(self):
        data = codex_sample()
        data['rateLimits']['rateLimits']['primary']['usedPercent'] = 99.7
        self.assertIn('<1%', plain(codex.render(data, NOW)['text']))

    def test_missing_data_not_zero(self):
        for module in (codex, gemini):
            output = module.render({}, NOW)
            self.assertIn('unavailable', plain(output['text']))
            self.assertNotIn('0%', plain(output['text']))

    def test_missing_codex_usage_does_not_hide_limits(self):
        data = codex_sample()
        del data['usage']
        output = codex.render(data, NOW)
        self.assertIn('Week 12%', plain(output['text']))
        self.assertIn('Account activity unavailable', plain(output['tooltip']))

    def test_invalid_fractions_rejected(self):
        for value in [True, None, -1, 2, float('nan'), float('inf')]:
            with self.assertRaises(ValueError):
                gemini.normalize_groups({'groups': [{'buckets': [{'remaining_fraction': value}]}]})
        data = gemini.normalize_groups({'groups': [{'buckets': [{'remaining_fraction': 0}]}]})
        self.assertEqual(data[0]['buckets'][0]['remaining'], 0)

    def test_refuses_model_turns_as_usage_report(self):
        original = gemini.run_cli
        try:
            for turns, conversation in [(1, ''), (0, 'conversation')]:
                gemini.run_cli = lambda *a: json.dumps({'status': 'SUCCESS', 'num_turns': turns,
                    'conversation_id': conversation, 'command': {'name': 'usage', 'data': {}}}).encode()
                with self.assertRaises(ValueError):
                    gemini.command_report('usage', {}, '/')
        finally:
            gemini.run_cli = original


class IntegrationTests(unittest.TestCase):
    def test_installer_with_spaces_and_no_config_rewrite(self):
        with tempfile.TemporaryDirectory(prefix='aillowance test ') as temp:
            destination = Path(temp) / 'modules'
            subprocess.run([sys.executable, str(ROOT / 'install.py'), '--destination', str(destination)],
                           check=True, stdout=subprocess.DEVNULL)
            config = json.loads((destination / 'modules.json').read_text())
            command = config['custom/antigravity-usage']['exec']
            self.assertTrue(command.startswith("'"))
            self.assertFalse(config['custom/codex-usage']['escape'])
            self.assertTrue(os.access(destination / 'codex-usage.sh', os.X_OK))
            self.assertFalse((Path(temp) / 'config').exists())

    def test_codex_collector_offline_and_private_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            fake = Path(temp) / 'codex'
            sample = codex_sample()
            fake.write_text('#!' + sys.executable + '\nimport sys,json\n' +
                'responses=' + repr({0: {}, 6: sample['rateLimits'], 7: sample['usage']}) + '\n' +
                'for line in sys.stdin:\n r=json.loads(line)\n if "id" in r: print(json.dumps({"id":r["id"],"result":responses[r["id"]]}),flush=True)\n')
            fake.chmod(0o700)
            cache = Path(temp) / 'cache' / 'codex.json'
            env = {**os.environ, 'CODEX_USAGE_CODEX_BIN': str(fake), 'CODEX_USAGE_CACHE_FILE': str(cache)}
            subprocess.run(['bash', str(ROOT / 'scripts/codex-usage-refresh.sh')], env=env, check=True, timeout=10)
            snapshot = json.loads(cache.read_text())
            self.assertEqual(snapshot['rateLimits'], sample['rateLimits'])
            self.assertEqual(cache.stat().st_mode & 0o777, 0o600)
            result = subprocess.check_output(['bash', str(ROOT / 'scripts/codex-usage.sh')], env=env, timeout=5)
            self.assertIn('Week 12%', plain(json.loads(result)['text']))


if __name__ == '__main__':
    unittest.main()
