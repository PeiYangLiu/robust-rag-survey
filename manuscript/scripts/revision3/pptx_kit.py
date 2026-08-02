#!/usr/bin/env python3
"""A small PowerPoint drawing kit in the style of the reference deck.

Every figure in this paper is drawn as PowerPoint shapes and exported to vector
PDF, so the source of a figure is an editable ``.pptx`` rather than a bitmap or
a TikZ program.  The palette and geometry are lifted from the reference deck the
author supplied: panels are thin navy rectangles with a bold blue title, inner
groups carry a bold black label on the border line, data cells use the pastel
fills, and flow is shown with grey chevrons inside a panel and grey elbow
connectors between panels.

Colours were sampled from the rendered reference rather than guessed.
"""

from __future__ import annotations

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Pt

# ---------------------------------------------------------------- palette
NAVY = RGBColor(0x1D, 0x31, 0x55)      # panel borders and body text
TITLE = RGBColor(0x2E, 0x75, 0xB6)     # panel titles
GREY = RGBColor(0x7F, 0x7F, 0x7F)      # connectors
RED = RGBColor(0xC0, 0x00, 0x00)       # emphasis
BLACK = RGBColor(0x00, 0x00, 0x00)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

BLUE = RGBColor(0xDE, 0xEB, 0xF7)
GREEN = RGBColor(0xE2, 0xF0, 0xD9)
ORANGE = RGBColor(0xFB, 0xE5, 0xD6)
CREAM = RGBColor(0xEF, 0xEB, 0xD8)
WARMGREY = RGBColor(0xED, 0xE8, 0xE7)
CYAN = RGBColor(0x7E, 0xCB, 0xE3)
MUTED = RGBColor(0xDB, 0xD1, 0xCE)
SLATE = RGBColor(0x93, 0xA0, 0xB2)

EMU_IN = 914400


def inches(x: float) -> Emu:
    return Emu(int(round(x * EMU_IN)))


_A_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def _strip_theme_shadow(shape) -> None:
    """Point the shape's theme effect reference at "no effect".

    ``shadow.inherit = False`` only writes an empty ``<a:effectLst/>`` into
    ``spPr``.  Autoshapes also carry a ``<p:style>`` block whose
    ``<a:effectRef idx="2">`` names a themed drop shadow, and LibreOffice
    applies that reference regardless of the empty local effect list, so the
    white label covers meant to blend into the page picked up a visible
    shadow.  Setting the index to zero removes it at the source.
    """
    for ref in shape._element.iter(f"{_A_NS}effectRef"):
        ref.set("idx", "0")


