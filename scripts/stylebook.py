# -*- coding: utf-8 -*-
"""
Push a design system into the Greenshift stylebook (global settings).

    python stylebook.py push reference/starter-tokens.json
    python stylebook.py dump                 # what is currently stored
    python stylebook.py verify               # confirm tokens/classes reach the front end

Why the stylebook and not per-block styles: every value lives in ONE place, so a brand
tweak is a single API call instead of a re-generation of every page. It also sidesteps
the responsive-array bug in server-side CSSRender, because media queries live in class
CSS rather than in block styleAttributes.

Merge semantics: each top-level key you send REPLACES the stored value wholesale, so
this script always reads current settings and merges locally before writing.
"""
import json
import re
import sys
import urllib.request

sys.path.insert(0, __file__.rsplit('\\', 1)[0].rsplit('/', 1)[0])
from wp_api import WP  # noqa: E402


def to_css(spec):
    """Render a stylebook spec as plain CSS.

    The core backend has no Greenshift to hold global classes, but the markup it
    emits still references them, so they have to be defined somewhere or the page
    ships unstyled. This is the same design system, expressed as CSS.
    """
    out = []
    rows = []
    for v in spec.get('variables') or []:
        name = (v.get('variable') or v.get('name') or '').lstrip('-')
        if name:
            rows.append('  --%s: %s;' % (name, v.get('variable_value', v.get('value', ''))))
    if rows:
        out.append(':root{\n' + '\n'.join(rows) + '\n}')
    for element in spec.get('elements') or []:
        if element.get('css'):
            out.append(element['css'])
    for cls in spec.get('global_classes') or []:
        if cls.get('css'):
            out.append(cls['css'])
    return '\n'.join(out)


def push_core(path):
    """Push the stylebook as CSS onto the FSE global-styles record, no plugin.

    FSE themes carry arbitrary CSS at styles.css on that record, which is the
    closest native equivalent to a Greenshift global class and survives theme
    updates. If the record cannot be resolved, fall back to `css` and paste.
    """
    wp = WP()
    with open(path, encoding='utf-8') as fh:
        spec = json.load(fh)
    css = to_css(spec)

    active = wp.get('wp/v2/themes?status=active')
    slug = active[0]['stylesheet'] if active else None
    record = None
    if slug:
        try:
            record = wp.get('wp/v2/global-styles/themes/%s' % slug)
        except Exception:
            record = None
    gs_id = (record or {}).get('id')
    if not gs_id:
        raise SystemExit(
            'could not resolve the global-styles record for the active theme.\n'
            'Write the CSS out and paste it into Appearance -> Editor -> Styles -> '
            'Additional CSS instead:\n'
            '  python scripts/stylebook.py css <spec.json> > stylebook.css')

    current = wp.get('wp/v2/global-styles/%s?context=edit' % gs_id)
    styles = dict(current.get('styles') or {})
    styles['css'] = css
    wp.post('wp/v2/global-styles/%s' % gs_id, {'styles': styles})
    print('pushed %d bytes of stylebook CSS to global styles (%s)' % (len(css), slug))


def push(path):
    wp = WP()
    with open(path, encoding='utf-8') as fh:
        spec = json.load(fh)

    current = wp.gs_settings()
    payload = {}

    if spec.get('variables'):
        merged = list(current.get('variables') or [])
        index = {v.get('variable'): i for i, v in enumerate(merged)}
        for var in spec['variables']:
            if var['variable'] in index:
                merged[index[var['variable']]] = var
            else:
                merged.append(var)
        payload['variables'] = merged

    if spec.get('global_classes'):
        merged = list(current.get('global_classes') or [])
        index = {c.get('value'): i for i, c in enumerate(merged)}
        for cls in spec['global_classes']:
            if cls['value'] in index:
                merged[index[cls['value']]] = cls
            else:
                merged.append(cls)
        payload['global_classes'] = merged

    if spec.get('elements'):
        payload['elements'] = spec['elements']   # element styles are a full set, not a merge

    if spec.get('colours'):
        payload['colours'] = spec['colours']

    wp.post('greenshift/v1/global_settings', payload)

    after = wp.gs_settings()
    print(f"variables: {len(after.get('variables') or [])}  "
          f"classes: {len(after.get('global_classes') or [])}  "
          f"elements: {len(after.get('elements') or [])}  "
          f"colours: {len(after.get('colours') or [])}")


def dump():
    settings = WP().gs_settings()
    print(json.dumps({
        'variables': settings.get('variables') or [],
        'colours': settings.get('colours') or [],
        'elements': [e.get('selector') for e in (settings.get('elements') or [])],
        'global_classes': [c.get('value') for c in (settings.get('global_classes') or [])],
    }, indent=1))


def verify():
    """Fetch the home page and confirm tokens + classes actually reach the browser."""
    wp = WP()
    settings = wp.gs_settings()
    req = urllib.request.Request(wp.url + '/?stylebook_check=1')
    req.add_header('User-Agent', 'Mozilla/5.0 (compatible; stylebook-verify)')
    with urllib.request.urlopen(req, timeout=60) as resp:
        html = resp.read().decode('utf-8', 'replace')

    missing_vars, missing_classes = [], []
    for var in (settings.get('variables') or []):
        if var['variable'] + ':' not in html:
            missing_vars.append(var['variable'])
    for cls in (settings.get('global_classes') or []):
        selector = re.escape('.' + cls['value'])
        if not re.search(selector + r'[{\s:,]', html):
            missing_classes.append(cls['value'])

    print(f"variables on page: {len(settings.get('variables') or []) - len(missing_vars)}"
          f"/{len(settings.get('variables') or [])}")
    if missing_vars:
        print('  missing:', ', '.join(missing_vars))
    print(f"classes on page: {len(settings.get('global_classes') or []) - len(missing_classes)}"
          f"/{len(settings.get('global_classes') or [])}")
    if missing_classes:
        print('  missing (may simply be unused on this page):', ', '.join(missing_classes))

    # a grouped selector (body h1,body h2{...}) is correct and common, so match
    # the selector in any position rather than only at the start of a rule
    import re as _re
    if not _re.search(r'body\s+h1\s*[,{]', html):
        print('WARNING: element styles absent, check `elements` used the `body h1` prefix, '
              'otherwise theme rules that load later will win.')


if __name__ == '__main__':
    command = sys.argv[1] if len(sys.argv) > 1 else 'dump'
    spec_path = (sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith('-')
                 else 'reference/starter-tokens.json')
    if command == 'push':
        # --core writes the same design system as CSS on the FSE global-styles
        # record, for builds that are not running the Greenshift plugin
        (push_core if '--core' in sys.argv else push)(spec_path)
    elif command == 'css':
        print(to_css(json.load(open(spec_path, encoding='utf-8'))))
    elif command == 'verify':
        verify()
    else:
        dump()
