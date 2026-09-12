# -*- coding: utf-8 -*-
"""
check_blocks.py must fail a spacing value that skipped its token.

The bug this pins: stylebook.py defines --gt-section-pad, --gt-gap and
--gt-col-gap on the site, and a generator that hard-codes clamp() past them
leaves every one of those tokens defined and unreferenced. The page renders,
so verify.py passes; verify only computes `used - tokens`, never the reverse.
check_blocks.py never looked at a value at all. examples/generate_pages.py
overrides pad= with a literal in all five of its sections, so the pattern an
agent copies is the broken one.

    python tests/test_token_spacing.py
"""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'scripts'))
from check_blocks import audit  # noqa: E402

# `--` cannot appear literally inside block JSON, so custom properties arrive
# escaped exactly the way blocks.py emits them.
DASH = r'\u002d\u002d'


def block(style):
    attrs = (
        '{"id":"gsbp-a1b2c3d","localId":"gsbp-a1b2c3d","type":"inner","tag":"div",'
        '"CSSRender":"1","styleAttributes":{%s}}' % style
    )
    return ('<!-- wp:greenshift-blocks/element %s -->\n'
            '<div class="gsbp-a1b2c3d"></div>\n'
            '<!-- /wp:greenshift-blocks/element -->\n' % attrs)


CASES = [
    (
        'token spacing passes',
        block('"paddingTop":["var(%sgt-section-pad, clamp(3rem, 7vw, 5rem))"]' % DASH),
        False,
    ),
    (
        'zero margin is not a literal to tokenise',
        block('"marginTop":["0px"],"marginBottom":["0"]'),
        False,
    ),
    (
        'auto margin is not a literal to tokenise',
        block('"marginLeft":["auto"],"marginRight":["auto"]'),
        False,
    ),
    (
        'literal clamp() padding must fail',
        block('"paddingTop":["clamp(3.75rem, 7vw, 5.5rem)"]'),
        True,
    ),
    (
        'literal rem gap must fail',
        block('"rowGap":["0.6rem"]'),
        True,
    ),
    (
        'literal in a later responsive entry must fail',
        block('"paddingBottom":["var(%sgt-section-pad)","40px"]' % DASH),
        True,
    ),
]


def run():
    failures = 0
    tmp = tempfile.mkdtemp(prefix='gl-token-test-')
    for i, (name, markup, want_problem) in enumerate(CASES):
        path = os.path.join(tmp, 'case%d.html' % i)
        io.open(path, 'w', encoding='utf-8').write(markup)
        _, problems = audit(path)
        spacing = [p for p in problems if 'token' in p.lower()]
        got_problem = bool(spacing)
        ok = got_problem == want_problem
        print('%s %s' % ('ok  ' if ok else 'FAIL', name))
        if not ok:
            failures += 1
            print('       wanted a spacing-token problem: %s' % want_problem)
            print('       got problems: %s' % (problems or 'none'))
        elif problems and not want_problem:
            print('       (unrelated problems present: %s)' % problems)
    print('\n%d failing case(s)' % failures)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(run())
