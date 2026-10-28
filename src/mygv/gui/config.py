"""Browser settings. Edit config.json beside this file to change the defaults."""

import json
from pathlib import Path

from PySide6.QtGui import QColor

DEFAULT = Path(__file__).with_name("config.json")


class Colors:
    def __init__(self, data):
        self.INK = QColor(data["INK"])
        self.LIGHT_INK = QColor(data["LIGHT_INK"])
        self.PAPER = QColor(data["PAPER"])
        self.LINE = QColor(data["LINE"])
        self.WHITE = QColor(data["WHITE"])
        self.PLUS = QColor(data["PLUS"])
        self.MINUS = QColor(data["MINUS"])
        self.OTHER = QColor(data["OTHER"])
        self.WASH = data["WASH"]
        self.BASE = {key: QColor(value) for key, value in data["BASE"].items()}

    def base_color(self, base):
        return self.BASE.get(base.upper(), self.OTHER)


class Config:
    def __init__(self, data):
        self.DRAW_LIMIT = data["DRAW_LIMIT"]
        self.MIN_SPAN = data["MIN_SPAN"]
        self.LABEL_PX = data["LABEL_PX"]
        self.GLYPH_PX = data["GLYPH_PX"]
        self.PAN_PART = data["PAN_PART"]
        self.ZOOM = data["ZOOM"]
        self.TICK_PX = data["TICK_PX"]
        self.LOCUS_SPAN = data["LOCUS_SPAN"]
        self.COLORS = Colors(data["COLORS"])


def load(path=None):
    file = DEFAULT if path is None else Path(path)
    return Config(json.loads(file.read_text()))
