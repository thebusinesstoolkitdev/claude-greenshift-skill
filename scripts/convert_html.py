# -*- coding: utf-8 -*-
"""
Convert one HTML design to GreenLight blocks with upstream's converter, then
apply this skill's delivery contract and checks.

    python scripts/convert_html.py input/hero.html -o output/hero.html
    python scripts/convert_html.py input/home.html -o output/home.html --target page
    python scripts/convert_html.py input/home.html --target page --publish "Home" --slug home
    python scripts/convert_html.py input/home.html --target page --raw-css ...

When you have a single finished HTML file, WPsoul's `convert.js` is the better
tool than hand-emitting blocks from Python: it maps every element, turns the
`<style>` into a stylemanager block with local classes, hover and media rules,
and `deconvert.js` brings the result back to HTML for editing. What it does not
do is the delivery contract, which this wrapper adds:

  * template target: `"CSSRender": "1"` on every block carrying styleAttributes,
    dynamicGClasses or customCss (the converter emits none)
  * page target: no CSSRender; the page CSS is compiled from the blocks with
    blocks.compile_css() and written next to the output as `<name>.css`, or
    pushed with --publish
  * what the converter changes: a rule is filed under the first class in its
    selector, and the compound before that class is dropped (`body.dark .title`
    becomes `.dark .title`); a rule with no class at all (`nav a`, `:root{}`)
    goes to the stylemanager's `customCss`, which the PHP renderer never emits,
    so on a template target it is lost. Every input rule is checked and the
    rewritten or lost ones listed. --raw-css sidesteps all of it on a page target
    by shipping the original stylesheet as the page CSS instead
  * check_blocks.py over the result

Needs node on PATH and the pinned upstream clone:  python scripts/upstream.py sync
"""
import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import blocks  # noqa: E402
from check_blocks import audit  # noqa: E402

CONVERT_JS = os.path.join(os.path.dirname(HERE), 'reference', 'upstream', 'skills',
                          'greenlight-vibe', 'scripts', 'convert.js')
BLOCK = re.compile(r'<!-- wp:greenshift-blocks/element (\{.*?\}) -->', re.S)


def encode(obj):
    """convert.js's wpJsonEncode, plus the block-comment rule for `--`."""
    text = json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
    return (text.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
            .replace('--', blocks.DASH))


def run_converter(html_path):
    if not os.path.exists(CONVERT_JS):
        raise SystemExit('upstream converter not found at %s\nrun: python scripts/upstream.py sync'
                         % CONVERT_JS)
    node = shutil.which('node')
    if not node:
        raise SystemExit('node is not on PATH; the converter is a zero-dependency node script')
    proc = subprocess.run([node, CONVERT_JS, html_path], capture_output=True, text=True,
                          encoding='utf-8')
    if proc.returncode != 0:
        raise SystemExit('convert.js failed:\n' + proc.stderr)
    return proc.stdout


def apply_target(markup, target):
    """Add or strip CSSRender per target, re-encoding only the blocks that change."""
    def fix(m):
        attrs = json.loads(m.group(1).replace(blocks.DASH, '--'))
        styled = any(k in attrs for k in ('styleAttributes', 'dynamicGClasses'))
        if target == 'page':
            attrs.pop('CSSRender', None)
        elif styled:
            attrs['CSSRender'] = blocks.CSSRENDER
        # every block is re-encoded: the converter leaves `--` unescaped inside the
        # comment JSON, which WordPress tolerates and this skill's checks do not
        return '<!-- wp:greenshift-blocks/element %s -->' % encode(attrs)
    return BLOCK.sub(fix, markup)


# ---------------------------------------------------------------------------
# the converter's selector blind spot
# ---------------------------------------------------------------------------

def input_css(html):
    return '\n'.join(re.findall(r'<style[^>]*>(.*?)</style>', html, re.S | re.I))


