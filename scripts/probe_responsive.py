# -*- coding: utf-8 -*-
"""
Probe: do responsive styleAttributes arrays survive REST and compile on the front end?

Publishes one throwaway page carrying every array shape this skill cares about,
reads the raw content back, fetches the rendered page, checks the compiled CSS for
each block, and deletes the page. Exit code is non-zero on any failure, so it can
gate a build.

    python scripts/probe_responsive.py            # persistence + render check
    python scripts/probe_responsive.py --parity   # also diff compile_css() against the renderer
    python scripts/probe_responsive.py --keep     # leave the page up for a look

Needs WP_URL / WP_USER / WP_APP_PASSWORD (env or .env) and a site where the page
is publicly readable once published: the front end is fetched anonymously.
"""
import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.wp_api import WP, UA  # noqa: E402
from scripts import blocks as B  # noqa: E402

CASES = {
    'one':   {'padding': ['40px']},
    'two':   {'padding': ['40px', '30px']},
    'three': {'padding': ['40px', '30px', '20px']},
    'four':  {'padding': ['40px', '30px', '20px', '10px'],
              'fontSize': ['32px', '28px', '24px', '18px']},
    'nulls': {'padding': ['40px', None, None, '10px']},
    'empty': {'padding': ['40px', '', '', '10px']},
    'grid':  {'display': ['grid'],
              'gridTemplateColumns': ['1fr 1fr 1fr', '1fr 1fr', '1fr'],
              'gap': ['24px', '16px', '8px']},
    'mixed': {'padding': ['40px', '30px', '20px'], 'fontSize': ['32px'],
              'color': ['#ff0000', '#00ff00', '#0000ff', '#000000']},
}


# a stylemanager block: one local class with a media rule, plus class-less CSS
SM_CLASSES = {
    'glprobe-card': '.glprobe-card{border:2px solid #123456;}'
                    '@media (max-width:767.98px){.glprobe-card{border-width:1px;}}',
}
# class-less CSS on the carrier. Known: the PHP renderer does NOT emit it (nor
# customCSS_Extra) on template targets; compile_css() does on page targets. The
# probe reports rather than fails, so a renderer that starts emitting it is noticed.
SM_CUSTOM = '.glprobe-card>span{color:#654321;}'
SM_EXPECT = {'class css': SM_CLASSES['glprobe-card']}


def kebab(prop):
    return re.sub(r'(?<!^)(?=[A-Z])', '-', prop).lower()


def expected_rules(bid, style):
    """The rule set the renderer should emit: {(breakpoint, 'prop:value')}."""
    out = set()
    for prop, values in style.items():
        for i, v in enumerate(values[:len(B.BREAKPOINTS)]):
            if v in (None, ''):
                continue
            out.add((B.BREAKPOINTS[i], '%s:%s' % (kebab(prop), v)))
    return out


def rules_in(css, bid):
    """Parse rendered CSS into the same {(breakpoint, 'prop:value')} shape."""
    out = set()
    for m in re.finditer(r'(?:@media \(max-width:([\d.]+px)\)\s*\{)?\s*\.%s\{([^}]*)\}'
                         % re.escape(bid), css):
        bp, body = m.group(1), m.group(2)
        for decl in body.split(';'):
            decl = decl.strip()
            if decl:
                out.add((bp, re.sub(r'\s*:\s*', ':', decl)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--parity', action='store_true',
                    help='also compare compile_css() output with the live renderer')
    ap.add_argument('--keep', action='store_true', help='do not delete the probe page')
    args = ap.parse_args()

    wp = WP()
    B.set_target('template')  # CSSRender on, so the PHP renderer does the compiling
    markup = B.style_manager('probe-sm', classes=SM_CLASSES, name='probe stylemanager')
    # customCss is appended by hand: style_manager() refuses it on a template target
    markup = markup.replace('"isVariation": "stylemanager"',
                            '"isVariation": "stylemanager", "customCss": "%s"' % SM_CUSTOM)
    markup += ''.join(B.block('probe-' + k, tag='div', text=k, style=v, name='probe ' + k,
                              classes='glprobe-card' if k == 'one' else None)
                      for k, v in CASES.items())
    page = wp.post('wp/v2/pages', {'title': 'greenlight responsive probe',
                                   'slug': 'greenlight-responsive-probe',
                                   'status': 'publish', 'content': markup})
    pid, link = page['id'], page['link']
    print('probe page', pid, link)
    failures = 0
    try:
        raw = wp.get('wp/v2/pages/%d?context=edit' % pid)['content']['raw']
        req = urllib.request.Request(link, headers={'User-Agent': UA})
        html = urllib.request.urlopen(req, timeout=60).read().decode('utf-8', 'replace')
        css_all = ''.join(re.findall(r'<style[^>]*>(.*?)</style>', html, re.S))

        for name, style in CASES.items():
            bid = B.make_id('probe-' + name)
            stored = re.search(r'"id":"%s".*?"styleAttributes":(\{.*?\})' % bid, raw)
            persisted = stored and json.loads(stored.group(1)) == style
            want = expected_rules(bid, style)
            got = rules_in(css_all, bid)
            ok = persisted and want == got
            failures += 0 if ok else 1
            print('%-6s %s  stored=%s  rules=%d/%d'
                  % (name, 'PASS' if ok else 'FAIL', 'yes' if persisted else 'NO',
                     len(want & got), len(want)))
            if not ok:
                for r in sorted(want - got, key=str):
                    print('        missing', r)
                for r in sorted(got - want, key=str):
                    print('        extra  ', r)

        # stylemanager: local classes and customCss must reach the page verbatim
        squash = lambda s: re.sub(r'\s+', '', s)
        for label, fragment in SM_EXPECT.items():
            ok = squash(fragment) in squash(css_all)
            failures += 0 if ok else 1
            print('%-6s %s  stylemanager %s' % ('sm', 'PASS' if ok else 'FAIL', label))
        rendered = squash(SM_CUSTOM) in squash(css_all)
        print('%-6s %s  stylemanager customCss %s' % (
            'sm', 'INFO', 'RENDERED: the PHP renderer now emits customCss, revisit '
            'style_manager() and check_blocks.py' if rendered
            else 'not rendered by PHP (known; page targets compile it)'))

        if args.parity:
            print('\ncompile_css() parity against the renderer:')
            local = B.compile_css(markup)
            for name, style in CASES.items():
                bid = B.make_id('probe-' + name)
                a, b = rules_in(local, bid), rules_in(css_all, bid)
                ok = a == b
                failures += 0 if ok else 1
                print('%-6s %s' % (name, 'PASS' if ok else 'FAIL'))
                if not ok:
                    print('        local-only ', sorted(a - b, key=str))
                    print('        server-only', sorted(b - a, key=str))
            for label, fragment in list(SM_EXPECT.items()) + [('customCss', SM_CUSTOM)]:
                ok = squash(fragment) in squash(local)
                failures += 0 if ok else 1
                print('%-6s %s  stylemanager %s' % ('sm', 'PASS' if ok else 'FAIL', label))
    finally:
        if not args.keep:
            wp.delete('wp/v2/pages/%d?force=true' % pid)
            print('\nprobe page deleted')
    print('\n%s' % ('ALL PASS' if not failures else '%d FAILURE(S)' % failures))
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
