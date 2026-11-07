#!/usr/bin/env python3
"""Install standalone modules and write a config fragment; never edit the user's bar."""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil


def install(destination):
    source = Path(__file__).resolve().parent
    destination = destination.expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    for file in (source / 'scripts').iterdir():
        if file.suffix in ('.py', '.sh'):
            target = destination / file.name
            shutil.copyfile(file, target)
            target.chmod(0o755 if file.suffix == '.sh' or file.name.endswith('-usage.py') else 0o644)
    config = {}
    for name, script, interval in [('codex', 'codex-usage.sh', 10), ('antigravity', 'antigravity-usage.py', 30)]:
        command = shlex.quote(str(destination / script))
        config[f'custom/{name}-usage'] = {
            'exec': command, 'interval': interval, 'return-type': 'json',
            'tooltip': True, 'escape': False,
            'on-click': command + ' --refresh', 'exec-on-event': True,
        }
    (destination / 'modules.json').write_text(json.dumps(config, indent=2) + '\n')
    shutil.copyfile(source / 'examples/style.css', destination / 'style.css')
    print(f'Installed to {destination}')
    print(f'Merge {destination / "modules.json"} into your Waybar config.')
    print('Add custom/codex-usage and/or custom/antigravity-usage to modules-right.')
    print('Existing Waybar configuration was not changed. See README.md for styling.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path,
                        default=Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'waybar/aillowance')
    install(parser.parse_args().destination)
