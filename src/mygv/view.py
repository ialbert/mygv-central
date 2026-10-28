"""Visible window on a contig, and the map from bases to pixels."""

import math


class View:
    """1-based inclusive window `[start, end]` on one contig.

    Listeners are called after zoom, pan, or jump.
    """

    def __init__(self, name, length, start=1, end=None, MIN_SPAN=40):
        self.name = name
        self.length = length
        self.MIN_SPAN = MIN_SPAN
        self.start = 1
        self.end = length
        self.listeners = []
        self.jump(start, length if end is None else end)

    @property
    def span(self):
        return self.end - self.start + 1

    def zoom(self, factor, anchor):
        """Zoom by `factor` around `anchor`. Factor 2 shows half as many bases."""
        if factor <= 0 or self.span <= 0:
            return
        span = min(max(self.span / factor, self.MIN_SPAN), self.length)
        if int(round(span)) == self.span:
            return
        frac = (anchor - self.start) / self.span
        self._place(anchor - frac * span, span)
        self._notify()

    def pan(self, delta):
        """Slide the window by `delta` bases."""
        self._place(self.start + delta, self.span)
        self._notify()

    def jump(self, start, end=None):
        """Replace the window. A missing end jumps to a single base."""
        if end is None:
            end = start
        if end < start:
            start, end = end, start
        self._place(start, end - start + 1)
        self._notify()

    def _place(self, start, span):
        span = int(round(span))
        span = max(1, min(span, self.length))
        if self.length >= self.MIN_SPAN:
            span = max(self.MIN_SPAN, span)
        start = int(round(start))
        if start < 1:
            start = 1
        end = start + span - 1
        if end > self.length:
            end = self.length
            start = max(1, end - span + 1)
        self.start = start
        self.end = end

    def _notify(self):
        for fn in self.listeners:
            fn()


class Scale:
    """Map between the current window and a pixel width. Not stored on the view."""

    def __init__(self, view, width):
        self.view = view
        self.width = width

    def to_x(self, bp):
        if self.width <= 0 or self.view.span <= 0:
            return 0.0
        return (bp - self.view.start) / self.view.span * self.width

    def to_bp(self, x):
        if self.width <= 0 or self.view.span <= 0:
            return float(self.view.start)
        return self.view.start + x / self.width * self.view.span


def ticks(start, end, width, min_px=80):
    """Major tick positions as `(bp, label)`, about `min_px` apart.

    The step is 1, 2, or 5 times a power of ten. A step of 1 marks every base.
    """
    span = end - start + 1
    if span <= 0 or width <= 0:
        return []
    step = _step(span / max(width / min_px, 1))
    bp = ((start + step - 1) // step) * step
    out = []
    while bp <= end:
        out.append((bp, f"{bp:,}"))
        bp += step
    return out


def human_bp(n):
    """Short label for a base count, such as `800 bp` or `10 kb`."""
    n = max(0, int(round(n)))
    if n < 1000:
        return f"{n} bp"
    for unit, size in (("Gb", 1_000_000_000), ("Mb", 1_000_000), ("kb", 1000)):
        if n < size:
            continue
        value = n / size
        if value >= 10:
            text = str(int(round(value)))
        else:
            text = f"{value:.1f}".rstrip("0").rstrip(".")
        return f"{text} {unit}"
    return f"{n} bp"


def _step(raw):
    if raw <= 1:
        return 1
    exp = math.floor(math.log10(raw))
    frac = raw / 10**exp
    if frac <= 1:
        nice = 1
    elif frac <= 2:
        nice = 2
    elif frac <= 5:
        nice = 5
    else:
        nice = 10
    return int(nice * 10**exp)
