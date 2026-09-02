# -*- coding: utf-8 -*-
"""
WCAG contrast gate for a brand palette.

Run this BEFORE writing colour tokens into the stylebook. Designers routinely hand
over muted greys and mid-tone brand colours that fail AA on a light background, catching it here means one token change instead of a site-wide retrofit later.

    python check_contrast.py --bg "#fbf6ec" --fg body:#8c8172 accent:#e27b4b
    python check_contrast.py --pairs "#ffffff on #7c8b54" "#fbf6ec on #7e5aa6"
    python check_contrast.py --fix "#8c8172" --bg "#fbf6ec"     # darken until it passes

Thresholds: 4.5 normal text, 3.0 large text (>=24px, or >=18.7px bold) and UI borders.
"""
import argparse
import colorsys


def _channel(value):
    value = value / 255
    return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4


def luminance(hex_colour):
    h = hex_colour.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def ratio(fg, bg):
    a, b = luminance(fg), luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def verdict(value, large=False):
    if value >= 7:
        return 'AAA'
    if value >= 4.5:
        return 'AA'
    if value >= 3 and large:
        return 'AA (large only)'
    if value >= 3:
        return 'FAIL text / ok for UI borders'
    return 'FAIL'


def darken_until(fg, bg, target=4.5, step=0.02):
    """Walk lightness down (or up on dark backgrounds) until the target ratio is met."""
    h = fg.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    hue, light, sat = colorsys.rgb_to_hls(r, g, b)
    direction = -1 if luminance(bg) > 0.18 else 1
    for _ in range(60):
        candidate = '#%02x%02x%02x' % tuple(
            round(c * 255) for c in colorsys.hls_to_rgb(hue, light, sat))
        if ratio(candidate, bg) >= target:
            return candidate, ratio(candidate, bg)
        light = max(0.0, min(1.0, light + direction * step))
    return None, None


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--bg', default='#ffffff', help='background colour')
    parser.add_argument('--fg', nargs='*', default=[], help='label:#hex foreground colours')
    parser.add_argument('--pairs', nargs='*', default=[], help='"#fg on #bg" pairs')
    parser.add_argument('--fix', help='suggest a passing variant of this colour')
    parser.add_argument('--target', type=float, default=4.5)
    args = parser.parse_args()

    failures = 0

    for item in args.fg:
        label, _, colour = item.rpartition(':')
        value = ratio(colour, args.bg)
        state = verdict(value)
        if value < args.target:
            failures += 1
            suggestion, new_value = darken_until(colour, args.bg, args.target)
            extra = f'  -> try {suggestion} ({new_value:.2f})' if suggestion else ''
        else:
            extra = ''
        print(f'{label or colour:<16} {colour} on {args.bg}: {value:5.2f}  {state}{extra}')

    for pair in args.pairs:
        fg, _, bg = pair.replace(' on ', '|').partition('|')
        value = ratio(fg.strip(), bg.strip())
        print(f'{fg.strip()} on {bg.strip()}: {value:5.2f}  {verdict(value)}')
        failures += value < args.target

    if args.fix:
        suggestion, value = darken_until(args.fix, args.bg, args.target)
        print(f'{args.fix} -> {suggestion} ({value:.2f} on {args.bg})' if suggestion
              else f'no passing variant of {args.fix} on {args.bg}')

    if failures:
        print(f'\n{failures} colour(s) below {args.target}:1, fix the TOKEN, not the usage.')
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
