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
  * full-bleed sections do not set width (FSE alignfull already spans)
  * nocolumncontent wraps carry the theme wide-size, not the section
"""
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from blocks import _RENDERED_ATTRS, CSSRENDER, is_theme_shell_decl  # noqa: E402

BLOCK = re.compile(r'<!-- wp:greenshift-blocks/element (\{.*?\}) -->\s*(<[^>]*>)', re.S)
ATTR = re.compile(r'([a-zA-Z_:][-\w:.]*)\s*=\s*"([^"]*)"')
# emitted by GreenLight from its own keys, or produced by the renderer itself
DERIVED = _RENDERED_ATTRS | {'id', 'style', 'decoding', 'fetchpriority', 'viewbox'}

SPACING_KEYS = {
    'padding', 'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft',
    'margin', 'marginTop', 'marginRight', 'marginBottom', 'marginLeft',
    'blockGap', 'gap', 'rowGap', 'columnGap',
}
# not design decisions, so there is no token for them to reference
SPACING_EXEMPT = {'auto', 'inherit', 'initial', 'unset', 'revert', 'normal', 'none'}
ZERO = re.compile(r'^0(\.0+)?[a-z%]*$', re.I)


def literal_spacing(style):
    """Yield (key, value) for each spacing value that references no custom property.

    A hard-coded length is not wrong on its own; it is wrong because the stylebook
    already defines the rhythm. Overriding it leaves --gt-section-pad and friends
    defined and unreferenced, which verify.py cannot see: it only computes
    `used - tokens`, so a token nothing uses is indistinguishable from a healthy one.
    """
    for key, raw in (style or {}).items():
        if key not in SPACING_KEYS:
            continue
        for value in (raw if isinstance(raw, list) else [raw]):
            if not isinstance(value, str):
                continue
            text = value.strip()
            if not text or 'var(' in text:
                continue
            if text.lower() in SPACING_EXEMPT or ZERO.match(text):
                continue
            yield key, text


def audit(path, target='template', check_tokens=True):
    src = io.open(path, encoding='utf-8').read()
    problems = []

    # self-closing blocks (<!-- wp:site-logo /-->) open nothing
    opens = len(re.findall(r'<!-- wp:', src)) - len(re.findall(r'<!-- wp:[^\n]*?/-->', src))
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
        # upstream's converter emits <svg> as an icon block: tag "svg", the whole
        # markup under icon.icon.svgRaw, no `type`. Its attributes are declared
        # by that key, so the checks below do not apply to it.
        is_icon = attrs.get('tag') == 'svg' and 'icon' in attrs
        if 'type' not in attrs and not is_icon:
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
        for name, value in (html_attrs.items() if not is_icon else ()):
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

        variation = attrs.get('isVariation')
        style = attrs.get('styleAttributes') or {}
        tag_name = (re.match(r'<([a-zA-Z0-9]+)', tag) or [None, ''])[1].lower()
        is_full_section = (
            variation in ('contentwrapper', 'contentcolumns')
            or (attrs.get('align') == 'full' and tag_name == 'section')
            or 'wp-section' in (html_attrs.get('class') or '').split()
        )
        if is_full_section:
            for key in ('width', 'maxWidth', 'minWidth', 'inlineSize'):
                if key in style:
                    problems.append(
                        '%s: full-bleed section sets styleAttributes.%s=%r. FSE '
                        'alignfull is already 100%% wide; put measure on the inner '
                        'nocolumncontent wrap only (reference/fse-and-greenshift.md)'
                        % (bid, key, style[key]))
            extra_css = style.get('customCSS_Extra') or ''
            if re.search(r'(^|[^\w-])(width|max-width|min-width)\s*:', extra_css):
                problems.append(
                    '%s: customCSS_Extra sets width on a full-bleed section; the '
                    'inspector cannot edit that. Use alignfull + inner wide-size'
                    % bid)
        if variation == 'nocolumncontent' and 'width' not in style:
            problems.append(
                '%s: nocolumncontent wrap missing width: '
                'var(--wp--style--global--wide-size, 1200px)' % bid)
        if style.get('customCSS_Extra') and re.search(
                r'\.wp-section\s*\{|\.wp-content-wrap\s*\{', style.get('customCSS_Extra') or ''):
            problems.append(
                '%s: copies .wp-section / .wp-content-wrap CSS; the theme and '
                'section() already own that shell' % bid)

        has_css = ('styleAttributes' in attrs or 'dynamicGClasses' in attrs
                   or 'customCss' in attrs)
        cr = attrs.get('CSSRender')
        if target == 'page' and cr is not None:
            problems.append('%s: CSSRender on a page target. Pages carry no CSSRender; '
                            'their CSS goes in the _gspb_post_css meta' % bid)
        elif target != 'page' and has_css and cr != CSSRENDER:
            problems.append('%s: CSSRender is %r, expected the string %r'
                            % (bid, cr, CSSRENDER))

        if check_tokens:
            for key, value in literal_spacing(attrs.get('styleAttributes')):
                problems.append('%s: %s is the literal %r and references no spacing '
                                'token. The stylebook owns the rhythm; hard-coding a '
                                'length here leaves its token defined and unused, and '
                                'the next scale change moves every section but this '
                                'one. Pass var(%sgt-section-pad) or define a token'
                                % (bid, key, value, '--'))


    return seen, problems


def main():
    argv = sys.argv[1:]
    target = 'template'
    check_tokens = '--no-token-check' not in argv
    argv = [a for a in argv if a != '--no-token-check']
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
        seen, problems = audit(path, target, check_tokens)
        total += len(problems)
        mark = 'ok ' if not problems else 'BAD'
        print('%s %s  %d blocks, target=%s' % (mark, path, seen, target))
        for p in problems:
            print('      ' + p)
    print('\n%d problem(s)' % total)
    return 1 if total else 0


if __name__ == '__main__':
    sys.exit(main())
