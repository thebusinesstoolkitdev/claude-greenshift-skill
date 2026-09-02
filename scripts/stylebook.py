# -*- coding: utf-8 -*-
"""
Push a design system into the Greenshift stylebook (global settings), and
optionally register the same tokens as theme.json presets.

    python stylebook.py push reference/starter-tokens.json           # stylebook only
    python stylebook.py push reference/starter-tokens.json --theme   # + theme.json presets, gt- aliased
    python stylebook.py push reference/starter-tokens.json --core    # no plugin: CSS on global styles
    python stylebook.py map  reference/starter-tokens.json [--apply] # find theme presets with the same value
    python stylebook.py remove reference/starter-tokens.json         # retire everything the spec defines
    python stylebook.py dump                                         # what is currently stored
    python stylebook.py verify                                       # tokens/classes reach the front end

Why the stylebook: every shared value lives in ONE place, so a brand tweak is a
single API call instead of a re-generation of every page. Per-page classes do
not belong here; they go in a stylemanager block (blocks.style_manager).

Why --theme: upstream prefers the theme's own `--wp--preset--*` and
`--wp--custom--*` variables over a parallel token set, because two systems
drift. With --theme each `gt-` token becomes a theme.json preset of its `kind`
(palette, font size, spacing size, or settings.custom) on the user global-styles
record, and the stylebook variable is rewritten to alias it:

    --gt-purple: var(--wp--preset--color--gt-purple)

Generators keep using the gt- names; the theme owns the values, the site editor
shows them, and core blocks can pick them from the preset pickers. A token with
an explicit `alias` points at an existing theme variable instead of registering
a new one (`map --apply` fills those in where values already match).

Merge semantics: each top-level stylebook key you send REPLACES the stored value
wholesale, and so does each of `settings` / `styles` on the global-styles record,
so this script always reads, merges locally, then writes.
"""
import json
import re
import sys
import urllib.request

sys.path.insert(0, __file__.rsplit('\\', 1)[0].rsplit('/', 1)[0])
from wp_api import WP  # noqa: E402

KINDS = ('color', 'font-size', 'spacing', 'font-family', 'custom')

# kind -> (settings path, value key, css var prefix)
PRESETS = {
    'color':     (('color', 'palette'), 'color', '--wp--preset--color--'),
    'font-size': (('typography', 'fontSizes'), 'size', '--wp--preset--font-size--'),
    'spacing':   (('spacing', 'spacingSizes'), 'size', '--wp--preset--spacing--'),
}


def load(path):
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


def var_name(var):
    return (var.get('variable') or var.get('name') or '').lstrip('-')


def kind_of(var):
    """Explicit `kind`, else a conservative guess: only colours are inferred."""
    kind = var.get('kind')
    if kind:
        if kind not in KINDS:
            raise SystemExit('%s: kind %r is not one of %s' % (var.get('variable'), kind, KINDS))
        return kind
    value = str(var.get('variable_value', ''))
    if re.match(r'^(#[0-9a-f]{3,8}|rgba?\(|hsla?\()', value, re.I):
        return 'color'
    return 'custom'


def custom_slug(name):
    return name.replace('gt-', '', 1) if name.startswith('gt-') else name


def wp_kebab(text):
    """WordPress's _wp_to_kebab_case, which it applies to every preset slug and
    settings.custom key before emitting the CSS variable: `h1` becomes `h-1`,
    `fooBar` becomes `foo-bar`. Alias to what the page will actually define."""
    words = re.findall(r'[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+', text)
    return '-'.join(w.lower() for w in words)


def alias_var(var):
    """The theme variable this token points at once registered (or its `alias`)."""
    if var.get('alias'):
        return var['alias']
    kind, name = kind_of(var), var_name(var)
    if kind in PRESETS:
        return PRESETS[kind][2] + wp_kebab(name)
    return '--wp--custom--gt--' + wp_kebab(custom_slug(name))


# ---------------------------------------------------------------------------
# plain CSS rendering (core backend, or a file to paste)
# ---------------------------------------------------------------------------

def to_css(spec, aliased=False):
    """Render a stylebook spec as plain CSS.

    The core backend has no Greenshift to hold global classes, but the markup it
    emits still references them, so they have to be defined somewhere or the page
    ships unstyled. This is the same design system, expressed as CSS.
    """
    out = []
    rows = []
    for v in spec.get('variables') or []:
        name = var_name(v)
        if name:
            value = ('var(%s)' % alias_var(v) if aliased
                     else v.get('variable_value', v.get('value', '')))
            rows.append('  --%s: %s;' % (name, value))
    if rows:
        out.append(':root{\n' + '\n'.join(rows) + '\n}')
    for element in spec.get('elements') or []:
        if element.get('css'):
            out.append(element['css'])
    for cls in spec.get('global_classes') or []:
        if cls.get('css'):
            out.append(cls['css'])
    return '\n'.join(out)


# ---------------------------------------------------------------------------
# theme.json presets on the user global-styles record
# ---------------------------------------------------------------------------

