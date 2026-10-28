"""IGV-style window: ruler, tracks, and a text panel on one shared scale."""

import sys

from PySide6.QtCore import QEvent, QPoint, QRect, Qt
from PySide6.QtGui import QColor, QFontDatabase, QPainter, QPolygon
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from pyfaidx import Fasta

from mygv import db
from mygv.gui.config import load
from mygv.view import Scale, View, human_bp, ticks

config = load()


def pan_wheel(view, event):
    """Scroll pans. One notch slides about an eighth of the window."""
    dy = event.angleDelta().y()
    dx = event.angleDelta().x()
    step = dy / 120 if dy else -dx / 120
    if step:
        view.pan(-step * view.span / config.PAN_PART)
    event.accept()


def wash(color):
    """Same base color, light enough for a strip of many columns."""
    pale = QColor(color)
    pale.setAlpha(config.COLORS.WASH)
    return pale


def pointed(x, y, w, h, right=True):
    """Bar with the 3' corners cut so that end meets in a point."""
    tip = min(h // 2, w // 2)
    x2 = x + w
    mid = y + h // 2
    if right:
        return QPolygon([
            QPoint(x, y),
            QPoint(x2 - tip, y),
            QPoint(x2, mid),
            QPoint(x2 - tip, y + h),
            QPoint(x, y + h),
        ])
    return QPolygon([
        QPoint(x + tip, y),
        QPoint(x2, y),
        QPoint(x2, y + h),
        QPoint(x + tip, y + h),
        QPoint(x, mid),
    ])


class Interval:
    def __init__(self, start, end, label, strand="."):
        self.start = start
        self.end = end
        self.label = label
        self.strand = strand

    def caption(self):
        if self.strand == "+":
            return f"{self.label}"
        if self.strand == "-":
            return f"{self.label}"
        return self.label


class SequenceTrack:
    """Color strip of the visible sequence. Letters appear once a base is wide enough.

    A window longer than `DRAW_LIMIT` is a grey bar, so a whole chromosome is not read.
    """

    def __init__(self, fa, height=26):
        self.fa = fa
        self.name = "sequence"
        self.height = height
        self._key = None
        self._seq = ""

    def sequence(self, view):
        key = (view.name, view.start, view.end)
        if key != self._key:
            self._key = key
            self._seq = self.fa[view.name][view.start - 1:view.end].seq
        return self._seq

    def paint(self, painter, scale, rect):
        view = scale.view
        if scale.width <= 0 or view.span <= 0:
            return
        top = rect.y() + 3
        height = max(4, rect.height() - 6)
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setPointSize(11)
        painter.setFont(font)
        letter = painter.fontMetrics().horizontalAdvance("G") + 2
        if scale.width / view.span >= letter:
            self._letters(painter, scale, self.sequence(view), top, height)
        elif view.span <= config.DRAW_LIMIT:
            self._colors(painter, scale, self.sequence(view), top, height)
        else:
            self._key = None
            self._seq = ""
            painter.fillRect(0, top, int(scale.width), height, wash(config.COLORS.OTHER))

    def _letters(self, painter, scale, seq, top, height):
        view = scale.view
        flags = Qt.AlignmentFlag.AlignCenter
        for i, base in enumerate(seq):
            bp = view.start + i
            x1 = int(scale.to_x(bp))
            x2 = int(scale.to_x(bp + 1))
            if x2 <= x1:
                continue
            ch = base.upper()
            color = config.COLORS.base_color(ch)
            painter.fillRect(x1, top, x2 - x1, height, wash(color))
            painter.setPen(color)
            painter.drawText(QRect(x1, top, x2 - x1, height), flags, ch)

    def _colors(self, painter, scale, seq, top, height):
        view = scale.view
        painter.setPen(Qt.PenStyle.NoPen)
        if scale.width >= view.span:
            for i, base in enumerate(seq):
                bp = view.start + i
                x1 = int(scale.to_x(bp))
                x2 = int(scale.to_x(bp + 1))
                if x2 <= x1:
                    x2 = x1 + 1
                painter.setBrush(wash(config.COLORS.base_color(base)))
                painter.drawRect(x1, top, x2 - x1, height)
            return
        width = int(scale.width)
        cols = [{} for _ in range(width)]
        for i, base in enumerate(seq):
            x = int(scale.to_x(view.start + i))
            if 0 <= x < width:
                ch = base.upper()
                cols[x][ch] = cols[x].get(ch, 0) + 1
        run_x = 0
        run = None
        for x, hist in enumerate(cols):
            base = max(hist, key=hist.get) if hist else None
            if base == run:
                continue
            if run is not None:
                painter.setBrush(wash(config.COLORS.base_color(run)))
                painter.drawRect(run_x, top, x - run_x, height)
            run_x = x
            run = base
        if run is not None:
            painter.setBrush(wash(config.COLORS.base_color(run)))
            painter.drawRect(run_x, top, width - run_x, height)

    def hit(self, bp):
        return None


class IntervalTrack:
    """Genes on one strand. A crowded window draws pixel runs."""

    def __init__(self, name, conn, view, strand, color, height=36):
        self.name = name
        self.conn = conn
        self.view = view
        self.strand = strand
        self.color = color
        self.height = height
        self.intervals = []
        self._key = None
        self._width = 0

    def _sync(self, view):
        key = (view.name, view.start, view.end)
        if key == self._key:
            return
        self._key = key
        self.intervals = []
        if self.conn is None:
            return
        rows = db.genes(self.conn, view.name, view.start, view.end, self.strand)
        for start, end, strand, label in rows:
            self.intervals.append(Interval(int(start), int(end), label, strand))

    def _dense(self, width):
        return width > 0 and len(self.intervals) > width

    def paint(self, painter, scale, rect):
        self._sync(scale.view)
        self._width = int(scale.width)
        top = rect.y() + 8
        height = max(4, rect.height() - 16)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.color)
        if self._dense(self._width):
            for x1, x2 in self._runs(scale):
                painter.drawRect(x1, top, x2 - x1, height)
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for iv in self.intervals:
            x1 = scale.to_x(iv.start)
            x2 = scale.to_x(iv.end + 1)
            w = max(config.GLYPH_PX, x2 - x1)
            right = iv.strand != "-"
            painter.drawPolygon(pointed(int(x1), top, int(w), height, right))
            label_x = max(x1, 0) + 4
            if not right:
                label_x += min(height // 2, int(w) // 2)
            if x2 - label_x > config.LABEL_PX:
                painter.setPen(config.COLORS.INK)
                painter.drawText(int(label_x), top + height - 5, iv.caption())
                painter.setPen(Qt.PenStyle.NoPen)

    def _runs(self, scale):
        """Pixel columns a gene touches, joined into contiguous bars."""
        width = int(scale.width)
        filled = bytearray(width)
        for iv in self.intervals:
            x1 = int(scale.to_x(iv.start))
            x2 = int(scale.to_x(iv.end + 1))
            if x2 <= x1:
                x2 = x1 + 1
            x1 = max(0, x1)
            x2 = min(width, x2)
            if x1 < x2:
                filled[x1:x2] = b"\x01" * (x2 - x1)
        runs = []
        run = None
        for x, bit in enumerate(filled):
            if bit and run is None:
                run = x
            elif not bit and run is not None:
                runs.append((run, x))
                run = None
        if run is not None:
            runs.append((run, width))
        return runs

    def hit(self, bp):
        self._sync(self.view)
        if self._dense(self._width):
            rows = db.genes(self.conn, self.view.name, bp, bp, self.strand) if self.conn else ()
            found = [self._line(Interval(int(a), int(b), name, strand)) for a, b, strand, name in rows]
            return "\n".join(found) if found else None
        found = [self._line(iv) for iv in self.intervals if iv.start <= bp <= iv.end]
        return "\n".join(found) if found else None

    def _line(self, iv):
        return f"{iv.caption()}  {iv.start:,}-{iv.end:,}"


class RulerTrack:
    """Tick marks for the visible window."""

    def __init__(self, height=44):
        self.name = "coordinate"
        self.height = height

    def paint(self, painter, scale, rect):
        painter.fillRect(rect, config.COLORS.PAPER)
        bottom = rect.bottom()
        painter.setPen(config.COLORS.INK)
        painter.drawLine(rect.left(), bottom, rect.right(), bottom)
        metrics = painter.fontMetrics()
        last = -10**9
        for bp, label in ticks(scale.view.start, scale.view.end, rect.width(), config.TICK_PX):
            x = int(rect.left() + scale.to_x(bp))
            painter.drawLine(x, bottom - 12, x, bottom)
            if x < last:
                continue
            painter.drawText(x + 3, bottom - 16, label)
            last = x + metrics.horizontalAdvance(label) + 10

    def hit(self, bp):
        return None


class SpanTrack:
    """Arrow across the visible window, labeled with its size."""

    def __init__(self, height=22):
        self.name = "span"
        self.height = height

    def paint(self, painter, scale, rect):
        painter.fillRect(rect, config.COLORS.PAPER)
        label = human_bp(scale.view.span)
        metrics = painter.fontMetrics()
        baseline = rect.top() + (rect.height() + metrics.ascent()) // 2 - 1
        line_y = baseline - metrics.ascent() // 2
        mw = metrics.horizontalAdvance(label)
        cx = rect.left() + (rect.width() - mw) // 2
        x0 = rect.left() + 2
        x1 = rect.right() - 2
        head = 6
        gap = 8
        painter.setPen(config.COLORS.LIGHT_INK)
        painter.drawText(cx, baseline, label)
        if cx - gap > x0 + head:
            painter.drawLine(x0 + head, line_y, cx - gap, line_y)
            painter.drawLine(x0, line_y, x0 + head, line_y - 3)
            painter.drawLine(x0, line_y, x0 + head, line_y + 3)
        if x1 - head > cx + mw + gap:
            painter.drawLine(cx + mw + gap, line_y, x1 - head, line_y)
            painter.drawLine(x1, line_y, x1 - head, line_y - 3)
            painter.drawLine(x1, line_y, x1 - head, line_y + 3)

    def hit(self, bp):
        return None


class Pane(QWidget):
    """Pan, zoom, and click. Subclasses paint and resolve what a base hits."""

    def __init__(self, view, report):
        super().__init__()
        self.view = view
        self.report = report
        self._origin = None
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.view.listeners.append(self.update)

    def scale(self):
        return Scale(self.view, max(self.width(), 1))

    def x_to_bp(self, x):
        return self.scale().to_bp(x)

    def lookup(self, bp, y):
        return None

    def wheelEvent(self, event):
        pan_wheel(self.view, event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            factor = config.ZOOM
        elif event.button() == Qt.MouseButton.RightButton:
            factor = 1 / config.ZOOM
        else:
            return
        if self._origin is not None:
            self._origin = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        bp = self.x_to_bp(event.position().x())
        mid = (self.view.start + self.view.end) / 2
        self.view.pan(bp - mid)
        self.view.zoom(factor, bp)
        event.accept()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._origin = (event.position().x(), self.view.start, self.view.end)
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        self._emit(event.position().x(), event.position().y())

    def mouseMoveEvent(self, event):
        x = event.position().x()
        y = event.position().y()
        if self._origin is not None:
            span = self._origin[2] - self._origin[1] + 1
            delta = -(x - self._origin[0]) / max(self.scale().width, 1) * span
            self.view.start = self._origin[1]
            self.view.end = self._origin[2]
            self.view.pan(delta)
        self._emit(x, y)

    def mouseReleaseEvent(self, event):
        self._origin = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def _emit(self, x, y):
        bp = round(self.x_to_bp(x))
        self.report(bp, self.lookup(bp, y))


def track_index(tracks, y):
    if not tracks or y < 0:
        return 0
    top = 0
    for i, track in enumerate(tracks):
        if y < top + track.height:
            return i
        top += track.height
    return len(tracks) - 1


class Gutter(QWidget):
    """Left panel for track names. Drag a row to reorder it."""

    def __init__(self, view, tracks, on_change):
        super().__init__()
        self.view = view
        self.tracks = tracks
        self.on_change = on_change
        self._drag = None
        self._insert = None
        self.setMinimumWidth(110)
        self.setMinimumHeight(sum(track.height for track in tracks) or 80)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def wheelEvent(self, event):
        pan_wheel(self.view, event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), config.COLORS.PAPER)
        metrics = painter.fontMetrics()
        y = 0
        for i, track in enumerate(self.tracks):
            if i == self._drag:
                painter.fillRect(0, y, self.width(), track.height, config.COLORS.WHITE)
            self._grip(painter, y, track.height, i == self._drag)
            baseline = y + (track.height + metrics.ascent()) // 2 - 1
            name = metrics.elidedText(track.name, Qt.TextElideMode.ElideRight, max(self.width() - 22, 8))
            painter.setPen(config.COLORS.INK)
            painter.drawText(16, baseline, name)
            y += track.height
            painter.setPen(config.COLORS.LINE)
            painter.drawLine(0, y, self.width(), y)
        if self._drag is not None and self._insert is not None:
            mark = sum(track.height for track in self.tracks[: self._insert])
            painter.setPen(config.COLORS.INK)
            painter.drawLine(0, mark, self.width(), mark)
        painter.end()

    def _grip(self, painter, y, height, active):
        painter.setPen(config.COLORS.INK if active else config.COLORS.LIGHT_INK)
        cx = 7
        cy = y + height // 2
        for dy in (-4, 0, 4):
            painter.drawPoint(cx - 2, cy + dy)
            painter.drawPoint(cx + 2, cy + dy)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._drag = track_index(self.tracks, event.position().y())
        self._insert = self._drag
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        self.update()

    def mouseMoveEvent(self, event):
        if self._drag is None:
            return
        self._insert = track_index(self.tracks, event.position().y())
        self.update()

    def mouseReleaseEvent(self, event):
        if self._drag is None:
            return
        src = self._drag
        dst = self._insert
        self._drag = None
        self._insert = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        if dst is not None and dst != src:
            track = self.tracks.pop(src)
            self.tracks.insert(dst, track)
            self.on_change()
        self.update()


class TrackPane(Pane):
    """One scale, one list of tracks."""

    def __init__(self, view, tracks, report):
        super().__init__(view, report)
        self.tracks = tracks
        self.setMinimumHeight(sum(track.height for track in tracks) or 80)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), config.COLORS.WHITE)
        scale = self.scale()
        y = 0
        for track in self.tracks:
            painter.save()
            painter.translate(0, y)
            track.paint(painter, scale, QRect(0, 0, scale.width, track.height))
            painter.restore()
            y += track.height
            painter.setPen(config.COLORS.LINE)
            painter.drawLine(0, y, self.width(), y)
        painter.end()

    def lookup(self, bp, y):
        top = 0
        for track in self.tracks:
            if top <= y < top + track.height:
                return track.hit(bp)
            top += track.height
        return None


