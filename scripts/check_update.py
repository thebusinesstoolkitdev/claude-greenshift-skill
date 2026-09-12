# -*- coding: utf-8 -*-
"""
Check whether this skill is behind the published version on GitHub.

    python scripts/check_update.py

Run at the start of every session that uses the skill. The API gotchas documented here
change as GreenLight/GreenShift release, so a stale copy quietly produces broken builds.

Exit codes: 0 up to date (or check skipped/unavailable), 1 update available.
Set GREENLIGHT_SKIP_UPDATE_CHECK=1 to skip. Never blocks on network failure.
"""
import json
import os
import subprocess
import sys
import urllib.request

REPO = 'thebusinesstoolkitdev/claude-greenshift-skill'
BRANCH = 'main'
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def git(*args):
    try:
        out = subprocess.run(['git', '-C', SKILL_DIR, *args], capture_output=True,
                             text=True, timeout=20)
        return out.stdout.strip() if out.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def remote_head():
    req = urllib.request.Request(
        f'https://api.github.com/repos/{REPO}/commits/{BRANCH}',
        headers={'User-Agent': 'greenlight-skill-update-check', 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.load(resp)
    return data['sha'], data['commit']['committer']['date'][:10], \
        data['commit']['message'].split('\n', 1)[0]


def main():
    if os.environ.get('GREENLIGHT_SKIP_UPDATE_CHECK'):
        return 0

    local = git('rev-parse', 'HEAD')
    if not local:
        print('greenlight: installed without git, so updates cannot be checked. Reinstall with:\n'
              f'  git clone https://github.com/{REPO}.git "{SKILL_DIR}"')
        return 0

    try:
        remote, remote_date, remote_msg = remote_head()
    except Exception as exc:  # network, rate limit, offline — never block a build
        print(f'greenlight: update check skipped ({exc.__class__.__name__}).')
        return 0

    if remote == local:
        print(f'greenlight: up to date ({local[:7]}).')
        return 0

    local_date = git('log', '-1', '--format=%cs') or '?'
    behind = None
    if git('fetch', '-q', 'origin', BRANCH) is not None:
        count = git('rev-list', '--count', f'HEAD..origin/{BRANCH}')
        behind = int(count) if count and count.isdigit() else None
        if behind == 0:
            # Local is ahead of or diverged from the published branch — not stale.
            print(f'greenlight: local copy is ahead of GitHub ({local[:7]} vs {remote[:7]}).')
            return 0

    behind_txt = f'{behind} commit{"s" if behind != 1 else ""} behind' if behind else 'behind'
    print('=' * 72)
    print('GREENLIGHT SKILL UPDATE AVAILABLE')
    print(f'  installed : {local[:7]}  ({local_date})')
    print(f'  published : {remote[:7]}  ({remote_date})  {remote_msg}')
    print(f'  status    : {behind_txt}')
    print()
    print('Tell the user their local skill is out of date and to run:')
    print(f'  git -C "{SKILL_DIR}" pull')
    print('then restart the session so the new SKILL.md is loaded.')
    print('=' * 72)
    return 1


if __name__ == '__main__':
    sys.exit(main())
