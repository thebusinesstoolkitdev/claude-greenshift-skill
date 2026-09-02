# -*- coding: utf-8 -*-
"""
Fetch the upstream block specification and detect drift from it.

This exists because of a specific failure. The block format is defined by WPsoul
in github.com/wpsoul/greenlight-vibe, and an earlier version of this skill
described that format from web-page summaries instead of the source. The
summaries were wrong in ways that were invisible until a build broke:

  * `CSSRender` was reported as boolean `true`; it is the string `"1"`
  * the pages-vs-templates CSS contract came back inverted
  * `dynamicGClasses` and the `stylemanager` block never appeared at all
  * a file called `dynamic-content.md` was listed that does not exist, while
    `validate-styles.md`, `validate-scripts.md` and `dynamic-placeholders.md`
    (which do) were missing from the listing

A summary of a specification is not a specification. Read the source.

    python scripts/upstream.py sync     # clone upstream, record a pin
    python scripts/upstream.py check    # has upstream changed since the pin?
    python scripts/upstream.py show CSSRender      # grep the real docs
    python scripts/upstream.py show -f validate-styles.md

The clone lands in reference/upstream/ and is gitignored. It is deliberately not
vendored into this repo: a vendored copy goes stale silently, which is the same
class of bug this file exists to prevent.
"""
import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = 'https://github.com/wpsoul/greenlight-vibe.git'
DEST = os.path.join(HERE, 'reference', 'upstream')
PIN = os.path.join(HERE, 'reference', 'upstream-pin.json')
SKILL_DIR = os.path.join('skills', 'greenlight-vibe')


def _run(args, cwd=None):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def _spec_files(root):
    """Every file that defines the format: the skill body, its instructions,
    and the two converters, which are the executable spec."""
    base = os.path.join(root, SKILL_DIR)
    out = []
    for sub in ('', 'instructions', 'scripts'):
        d = os.path.join(base, sub)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            p = os.path.join(d, name)
            if os.path.isfile(p) and not name.startswith('.'):
                out.append((os.path.relpath(p, base).replace(os.sep, '/'), p))
    return out


def _digest(path):
    return hashlib.sha256(io.open(path, 'rb').read()).hexdigest()[:16]


def _force_rm(func, path, _exc):
    """git marks objects read-only, and Windows refuses to unlink those, so a
    plain rmtree silently leaves the directory behind and the next clone fails."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def clone(quiet=True):
    if os.path.isdir(DEST):
        shutil.rmtree(DEST, onerror=_force_rm)
        if os.path.isdir(DEST):
            raise SystemExit('could not remove %s, delete it by hand' % DEST)
    os.makedirs(os.path.dirname(DEST), exist_ok=True)
    r = _run(['git', 'clone', '--depth', '1', '-q', REPO, DEST])
    if r.returncode:
        raise SystemExit('clone failed: ' + (r.stderr or r.stdout)[:300])
    sha = _run(['git', 'log', '--format=%H', '-1'], cwd=DEST).stdout.strip()
    date = _run(['git', 'log', '--format=%ad', '--date=short', '-1'],
                cwd=DEST).stdout.strip()
    if not quiet:
        print('cloned %s @ %s (%s)' % (REPO, sha[:10], date))
    return sha, date


def sync():
    sha, date = clone(quiet=False)
    files = _spec_files(DEST)
    pin = {'repo': REPO, 'commit': sha, 'date': date,
           'files': {rel: _digest(p) for rel, p in files}}
    json.dump(pin, io.open(PIN, 'w', encoding='utf-8'), indent=1, sort_keys=True)
    print('pinned %d spec files -> %s' % (len(files), os.path.relpath(PIN, HERE)))
    print('source now readable under reference/upstream/%s/' % SKILL_DIR)
    return 0


def check():
    """Non-zero exit when upstream has moved. Safe to wire into a pre-push hook."""
    if not os.path.exists(PIN):
        print('no pin yet. Run: python scripts/upstream.py sync')
        return 1
    old = json.load(io.open(PIN, encoding='utf-8'))
    sha, date = clone()
    new = {rel: _digest(p) for rel, p in _spec_files(DEST)}

    added = sorted(set(new) - set(old['files']))
    removed = sorted(set(old['files']) - set(new))
    changed = sorted(r for r in set(new) & set(old['files'])
                     if new[r] != old['files'][r])

    print('pinned  %s (%s)' % (old['commit'][:10], old.get('date', '?')))
    print('current %s (%s)' % (sha[:10], date))
    if not (added or removed or changed):
        print('\nspec unchanged, %d files match the pin' % len(new))
        return 0

    print('\nUPSTREAM HAS MOVED. Reconcile before trusting this skill on block format.')
    for label, items in (('changed', changed), ('added', added), ('removed', removed)):
        for rel in items:
            print('  %-8s %s' % (label, rel))
    print('\nRead the changed files, update reference/upstream-block-spec.md and any\n'
          'affected emitter, then re-run sync to move the pin.')
    return 1


def show(args):
    if not os.path.isdir(DEST):
        clone()
    base = os.path.join(DEST, SKILL_DIR)
    if '-f' in args:
        name = args[args.index('-f') + 1]
        for rel, p in _spec_files(DEST):
            if rel.endswith(name):
                print('===== %s =====' % rel)
                print(io.open(p, encoding='utf-8', errors='replace').read())
                return 0
        print('no such spec file: ' + name)
        return 1
    if not args:
        for rel, _ in _spec_files(DEST):
            print('  ' + rel)
        return 0
    term = args[0]
    hits = 0
    for rel, p in _spec_files(DEST):
        for i, line in enumerate(io.open(p, encoding='utf-8', errors='replace'), 1):
            if term.lower() in line.lower():
                print('%s:%d: %s' % (rel, i, line.rstrip()[:300]))
                hits += 1
    if not hits:
        print('no match for %r in the upstream spec' % term)
    return 0


if __name__ == '__main__':
    # the spec contains arrow and dash characters that a cp1252 console cannot
    # encode; without this, `show` dies on output rather than on anything real
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

    cmd = sys.argv[1] if len(sys.argv) > 1 else 'check'
    sys.exit({'sync': lambda: sync(), 'check': lambda: check(),
              'show': lambda: show(sys.argv[2:])}.get(cmd, lambda: check())())