class Browser(QMainWindow):
    def __init__(self, fa, contig, conn):
        super().__init__()
        self.fa = fa
        self.view = View(contig.name, len(contig), MIN_SPAN=config.MIN_SPAN)
        self.setWindowTitle(contig.name)
        self.resize(980, 520)

        self.goto = QLineEdit()
        self.goto.setPlaceholderText("1234 or 1000-2000")
        self.goto.setFixedWidth(180)
        self.goto.returnPressed.connect(self.go)
        self.range = QLabel()

        zoom_out = QPushButton("Zoom out")
        zoom_out.clicked.connect(self.zoom_out)
        zoom_in = QPushButton("Zoom in")
        zoom_in.clicked.connect(self.zoom_in)
        go = QPushButton("Go")
        go.clicked.connect(self.go)

        tools = QHBoxLayout()
        tools.setContentsMargins(0, 0, 0, 0)
        self.chrom = QComboBox()
        for name in fa.keys():
            self.chrom.addItem(name)
        self.chrom.setCurrentText(contig.name)
        self.chrom.currentTextChanged.connect(self.use_contig)
        tools.addWidget(self.goto)
        tools.addWidget(go)
        tools.addWidget(zoom_out)
        tools.addWidget(zoom_in)
        tools.addWidget(self.range)
        tools.addStretch(1)
        bar = QWidget()
        bar.setLayout(tools)
        bar.setFixedHeight(32)
        self.chrom.setFixedHeight(32)

        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self._detail = ""
        self.detail.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.detail.setMinimumHeight(100)
        self.set_detail("Navigate with WASD keyboard")

        tracks = [
            SpanTrack(),
            RulerTrack(),
            SequenceTrack(fa),
            IntervalTrack("gene(+)", conn, self.view, "+", config.COLORS.PLUS),
            IntervalTrack("gene(-)", conn, self.view, "-", config.COLORS.MINUS),
        ]
        self.tracks = TrackPane(self.view, tracks, self.report)
        self.gutter = Gutter(self.view, tracks, self.tracks.update)

        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(6)
        side_layout.addWidget(self.chrom)
        side_layout.addWidget(self.gutter, 1)

        main = QWidget()
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(6)
        main_layout.addWidget(bar)
        main_layout.addWidget(self.tracks, 1)

        browser = QSplitter(Qt.Orientation.Horizontal)
        browser.addWidget(side)
        browser.addWidget(main)
        browser.setStretchFactor(0, 0)
        browser.setStretchFactor(1, 1)
        browser.setChildrenCollapsible(False)
        browser.setSizes([140, 820])

        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(browser)
        split.addWidget(self.detail)
        split.setStretchFactor(0, 1)
        split.setChildrenCollapsible(False)
        split.setSizes([320, 140])

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.addWidget(split, 1)
        self.setCentralWidget(root)

        self.view.listeners.append(self.show_range)
        self.show_range()
        self.tracks.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.tracks.setFocus()
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def use_contig(self, name):
        contig = self.fa[name]
        self.view.name = contig.name
        self.view.length = len(contig)
        self.setWindowTitle(contig.name)
        self.view.jump(1, len(contig))

    def zoom_in(self):
        self.view.zoom(config.ZOOM, self.center())

    def zoom_out(self):
        self.view.zoom(1 / config.ZOOM, self.center())

    def drag(self, direction):
        """Slide the window as a horizontal drag would. +1 drags to the right."""
        self.view.pan(-direction * self.view.span / config.PAN_PART)

    def keyPressEvent(self, event):
        if self.navigate(event):
            event.accept()
            return
        super().keyPressEvent(event)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress and not self.typing() and self.navigate(event):
            return True
        return super().eventFilter(obj, event)

    def typing(self):
        """True while a locus or contig field has focus."""
        widget = QApplication.focusWidget()
        while widget is not None:
            if isinstance(widget, (QLineEdit, QComboBox)):
                return True
            widget = widget.parentWidget()
        return False

    def closeEvent(self, event):
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        super().closeEvent(event)

    def navigate(self, event):
        """+ / W zoom in, - / S zoom out, A drags left, D drags right."""
        mods = event.modifiers()
        mods &= ~Qt.KeyboardModifier.ShiftModifier
        mods &= ~Qt.KeyboardModifier.KeypadModifier
        if mods:
            return False
        key = event.key()
        text = event.text()
        if key in (Qt.Key.Key_Plus, Qt.Key.Key_W) or text == "+":
            self.zoom_in()
            return True
        if key in (Qt.Key.Key_Minus, Qt.Key.Key_S) or text == "-":
            self.zoom_out()
            return True
        if key == Qt.Key.Key_A:
            self.drag(-1)
            return True
        if key == Qt.Key.Key_D:
            self.drag(1)
            return True
        return False

    def center(self):
        return (self.view.start + self.view.end) / 2

    def show_range(self):
        self.range.setText(f"{self.view.start:,} - {self.view.end:,}")

    def set_detail(self, text):
        if text == self._detail:
            return
        self._detail = text
        self.detail.setPlainText(text)

    def report(self, bp, hit):
        bp = min(max(int(round(bp)), 1), self.view.length)
        line = f"{self.view.name}:{bp:,}"
        base = self.fa[self.view.name][bp - 1:bp].seq
        if base:
            line += f"  {base}"
        lines = [line]
        if hit:
            lines.append(hit)
        self.set_detail("\n".join(lines))

    def go(self):
        try:
            start, end = parse_locus(self.goto.text())
        except ValueError:
            self.set_detail("Use 1234, 1000-2000, or 1000:2000")
            return
        if start == end:
            span = self.view.span
            if span == self.view.length:
                span = min(config.LOCUS_SPAN, self.view.length)
            self.view.jump(start - span // 2, start - span // 2 + span - 1)
        else:
            self.view.jump(start, end)
        self.set_detail(f"{self.view.name}:{self.view.start:,}-{self.view.end:,}")


def parse_locus(text):
    """Accept `1234`, `1000-2000`, `1000:2000`, or `contig:1000-2000`."""
    text = text.strip().replace(",", "").replace("..", "-")
    if not text:
        raise ValueError("empty")
    if ":" in text:
        head, tail = text.split(":", 1)
        try:
            int(head)
        except ValueError:
            text = tail
        else:
            text = head + "-" + tail
    text = text.replace(":", "-")
    if "-" in text:
        left, right = text.split("-", 1)
        return int(left), int(right)
    return int(text), int(text)


def run(fasta, gff=None):
    """Open the browser on the first sequence of `fasta`."""
    fa = Fasta(fasta)
    names = list(fa.keys())
    if not names:
        raise SystemExit(f"no sequences in {fasta}")
    contig = fa[names[0]]
    conn = None
    if gff:
        from mygv.cli import ensure_db

        conn = ensure_db(gff)
    app = QApplication.instance() or QApplication(sys.argv)
    win = Browser(fa, contig, conn)
    win.show()
    return app.exec()


def main():
    from mygv.data import fasta, gff

    raise SystemExit(run(fasta(), gff()))
