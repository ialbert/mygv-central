import gzip
from urllib.parse import unquote

COLUMNS = (
    "seqid",
    "source",
    "type",
    "start",
    "end",
    "score",
    "strand",
    "phase",
)


def parse_attr(text):
    """Turn a GFF3 attributes column into a dict of decoded tag/value pairs."""
    attrs = {}
    text = text.strip()
    if not text or text == ".":
        return attrs
    for field in text.split(";"):
        field = field.strip()
        if not field:
            continue
        key, sep, value = field.partition("=")
        if not sep:
            continue
        attrs[unquote(key)] = unquote(value)
    return attrs


def parse_line(line):
    """Parse one GFF3 feature line into a record dict."""
    cols = line.rstrip("\n\r").split("\t")
    if len(cols) != 9:
        raise ValueError(f"GFF3 line has {len(cols)} columns, expected 9")
    rec = dict(zip(COLUMNS, cols[:8]))
    rec["attr"] = parse_attr(cols[8])
    return rec


def parse_gff(path, on_bytes=None):
    """Yield feature records from a GFF3 file.

    A path ending in `.gz` is read as gzip. on_bytes, when set, is called with
    the number of file bytes consumed for each line.
    """
    if str(path).endswith(".gz"):
        fh = gzip.open(path, "rb")
    else:
        fh = open(path, "rb")
    with fh:
        consumed = 0
        for raw in fh:
            if on_bytes:
                if isinstance(fh, gzip.GzipFile):
                    pos = fh.fileobj.tell()
                    on_bytes(pos - consumed)
                    consumed = pos
                else:
                    on_bytes(len(raw))
            line = raw.decode()
            if line.startswith("##FASTA"):
                break
            if not line.strip() or line.startswith("#"):
                continue
            yield parse_line(line)
