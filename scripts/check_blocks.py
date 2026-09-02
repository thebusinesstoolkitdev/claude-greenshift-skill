# -*- coding: utf-8 -*-
"""
Audit generated block markup against the format rules, before it is pushed.

verify.py looks at a rendered page and cannot see any of this: a page with
undeclared attributes renders perfectly and only breaks when somebody opens it
in the editor, at which point Gutenberg offers "Attempt recovery" and recovery
deletes the attribute. An id lost that way silently kills every anchor link
pointing at that section.

    python scripts/check_blocks.py output/home.html
    python scripts/check_blocks.py output/*.html --target page

Checks, all of them things that have actually shipped broken:
  * every HTML attribute is reachable from the block JSON
  * no raw `id` attribute (it is the `anchor` key)
  * `type` is present on every block
  * `id` equals `localId`, and the id appears in the HTML class
  * CSSRender matches the target: "1" on template parts, absent on pages
  * no literal `--` inside block JSON
  * block comments balance
"""
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from blocks import _RENDERED_ATTRS, CSSRENDER  # noqa: E402

BLOCK = re.compile(r'<!-- wp:greenshift-blocks/element (\{.*?\}) -->\s*(<[^>]*>)', re.S)
ATTR = re.compile(r'([a-zA-Z_:][-\w:.]*)\s*=\s*"([^"]*)"')
# emitted by Greenshift from its own keys, or produced by the renderer itself
DERIVED = _RENDERED_ATTRS | {'id', 'style', 'decoding', 'fetchpriority', 'viewbox'}


def audit(path, target='template'):
    src = io.open(path, encoding='utf-8').read()
    problems = []

    opens = len(re.findall(r'<!-- wp:', src))
    closes = len(re.findall(r'<!-- /wp:', src))
    if opens != closes:
        problems.append('block comments unbalanced: %d open, %d close' % (opens, closes))

    seen = 0
    for m in BLOCK.finditer(src):
        seen += 1
        raw, tag = m.group(1), m.group(2)
        if '--' in raw:
            problems.append('literal -- inside block JSON, breaks the HTML comment')
        try:
            attrs = json.loads(raw.replace('\\u002d\\u002d', '--'))
        except ValueError as exc:
            problems.append('unparseable block JSON: %s' % str(exc)[:60])
            continue

        bid = attrs.get('id', '?')
        if 'type' not in attrs:
            problems.append('%s: no `type` (text/inner/no); deconvert reads it as inner '
                            'and a text block loses its textContent' % bid)
        if attrs.get('localId') and attrs['localId'] != bid:
            problems.append('%s: localId %s does not match id' % (bid, attrs['localId']))

        html_attrs = dict(ATTR.findall(tag))
        # a stylemanager block is an empty carrier for CSS and scripts; upstream's
        # own example emits <div></div> with no class, so it has no id to carry
        is_style_manager = attrs.get('isVariation') == 'stylemanager'
        if bid != '?' and not is_style_manager and bid not in html_attrs.get('class', ''):
            problems.append('%s: id missing from the HTML class attribute' % bid)

        # formAttributes is a declaration too: it is where a control's type,
        # name, placeholder and required are specified
        declared = {d.get('name') for d in attrs.get('dynamicAttributes') or []}
        declared |= set(attrs.get('formAttributes') or {})
        for name, value in html_attrs.items():
            low = name.lower()
            if low == 'id':
                if attrs.get('anchor') != value:
                    problems.append(
                        '%s: raw id="%s" with no matching anchor key. Gutenberg flags the '
                        'block invalid and recovery deletes the id, killing every anchor '
                        'link to it. Pass anchor=' % (bid, value))
                continue
            if low in DERIVED or name in declared:
                continue
            problems.append('%s: attribute %s="%s" is in the HTML but declared nowhere in '
                            'the JSON; recovery will strip it' % (bid, name, value[:24]))

        if is_style_manager:
            names = []
            for cls in attrs.get('dynamicGClasses') or []:
                value, css = cls.get('value') or cls.get('id'), cls.get('css', '')
                if not value:
                    problems.append('%s: stylemanager class without a value' % bid)
                    continue
                names.append(value)
                mentioned = css + ''.join(s.get('css', '') for s in cls.get('selectors') or [])
                if ('.' + value) not in mentioned:
                    problems.append('%s: local class %s has css that never mentions '
                                    '.%s, it styles nothing' % (bid, value, value))
                if cls.get('type') != 'local':
                    problems.append('%s: local class %s lacks type:"local"; the short '
                                    'shape renders but deconvert.js and the class manager '
                                    'do not read it. Use blocks.local_classes()'
                                    % (bid, value))
            listed = set((html_attrs.get('class') or '').split())
            if set(names) != listed:
                problems.append('%s: stylemanager carrier class="%s" does not list its '
                                'classes %s' % (bid, ' '.join(sorted(listed)), names))

        if target != 'page':
            # the PHP renderer emits dynamicGClasses css and styleAttributes
            # properties; these two fields are compiled by the editor only
            if attrs.get('customCss'):
                problems.append('%s: customCss on a template target never renders '
                                '(PHP CSSRender ignores it); move it to a stylebook '
                                'class or into a local class string' % bid)
            if (attrs.get('styleAttributes') or {}).get('customCSS_Extra'):
                problems.append('%s: styleAttributes.customCSS_Extra on a template '
                                'target never renders; same fix' % bid)

        has_css = ('styleAttributes' in attrs or 'dynamicGClasses' in attrs
                   or 'customCss' in attrs)
        cr = attrs.get('CSSRender')
        if target == 'page' and cr is not None:
            problems.append('%s: CSSRender on a page target. Pages carry no CSSRender; '
                            'their CSS goes in the _gspb_post_css meta' % bid)
        elif target != 'page' and has_css and cr != CSSRENDER:
            problems.append('%s: CSSRender is %r, expected the string %r'
                            % (bid, cr, CSSRENDER))

    return seen, problems


def main():
    argv = sys.argv[1:]
    target = 'template'
    if '--target' in argv:
        i = argv.index('--target')
        target = argv[i + 1] if i + 1 < len(argv) else 'template'
        del argv[i:i + 2]                 # or the value is read as a filename
    args = [a for a in argv if not a.startswith('-')]
    if target not in ('template', 'page'):
        print('--target must be template or page, got %r' % target)
        return 2
    if not args:
        print(__doc__.strip().split('\n\n')[2])
        return 2
    total = 0
    for path in args:
        seen, problems = audit(path, target)
        total += len(problems)
        mark = 'ok ' if not problems else 'BAD'
        print('%s %s  %d blocks, target=%s' % (mark, path, seen, target))
        for p in problems:
            print('      ' + p)
    print('\n%d problem(s)' % total)
    return 1 if total else 0


if __name__ == '__main__':
    sys.exit(main())
