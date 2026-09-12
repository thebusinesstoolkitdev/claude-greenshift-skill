# -*- coding: utf-8 -*-
"""
The theme-shell dedup must not eat a breakpoint reset.

Dropping a shell default is only safe while the block has emitted nothing of its
own. Once an entry is kept, the block's own rule beats the theme at every width,
so a later entry matching the theme is a reset the layout needs, not a duplicate.
Dropping it silently cascades the wider value down.

    python tests/test_theme_shell.py
"""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'scripts'))
import blocks  # noqa: E402
from check_blocks import audit  # noqa: E402

TABLET = '@media (max-width:991.98px)'
MOBILE = '@media (max-width:767.98px)'


def css_for(style, classes='wp-section'):
    return blocks.compile_css(blocks.block('x', 'div', inner='', style=style, classes=classes))


def shell_flags(style, classes='wp-section'):
    md = blocks.block('x', 'div', inner='', style=style, classes=classes)
    path = os.path.join(tempfile.mkdtemp(prefix='gl-shell-'), 'p.html')
    io.open(path, 'w', encoding='utf-8').write(md)
    _, problems = audit(path)
    return [p for p in problems if 'theme shell' in p]


# (label, style, predicate on the compiled css)
CSS_CASES = [
    ('lone shell default emits nothing',
     {'marginTop': ['0px']}, lambda c: c == ''),
    ('all-shell array emits nothing',
     {'marginTop': ['0px', '0px']}, lambda c: c == ''),
    ('shell default at desktop, real value below, keeps only the real one',
     {'marginTop': ['0px', '40px']},
     lambda c: 'margin-top:40px' in c and TABLET in c and c.count('margin-top') == 1),
    ('real value at desktop keeps the tablet reset',
     {'marginTop': ['40px', '0px']},
     lambda c: 'margin-top:40px' in c and TABLET in c and 'margin-top:0px' in c),
    ('real value at desktop keeps a mid reset with mobile after it',
     {'marginTop': ['40px', '0px', '24px']},
     lambda c: ('margin-top:40px' in c and 'margin-top:0px' in c
                and 'margin-top:24px' in c and MOBILE in c)),
    ('display:flex reset survives once a real display was emitted',
     {'display': ['grid', 'flex']},
     lambda c: 'display:grid' in c and 'display:flex' in c),
]

# (label, style, classes, expect a shell problem)
CHECK_CASES = [
    ('wholly redundant declaration is flagged', {'marginTop': ['0px']}, 'wp-section', True),
    ('all-shell array is flagged', {'marginTop': ['0px', '0px']}, 'wp-section', True),
    ('mixed array is a responsive pattern, not a duplicate',
     {'marginTop': ['0px', '40px']}, 'wp-section', False),
    ('breakpoint reset is not a duplicate',
     {'marginTop': ['40px', '0px']}, 'wp-section', False),
    ('shell props off the shell class are never flagged',
     {'marginTop': ['0px']}, 'gt-thing', False),
]


def run():
    failures = 0
    for label, style, ok in CSS_CASES:
        css = css_for(style)
        good = ok(css)
        print('%s css: %s' % ('ok  ' if good else 'FAIL', label))
        if not good:
            failures += 1
            print('       got: %r' % css)
    for label, style, classes, want in CHECK_CASES:
        flags = shell_flags(style, classes)
        good = bool(flags) == want
        print('%s chk: %s' % ('ok  ' if good else 'FAIL', label))
        if not good:
            failures += 1
            print('       wanted flag=%s, got %r' % (want, flags))
    print('\n%d failing case(s)' % failures)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(run())
