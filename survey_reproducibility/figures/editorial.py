"""Shared 2D academic vector primitives (V16 light pastel scholarly edition)."""
from art import *

def txt(a, n, x, y, w, text, size=11, bold=False, color='ink', align='left', italic=False, serif=False):
    lines = len(text.split('\n'))
    h = lines * size * 1.15 + 2.5
    return a.txt(n, x, y, w, h, text, size, bold, color, align, italic=italic, serif=serif)

def title(a, n, x, y, w, text, color='ink', size=17, align='left'):
    return txt(a, n, x, y, w, text, size, True, color, align=align, serif=True)

def arrow(a, n, x1, y1, x2, y2, color='ink', width=1.4, dash=False):
    return a.line(n, (x1, y1), (x2, y2), color, width, arrow=True, dash=dash)

def pill(a, n, x, y, w, h, text, fill='white', stroke='line', color='ink', size=10.5, bold=True, rounding=.32):
    a.rect(n, x, y, w, h, fill, stroke, .85, rounding)
    th = len(text.split('\n')) * size * 1.15
    ty = y + (h - th) / 2 - 0.5
    a.txt(n + '_txt', x + 4, ty, w - 8, th + 2.5, text, size, bold, color, 'center')

def folded_doc(a, n, x, y, w, h, stroke='blue', fill='bl', fold=12, dash=False):
    a.path(n, [(x, y), (x + w - fold, y), (x + w, y + fold), (x + w, y + h), (x, y + h)], stroke, 1.0, fill, True, dash=dash)
    a.path(n + '_fold', [(x + w - fold, y), (x + w - fold, y + fold), (x + w, y + fold)], stroke, 0.9, 'white', True, dash=dash)
    a.boxes[n] = [x, y, w, h]

def doc_mini_icon(a, n, x, y, w=14, h=18, color='blue', fill='white'):
    fold = 4.5
    a.path(n, [(x, y), (x + w - fold, y), (x + w, y + fold), (x + w, y + h), (x, y + h)], color, 1.0, fill, True)
    a.path(n + '_f', [(x + w - fold, y), (x + w - fold, y + fold), (x + w, y + fold)], color, 0.8, 'white', True)
    for i in range(3):
        a.line(n + f'_l{i}', (x + 3, y + 6.5 + i * 3.5), (x + w - 3, y + 6.5 + i * 3.5), color, 0.75)

def shield_icon(a, n, x, y, s=18, color='blue', fill='white'):
    w = s * 0.88
    h = s
    a.path(n, [
        (x, y - h * 0.5),
        (x + w * 0.5, y - h * 0.34),
        (x + w * 0.5, y + h * 0.06),
        (x, y + h * 0.5),
        (x - w * 0.5, y + h * 0.06),
        (x - w * 0.5, y - h * 0.34),
    ], color, 1.15, fill, True)
    a.path(n + '_v', [(x - 3.5, y + 0.3), (x - 0.8, y + 3.0), (x + 4.0, y - 2.4)], color, 1.35)

def router_icon(a, n, x, y, r=8, color='purple'):
    a.circle(n + '_c', x - 4, y, 2.8, 'white', color, 1.1)
    for dy in [-6, 0, 6]:
        a.line(n + f'_l{dy}', (x - 1, y), (x + 5, y + dy), color, 1.0)
        a.circle(n + f'_d{dy}', x + 6.5, y + dy, 2.0, color, None, 0)

def check_badge(a, n, x, y, r=7.5, color='teal', fg='white'):
    a.circle(n, x, y, r, color, None, 0)
    a.path(n + '_v', [(x - r * 0.44, y + r * 0.02), (x - r * 0.08, y + r * 0.38), (x + r * 0.46, y - r * 0.34)], fg, 1.45)

def cross_badge(a, n, x, y, r=7.5, color='red', fg='white'):
    a.circle(n, x, y, r, color, None, 0)
    d = r * 0.36
    a.line(n + '_1', (x - d, y - d), (x + d, y + d), fg, 1.4)
    a.line(n + '_2', (x + d, y - d), (x - d, y + d), fg, 1.4)

def bang_badge(a, n, x, y, r=7.5, color='red', fg='white'):
    a.circle(n, x, y, r, color, None, 0)
    a.line(n + '_bar', (x, y - r * 0.46), (x, y + r * 0.08), fg, 1.6)
    a.circle(n + '_dot', x, y + r * 0.36, 1.0, fg, None, 0)

def magnifier_icon(a, n, x, y, r=6.5, color='teal', fill='white'):
    a.circle(n, x, y, r, fill, color, 1.4)
    a.line(n + '_h', (x + r * 0.68, y + r * 0.68), (x + r * 1.42, y + r * 1.42), color, 1.8)

def bubble_icon(a, n, x, y, w=13, h=10, color='purple', fill='white'):
    a.rect(n, x, y, w, h, fill, color, 1.1, .2)
    a.path(n + '_t', [(x + 3, y + h), (x + 1.5, y + h + 3.2), (x + 6.5, y + h)], color, 0.9, fill, True)

def clock_icon(a, n, x, y, r=6.0, color='blue'):
    a.circle(n, x, y, r, 'white', color, 1.25)
    a.path(n + '_h', [(x, y - r * 0.55), (x, y), (x + r * 0.45, y + 0.8)], color, 1.15)

def target_icon(a, n, x, y, r=10, color='ink'):
    a.circle(n + '_1', x, y, r, 'white', color, 1.15)
    a.circle(n + '_2', x, y, r * 0.62, 'white', color, 1.0)
    a.circle(n + '_3', x, y, r * 0.26, color, None, 0)

def loop_icon(a, n, x, y, r=9.5, color='red'):
    pts = []
    for i in range(33):
        t = math.radians(35 + 285 * i / 32)
        pts.append((x + r * math.cos(t), y + r * math.sin(t)))
    a.path(n, pts, color, 1.5, arrow=True)
