# -*- coding: utf-8 -*-
"""Theme-shell CSS must not be re-emitted on every section.

The bug this pins: section() and container() used to copy the GreenLight theme's
.wp-section / .wp-content-wrap rules onto every block as styleAttributes.
compile_css() then shipped a second copy of the theme in _gspb_post_css. Agents
following upstream's "use next styles for sections" did the same in a <style>
tag. The design CSS was fine; the extra copy was not.

    python tests/test_css_hygiene.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'scripts'))
import blocks  # noqa: E402
from check_blocks import audit  # noqa: E402

blocks.set_backend('greenlight')
blocks.set_target('page')


def _write(tmp, name, markup):
    path = os.path.join(tmp, name)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(markup)
    return path


def run():
    import tempfile
    tmp = tempfile.mkdtemp(prefix='gl-css-hygiene-')
    failures = 0

    def check(name, ok, detail=''):
        nonlocal failures
        print('%s %s' % ('ok  ' if ok else 'FAIL', name))
        if not ok:
            failures += 1
            if detail:
                print('       ' + detail)

    # section() only emits vertical pad (+ optional bg). Theme owns the rest.
    markup = blocks.section('hygiene-sec', blocks.heading('hygiene-h', 2, 'Hello'),
                            bg='#fbf6ec')
    css = blocks.compile_css(markup)
    check('section() compile_css has no display:flex',
          'display:flex' not in css.replace(' ', ''),
          css)
    check('section() compile_css keeps padding-top',
          'padding-top' in css, css)
    check('section() compile_css keeps background',
          'background-color:#fbf6ec' in css.replace(' ', ''),
          css)
    check('section() compile_css has no side-pad var',
          '--wp--spacing--side' not in css, css)

    path = _write(tmp, 'section.html', markup)
    _, problems = audit(path, target='page')
    shell = [p for p in problems if 'theme shell' in p]
    check('section() audit has no theme-shell problems',
          not shell, str(shell))

    # container() emits no style unless width is an override. Inner is an
    # unstyled text block so compile_css of the wrapper is actually empty.
    inner = blocks.block('hygiene-in', 'p', text='In')
    bare = blocks.container('hygiene-wrap', inner)
    wrapper_json = bare.split('-->', 1)[0]
    check('container() default has no styleAttributes',
          'styleAttributes' not in wrapper_json, wrapper_json[-180:])
    css = blocks.compile_css(bare)
    check('container() default compile_css is empty',
          css == '', css)

    wide = blocks.container('hygiene-wide', blocks.heading('hygiene-h3', 3, 'Wide'),
                            width='1000px')
    css = blocks.compile_css(wide)
    check('container(width=) keeps the override',
          '1000px' in css, css)
    check('container(width=) does not emit display:flex',
          'display:flex' not in css.replace(' ', ''),
          css)

    # Already-generated markup that copied the theme shell still gets slimed
    bloated = blocks.block(
        'shell-old', 'section', classes='wp-section', alignfull=True,
        style={
            'display': ['flex'], 'justifyContent': ['center'],
            'flexDirection': ['column'], 'alignItems': ['center'],
            'paddingLeft': ['var(--wp--spacing--side, min(3vw, 20px))'],
            'paddingRight': ['min(3vw, 20px)'],
            'paddingTop': ['var(--gt-section-pad)'],
            'paddingBottom': ['var(--gt-section-pad)'],
            'marginTop': ['0px'], 'position': ['relative'],
        })
    css = blocks.compile_css(bloated)
    check('compile_css drops theme-shell decls from old markup',
          'display:flex' not in css.replace(' ', '')
          and 'position:relative' not in css.replace(' ', ''),
          css)
    check('compile_css keeps real pad from old markup',
          'padding-top:var(--gt-section-pad)' in css.replace(' ', ''),
          css)

    path = _write(tmp, 'bloated.html', bloated)
    _, problems = audit(path, target='page')
    shell = [p for p in problems if 'theme shell' in p]
    check('audit flags theme-shell decls on old markup',
          len(shell) >= 4, str(problems))

    # Stylemanager that pasted upstream's section CSS
    pasted = (
        '.wp-section{display:flex;justify-content:center;flex-direction:column;'
        'align-items:center;padding-left:var(--wp--spacing--side, min(3vw, 20px));'
        'padding-right:var(--wp--spacing--side, min(3vw, 20px));'
        'padding-top:4rem;margin-top:0px;position:relative;}'
        '.wp-content-wrap{max-width:100%;width:var(--wp--style--global--wide-size, 1200px);}'
        '.hero-title{font-size:48px}'
    )
    slim = blocks.slim_stylesheet(pasted)
    check('slim_stylesheet drops empty .wp-content-wrap theme rule',
          '.wp-content-wrap' not in slim, slim)
    check('slim_stylesheet keeps section padding-top',
          'padding-top:4rem' in slim.replace(' ', ''), slim)
    check('slim_stylesheet keeps a real design class',
          '.hero-title{font-size:48px}' in slim.replace(' ', ''), slim)
    check('slim_stylesheet drops display:flex from .wp-section',
          'display:flex' not in slim.replace(' ', ''), slim)

    print('\n%d failing case(s)' % failures)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(run())
