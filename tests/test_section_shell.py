# -*- coding: utf-8 -*-
"""
The section shell is per-block styleAttributes, not a stripped duplicate.

Nothing on the front end styles `.wp-section` / `.wp-content-wrap`; the theme and
the plugin were both checked (Greenlight 2.1, gl-page-builder 3.3.7). Layout has to
travel with the block, the way the editor's own Section variation inserts it, so a
developer can change it in the inspector and a page renders without a stylebook push.
An earlier refactor stripped these declarations as "theme duplicates" and produced
full-width, un-centred sections. These cases pin the correct behaviour.

    python tests/test_section_shell.py
"""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'scripts'))
import blocks  # noqa: E402
from check_blocks import audit  # noqa: E402

WIDE = 'var(--wp--style--global--wide-size'
SIDE = '--wp--custom--spacing--side'
PAD = 'var(--wp--preset--spacing--70, 3.38rem)'


def compiled(markup):
    return blocks.compile_css(markup).replace(' ', '')


def problems_for(markup):
    path = os.path.join(tempfile.mkdtemp(prefix='gl-shell-'), 'p.html')
    io.open(path, 'w', encoding='utf-8').write(markup)
    _, problems = audit(path, target='page')
    return problems


def run():
    failures = 0

    def check(name, ok, detail=''):
        nonlocal failures
        print('%s %s' % ('ok  ' if ok else 'FAIL', name))
        if not ok:
            failures += 1
            if detail:
                print('       ' + str(detail)[:400])

    inner = blocks.heading('h', 2, 'Hello')

    sec = compiled(blocks.section('s', inner, pad=PAD))
    check('section() emits display:flex on the block', 'display:flex' in sec, sec)
    check('section() emits the theme side-padding token', SIDE in sec, sec)
    check('section() emits zero margins', 'margin-top:0px' in sec and 'margin-bottom:0px' in sec, sec)
    check('section() keeps its vertical padding', 'padding-top:var(--wp--preset--spacing--70' in sec, sec)
    check('section() never sets width', 'width:' not in sec, sec)
    check('compile_css keeps the shell (nothing stripped as a theme duplicate)',
          'display:flex' in sec and SIDE in sec, sec)

    wrap = compiled(blocks.container('c', inner))
    check('container() emits the theme wide-size variable', WIDE in wrap, wrap)
    check('container() emits max-width:100%', 'max-width:100%' in wrap, wrap)

    probs = problems_for(blocks.section('s3', blocks.container('c3', inner), pad=PAD))
    shell = [p for p in probs if 'theme shell' in p or 'duplicates the theme' in p]
    check('audit does not flag the shell on a section', not shell, shell)

    try:
        blocks.section('bad', inner, style={'width': ['1440px']})
        check('section(width=) is refused', False, 'no ValueError')
    except ValueError as exc:
        check('section(width=) is refused', 'never on the section' in str(exc), exc)

    cols = blocks.columns('cols', [inner, inner], widths=[60, 40])
    check('columns() uses the plugin column controls', 'flexWidths_Extra' in cols, cols[:300])
    # Block JSON escapes `--` as --, so count in the compiled CSS, where
    # the custom property is spelled out; it must occur once (the content area)
    # and never on the section.
    cols_css = compiled(cols)
    check('columns() puts wide-size on the content area, not the section',
          cols_css.count(WIDE) == 1, cols_css.count(WIDE))

    print('\n%d failing case(s)' % failures)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(run())