def _origin_list(settings, path):
    """Return the mutable list for a preset path on the user record.

    WordPress stores user-level presets keyed by origin (`palette.custom`); the
    theme's own entries sit under `palette.theme` and are left alone. A bare list
    is accepted too, in case a plugin wrote one.
    """
    node = settings
    for key in path[:-1]:
        node = node.setdefault(key, {})
    leaf = node.get(path[-1])
    if isinstance(leaf, list):
        return leaf
    if leaf is None:
        leaf = node[path[-1]] = {}
    return leaf.setdefault('custom', [])


def register_presets(wp, spec, remove=False):
    """Add (or remove) the spec's variables as presets on the user global styles.

    Returns {variable: alias var} for every token, whether registered or aliased
    onto an existing theme variable.
    """
    record = wp.global_styles()
    settings = dict(record.get('settings') or {})
    aliases = {}
    for var in spec.get('variables') or []:
        if var.get('alias'):
            aliases[var['variable']] = var['alias']  # points at an existing theme var
            continue
        kind, name = kind_of(var), var_name(var)
        value = var.get('variable_value', var.get('value', ''))
        if kind in PRESETS:
            path, value_key, prefix = PRESETS[kind]
            entries = _origin_list(settings, path)
            entries[:] = [e for e in entries if e.get('slug') != name]
            if not remove:
                entries.append({'slug': name, 'name': var.get('label') or name,
                                value_key: value})
        else:
            # settings.custom.gt.<name> -> --wp--custom--gt--<name>
            bucket = settings.setdefault('custom', {}).setdefault('gt', {})
            bucket.pop(custom_slug(name), None)
            if not remove:
                bucket[custom_slug(name)] = value
            if remove and not bucket:
                settings['custom'].pop('gt', None)
        aliases[var['variable']] = alias_var(var)
    if remove:
        # leave the record as it was found: no empty origin lists or buckets
        for path, _, _ in PRESETS.values():
            node = settings
            for key in path[:-1]:
                node = node.get(key) or {}
            leaf = node.get(path[-1])
            if isinstance(leaf, dict) and not leaf.get('custom'):
                leaf.pop('custom', None)
                if not leaf:
                    node.pop(path[-1], None)
        if not settings.get('custom'):
            settings.pop('custom', None)
    wp.set_global_styles(settings=settings)
    return aliases


# ---------------------------------------------------------------------------
# stylebook
# ---------------------------------------------------------------------------

def _merge_by(existing, incoming, key):
    merged = list(existing or [])
    index = {item.get(key): i for i, item in enumerate(merged)}
    for item in incoming:
        if item[key] in index:
            merged[index[item[key]]] = item
        else:
            merged.append(item)
    return merged


def _stylebook_var(var, aliases):
    """The spec entry in the shape Greenshift stores, minus this script's own keys."""
    out = {k: v for k, v in var.items() if k not in ('kind', 'alias')}
    if var['variable'] in aliases:
        out['variable_value'] = 'var(%s)' % aliases[var['variable']]
    out.setdefault('label', var_name(var))
    out.setdefault('value', 'var(%s)' % var['variable'])
    out.setdefault('group', 'imported')
    return out


def push(path, theme=False):
    wp = WP()
    spec = load(path)
    aliases = register_presets(wp, spec) if theme else {}

    current = wp.gs_settings()
    payload = {}
    if spec.get('variables'):
        incoming = [_stylebook_var(v, aliases) for v in spec['variables']]
        payload['variables'] = _merge_by(current.get('variables'), incoming, 'variable')
    if spec.get('global_classes'):
        payload['global_classes'] = _merge_by(current.get('global_classes'),
                                              spec['global_classes'], 'value')
    if spec.get('elements'):
        payload['elements'] = spec['elements']   # element styles are a full set, not a merge
    if spec.get('colours'):
        payload['colours'] = spec['colours']
    wp.post('greenshift/v1/global_settings', payload)

    after = wp.gs_settings()
    print('variables: %d  classes: %d  elements: %d  colours: %d'
          % (len(after.get('variables') or []), len(after.get('global_classes') or []),
             len(after.get('elements') or []), len(after.get('colours') or [])))
    if theme:
        print('theme presets registered: %d, gt- variables aliased onto them' % len(aliases))


def push_core(path, theme=False):
    """Push the stylebook as CSS onto the FSE global-styles record, no plugin.

    FSE themes carry arbitrary CSS at styles.css on that record, which is the
    closest native equivalent to a Greenshift global class and survives theme
    updates. With --theme the tokens are registered as presets first and the CSS
    aliases them, the same as the Greenshift path.
    """
    wp = WP()
    spec = load(path)
    if theme:
        register_presets(wp, spec)
    css = to_css(spec, aliased=theme)
    record = wp.global_styles()
    styles = dict(record.get('styles') or {})
    styles['css'] = css
    wp.set_global_styles(styles=styles)
    print('pushed %d bytes of stylebook CSS to global styles record %d'
          % (len(css), record['id']))