class Deck:
    """A one-slide deck sized to the figure being drawn."""

    def __init__(self, width_in: float, height_in: float, *, g: float = 1.0):
        r"""``g`` scales geometry but not type.

        Figures are drawn in a convenient coordinate space and then emitted at
        their true printed size, so that ``\includegraphics`` never rescales
        them and a point in this file is a point on the page.  Without this the
        canvas is fitted to the text width and every label shrinks with it.
        """
        self.g = g
        self.prs = Presentation()
        self.prs.slide_width = inches(width_in * g)
        self.prs.slide_height = inches(height_in * g)
        self.slide = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        self.w, self.h = width_in, height_in

    # ---------------------------------------------------------- primitives
    def box(
        self,
        x, y, w, h,
        *,
        fill=None,
        line=NAVY,
        line_w=0.9,
        shape=MSO_SHAPE.RECTANGLE,
        radius=None,
        dash=None,
    ):
        gg = self.g
        sh = self.slide.shapes.add_shape(
            shape, inches(x * gg), inches(y * gg), inches(w * gg), inches(h * gg))
        if fill is None:
            sh.fill.background()
        else:
            sh.fill.solid()
            sh.fill.fore_color.rgb = fill
        if line is None:
            sh.line.fill.background()
        else:
            sh.line.color.rgb = line
            sh.line.width = Pt(line_w)
            if dash is not None:
                sh.line.dash_style = dash
        sh.shadow.inherit = False
        _strip_theme_shadow(sh)
        if radius is not None and shape == MSO_SHAPE.ROUNDED_RECTANGLE:
            try:
                sh.adjustments[0] = radius
            except Exception:  # noqa: BLE001
                pass
        sh.text_frame.word_wrap = True
        return sh

    def text(
        self,
        x, y, w, h,
        runs,
        *,
        size=9,
        bold=False,
        color=BLACK,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
        line_spacing=0.95,
        font="Arial",
    ):
        """``runs`` is a string, or a list of (text, dict-of-overrides)."""
        gg = self.g
        tb = self.slide.shapes.add_textbox(
            inches(x * gg), inches(y * gg), inches(w * gg), inches(h * gg))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        tf.vertical_anchor = anchor
        if isinstance(runs, str):
            runs = [(runs, {})]
        para = tf.paragraphs[0]
        para.alignment = align
        try:
            para.line_spacing = line_spacing
        except Exception:  # noqa: BLE001
            pass
        for text, over in runs:
            for k, chunk in enumerate(text.split("\n")):
                if k:
                    para = tf.add_paragraph()
                    para.alignment = over.get("align", align)
                    try:
                        para.line_spacing = line_spacing
                    except Exception:  # noqa: BLE001
                        pass
                r = para.add_run()
                r.text = chunk
                r.font.size = Pt(over.get("size", size))
                r.font.bold = over.get("bold", bold)
                r.font.name = over.get("font", font)
                r.font.color.rgb = over.get("color", color)
        return tb

    def label_on_border(self, x, y, text, *, size=9.5, color=BLACK, pad=0.045):
        """A bold caption sitting on a group's top border, as in the reference.

        The cover must be sized from the *printed* extent of the type, which is
        fixed in points, so the estimate is computed in inches and converted
        back through ``self.g``; sizing it in drawing units would let the label
        wrap as soon as geometry and type stop scaling together.
        """
        ink_in = 0.0072 * size * len(text)          # bold Arial, ~0.52 em/char
        est_w = ink_in / self.g + 2 * pad
        cap_h = (size / 72.0) * 1.45 / self.g
        cover = self.box(x, y - cap_h / 2, est_w, cap_h, fill=WHITE, line=None)
        cover.text_frame.word_wrap = False
        self.text(x + pad, y - cap_h / 2, est_w, cap_h, text, size=size, bold=True,
                  color=color, align=PP_ALIGN.LEFT)
        return est_w

    def panel(self, x, y, w, h, title, *, fill=None):
        """An outer panel: thin navy frame plus a centred bold blue title."""
        self.box(x, y, w, h, fill=fill, line=NAVY, line_w=1.1)
        # type is fixed in points while geometry scales, so the default title
        # size tracks ``g`` to keep the printed proportions of the reference
        self.text(x, y + 0.055, w, 0.26, title, size=13 * self.g, bold=True,
                  color=TITLE)
        return x + 0.10, y + 0.36, w - 0.20, h - 0.46

    def label_clearance(self, size=9.5) -> float:
        """Drawing units a border label eats above its group's top edge.

        ``label_on_border`` centres a white cover on the border, so half the
        cover sits above it.  Anything stacked directly above a labelled group
        must leave at least this much room or it will be painted over.
        """
        return (size * self.g / 72.0) * 1.45 / self.g / 2 + 0.04

    def group(self, x, y, w, h, label, *, fill=None, line=NAVY, label_color=BLACK):
        """An inner group: frame plus a label that interrupts the top border."""
        self.box(x, y, w, h, fill=fill, line=line)
        if label:
            self.label_on_border(x + 0.10, y, label, size=9.5 * self.g,
                                 color=label_color)
        return x + 0.09, y + 0.16, w - 0.18, h - 0.25

    def chevron_down(self, cx, y, *, w=0.20, h=0.17, fill=GREEN):
        sh = self.box(cx - w / 2, y, w, h, fill=fill, line=RGBColor(0xBF, 0xBF, 0xBF),
                      line_w=0.6, shape=MSO_SHAPE.DOWN_ARROW)
        return sh

    def arrow_right(self, x, y, w, *, h=0.16, fill=SLATE):
        return self.box(x, y, w, h, fill=fill, line=None, shape=MSO_SHAPE.RIGHT_ARROW)

    def connector(self, pts, *, width=1.6, color=GREY, arrow=True):
        """A polyline of axis-aligned segments, drawn as thin rectangles."""
        t = width / 72.0
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if abs(y1 - y0) < 1e-6:
                self.box(min(x0, x1), y0 - t / 2, abs(x1 - x0), t, fill=color, line=None)
            else:
                self.box(x0 - t / 2, min(y0, y1), t, abs(y1 - y0), fill=color, line=None)
        if arrow:
            (x0, y0), (x1, y1) = pts[-2], pts[-1]
            s = 0.085
            if abs(y1 - y0) < 1e-6:
                shape = MSO_SHAPE.RIGHT_TRIANGLE if x1 > x0 else MSO_SHAPE.RIGHT_TRIANGLE
                head = self.box(x1 - (s if x1 > x0 else 0), y1 - s / 2, s, s,
                                fill=color, line=None, shape=MSO_SHAPE.ISOSCELES_TRIANGLE)
                head.rotation = 90 if x1 > x0 else 270
            else:
                head = self.box(x1 - s / 2, y1 - (s if y1 > y0 else 0), s, s,
                                fill=color, line=None, shape=MSO_SHAPE.ISOSCELES_TRIANGLE)
                head.rotation = 180 if y1 > y0 else 0

    def save(self, path):
        self.prs.save(str(path))
        return path