def selectors_in(css):
    """Every selector list in the stylesheet, media queries descended into."""
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    out = []
    depth_stack = []
    i, n = 0, len(css)
    buf = ''
    while i < n:
        ch = css[i]
        if ch == '{':
            head = buf.strip()
            buf = ''
            if head.startswith('@'):
                depth_stack.append(head)        # at-rule: descend
            else:
                out.append(head)
                # skip the declaration block
                j = css.find('}', i)
                i = j if j != -1 else n
        elif ch == '}':
            if depth_stack:
                depth_stack.pop()
            buf = ''
        else:
            buf += ch
        i += 1
    return [s for s in out if s]


def rule_report(html, target):
    """(lost, rewritten): selectors the converter cannot deliver as written.

    Verified against the renderer: a class-led rule survives even when the class
    is on no block (it rides in dynamicGClasses), so the only true losses are
    rules with no class at all, and only where customCss is not compiled.
    """
    lost, rewritten = [], []
    for selector_list in selectors_in(input_css(html)):
        for selector in selector_list.split(','):
            selector = selector.strip()
            if not selector:
                continue
            first = re.search(r'\.([a-zA-Z_-][a-zA-Z0-9_-]*)', selector)
            if not first:
                if target != 'page':            # customCss: editor-only on templates
                    lost.append(selector)
                continue
            head = selector[:first.start()]
            if head and not re.search(r'[\s>+~]$', head):
                rewritten.append('%s  ->  %s' % (selector, selector[first.start():]))
    return lost, rewritten


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('input')
    ap.add_argument('-o', '--output', help='block markup file (default: output/<name>.html)')
    ap.add_argument('--target', choices=('template', 'page'), default='page')
    ap.add_argument('--raw-css', action='store_true',
                    help='page target: ship the input <style> CSS as the page CSS verbatim')
    ap.add_argument('--publish', metavar='TITLE', help='page target: create a draft page')
    ap.add_argument('--slug')
    args = ap.parse_args()

    html = io.open(args.input, encoding='utf-8').read()
    markup = apply_target(run_converter(args.input), args.target)
    name = os.path.splitext(os.path.basename(args.input))[0]
    out_path = args.output or os.path.join('output', name + '.html')
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    io.open(out_path, 'w', encoding='utf-8', newline='\n').write(markup)
    print('blocks  ', out_path, '(%d blocks)' % len(BLOCK.findall(markup)))

    css = None
    if args.target == 'page':
        css = input_css(html) if args.raw_css else blocks.compile_css(markup)
        css_path = os.path.splitext(out_path)[0] + '.css'
        io.open(css_path, 'w', encoding='utf-8', newline='\n').write(css)
        print('page css', css_path, '(%d bytes, %s)' % (len(css), 'raw stylesheet' if args.raw_css else 'compiled'))

    lost, rewritten = rule_report(html, args.target)
    if rewritten and not args.raw_css:
        print('\n%d rule(s) rewritten (compound before the first class dropped):' % len(rewritten))
        for s in rewritten:
            print('   ', s)
        if args.target == 'page':
            print('    -> --raw-css ships the original stylesheet instead')
    if lost:
        print('\n%d class-less rule(s) land in customCss, which never renders on a '
              'template target:' % len(lost))
        for s in lost:
            print('   ', s)
        print('    -> move these into a stylebook class; the part is site-wide anyway')

    seen, problems = audit(out_path, args.target)
    print('\ncheck_blocks: %d blocks, %d problem(s)' % (seen, len(problems)))
    for p in problems:
        print('   ', p)

    if args.publish:
        if args.target != 'page':
            raise SystemExit('--publish is for page targets; template parts are patched, not created')
        from wp_api import WP
        wp = WP()
        page = wp.create_page(args.publish, args.slug or name, markup)
        wp.set_post_css(page['id'], css)
        print('\ndraft page %d  %s' % (page['id'], page.get('link')))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