def remove(path):
    """Retire every variable, class and preset the spec defines."""
    wp = WP()
    spec = load(path)
    names = {v['variable'] for v in spec.get('variables') or []}
    classes = {c['value'] for c in spec.get('global_classes') or []}
    current = wp.gs_settings()
    payload = {
        'variables': [v for v in current.get('variables') or []
                      if v.get('variable') not in names],
        'global_classes': [c for c in current.get('global_classes') or []
                           if c.get('value') not in classes],
    }
    wp.post('greenshift/v1/global_settings', payload)
    register_presets(wp, spec, remove=True)
    print('removed %d variables, %d classes, and their theme presets'
          % (len(names), len(classes)))


# ---------------------------------------------------------------------------
# inspection
# ---------------------------------------------------------------------------

def theme_presets(wp):
    """{css var: value} for every preset and custom value the theme exposes."""
    theme = wp.get('wp/v2/themes?status=active')[0]['stylesheet']
    data = wp.get('wp/v2/global-styles/themes/%s' % theme)
    settings = data.get('settings') or {}
    out = {}
    for kind, (path, value_key, prefix) in PRESETS.items():
        node = settings
        for key in path:
            node = (node or {}).get(key) or {}
        lists = node.values() if isinstance(node, dict) else [node]
        for entries in lists:
            for e in entries or []:
                if e.get('slug'):
                    out[prefix + wp_kebab(e['slug'])] = str(e.get(value_key, ''))

    def walk(node, trail):
        for k, v in (node or {}).items():
            slug = wp_kebab(k)
            if isinstance(v, dict):
                walk(v, trail + [slug])
            else:
                out['--wp--custom--' + '--'.join(trail + [slug])] = str(v)
    walk(settings.get('custom'), [])
    return out


def map_presets(path, apply=False):
    """Report which tokens already exist in the theme under another name."""
    wp = WP()
    spec = load(path)
    by_value = {}
    for name, value in theme_presets(wp).items():
        by_value.setdefault(re.sub(r'\s+', '', value.lower()), []).append(name)
    hits = 0
    for var in spec.get('variables') or []:
        value = re.sub(r'\s+', '', str(var.get('variable_value', '')).lower())
        matches = by_value.get(value) or []
        if matches:
            hits += 1
            print('%-22s = %-32s matches %s'
                  % (var['variable'], var.get('variable_value'), ', '.join(matches)))
            if apply:
                var['alias'] = matches[0]
        else:
            print('%-22s = %-32s (no theme preset with this value)'
                  % (var['variable'], var.get('variable_value')))
    print('\n%d of %d tokens have a theme preset with the same value'
          % (hits, len(spec.get('variables') or [])))
    if apply:
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(spec, fh, indent=1, ensure_ascii=False)
            fh.write('\n')
        print('wrote alias keys into', path)


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

    missing_vars, missing_classes, dangling = [], [], []
    for var in (settings.get('variables') or []):
        if var['variable'] + ':' not in html:
            missing_vars.append(var['variable'])
        # an aliased token is only as good as the preset it points at
        target = re.match(r'var\((--wp--[a-z0-9-]+)', str(var.get('variable_value', '')))
        if target and target.group(1) + ':' not in html:
            dangling.append('%s -> %s' % (var['variable'], target.group(1)))
    for cls in (settings.get('global_classes') or []):
        selector = re.escape('.' + cls['value'])
        if not re.search(selector + r'[{\s:,]', html):
            missing_classes.append(cls['value'])

    total_vars = len(settings.get('variables') or [])
    print('variables on page: %d/%d' % (total_vars - len(missing_vars), total_vars))
    if missing_vars:
        print('  missing:', ', '.join(missing_vars))
    if dangling:
        print('  ALIASED TO A VARIABLE THE PAGE NEVER DEFINES:', '; '.join(dangling))
    total_classes = len(settings.get('global_classes') or [])
    print('classes on page: %d/%d' % (total_classes - len(missing_classes), total_classes))
    if missing_classes:
        print('  missing (may simply be unused on this page):', ', '.join(missing_classes))

    # a grouped selector (body h1,body h2{...}) is correct and common, so match
    # the selector in any position rather than only at the start of a rule
    if not re.search(r'body\s+h1\s*[,{]', html):
        print('WARNING: element styles absent, check `elements` used the `body h1` prefix, '
              'otherwise theme rules that load later will win.')


if __name__ == '__main__':
    command = sys.argv[1] if len(sys.argv) > 1 else 'dump'
    spec_path = (sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith('-')
                 else 'reference/starter-tokens.json')
    theme = '--theme' in sys.argv
    if command == 'push':
        # --core writes the same design system as CSS on the FSE global-styles
        # record, for builds that are not running the Greenshift plugin
        (push_core if '--core' in sys.argv else push)(spec_path, theme=theme)
    elif command == 'css':
        print(to_css(load(spec_path), aliased=theme))
    elif command == 'map':
        map_presets(spec_path, apply='--apply' in sys.argv)
    elif command == 'remove':
        remove(spec_path)
    elif command == 'verify':
        verify()
    else:
        dump()
