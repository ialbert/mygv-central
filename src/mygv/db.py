import json
import os
import sqlite3

TABLES = """
CREATE TABLE feature (
    pk INTEGER PRIMARY KEY,
    seqid TEXT NOT NULL,
    source TEXT NOT NULL,
    type TEXT NOT NULL,
    start INTEGER NOT NULL,
    "end" INTEGER NOT NULL,
    score TEXT NOT NULL,
    strand TEXT NOT NULL,
    phase TEXT NOT NULL,
    attr TEXT NOT NULL,
    gff_id TEXT
);

CREATE TABLE relation (
    parent_pk INTEGER NOT NULL REFERENCES feature (pk),
    child_pk INTEGER NOT NULL REFERENCES feature (pk),
    PRIMARY KEY (parent_pk, child_pk)
);

CREATE TABLE gene (
    pk INTEGER PRIMARY KEY REFERENCES feature (pk),
    gene_id TEXT,
    gene_type TEXT,
    gene_name TEXT,
    hgnc_id TEXT,
    havana_gene TEXT
);

CREATE TABLE transcript (
    pk INTEGER PRIMARY KEY REFERENCES feature (pk),
    transcript_id TEXT,
    transcript_type TEXT,
    transcript_name TEXT,
    havana_transcript TEXT,
    protein_id TEXT
);
"""

INDEXES = """
CREATE INDEX feature_gff_id ON feature (gff_id);
CREATE INDEX feature_seqid_start_end ON feature (seqid, start, "end");
CREATE INDEX feature_seqid_end_start ON feature (seqid, "end", start);
CREATE INDEX relation_child ON relation (child_pk);
CREATE INDEX gene_gene_id ON gene (gene_id);
CREATE INDEX gene_gene_type ON gene (gene_type);
CREATE INDEX gene_gene_name ON gene (gene_name);
CREATE INDEX gene_hgnc_id ON gene (hgnc_id) WHERE hgnc_id IS NOT NULL;
CREATE INDEX gene_havana_gene ON gene (havana_gene) WHERE havana_gene IS NOT NULL;
CREATE INDEX transcript_transcript_id ON transcript (transcript_id);
CREATE INDEX transcript_transcript_type ON transcript (transcript_type);
CREATE INDEX transcript_transcript_name ON transcript (transcript_name);
CREATE INDEX transcript_havana_transcript ON transcript (havana_transcript) WHERE havana_transcript IS NOT NULL;
CREATE INDEX transcript_protein_id ON transcript (protein_id) WHERE protein_id IS NOT NULL;
"""

INSERT_FEATURE = """
INSERT INTO feature (
    pk, seqid, source, type, start, "end", score, strand, phase, attr, gff_id
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

INSERT_RELATION = "INSERT INTO relation (parent_pk, child_pk) VALUES (?, ?)"

INSERT_GENE = """
INSERT INTO gene (
    pk, gene_id, gene_type, gene_name, hgnc_id, havana_gene
) VALUES (?, ?, ?, ?, ?, ?)
"""

INSERT_TRANSCRIPT = """
INSERT INTO transcript (
    pk, transcript_id, transcript_type, transcript_name, havana_transcript, protein_id
) VALUES (?, ?, ?, ?, ?, ?)
"""

BATCH = 5000


def connect(path):
    """Open an existing database."""
    return sqlite3.connect(path)


_COLS = "seqid, source, type, start, \"end\", score, strand, phase, attr"
_SPAN = "seqid = ? AND start <= ? AND \"end\" >= ? ORDER BY start, \"end\""

OVERLAP = f"SELECT {_COLS} FROM feature WHERE type = ? AND {_SPAN}"
OVERLAP_ALL = f"SELECT {_COLS} FROM feature WHERE {_SPAN}"


GENES = """
SELECT f.start, f."end", f.strand, COALESCE(g.gene_name, 'gene')
FROM feature f
LEFT JOIN gene g ON g.pk = f.pk
WHERE f.type = 'gene' AND f.seqid = ? AND f.start <= ? AND f."end" >= ?
"""


def genes(conn, seqid, start, end, strand=None):
    """Yield `(start, end, strand, name)` for genes overlapping `[start, end]`.

    Pass `strand` (`+` or `-`) to keep one strand.
    """
    sql = GENES
    args = [seqid, end, start]
    if strand is not None:
        sql += " AND f.strand = ?"
        args.append(strand)
    sql += ' ORDER BY f.start, f."end"'
    return conn.execute(sql, args)


def overlap(conn, seqid, start, end, type=None):
    """Yield features on seqid that overlap [start, end]. Omit type to keep every feature type."""
    cols = ("seqid", "source", "type", "start", "end", "score", "strand", "phase", "attr")
    if type:
        rows = conn.execute(OVERLAP, (type, seqid, end, start))
    else:
        rows = conn.execute(OVERLAP_ALL, (seqid, end, start))
    for row in rows:
        rec = dict(zip(cols, row))
        rec["attr"] = json.loads(rec["attr"])
        yield rec


def create(path):
    """Create a new database at path, replacing any file already there."""
    if os.path.exists(path):
        os.remove(path)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(TABLES)
    return conn


def _row(pk, rec):
    attr = rec["attr"]
    gff_id = attr.get("ID") or None
    return (
        pk,
        rec["seqid"],
        rec["source"],
        rec["type"],
        int(rec["start"]),
        int(rec["end"]),
        rec["score"],
        rec["strand"],
        rec["phase"],
        json.dumps(attr, separators=(",", ":")),
        gff_id,
    )


def _gene_row(pk, rec):
    attr = rec["attr"]
    return (
        pk,
        attr.get("gene_id") or attr.get("ID") or None,
        attr.get("gene_type") or attr.get("gene_biotype") or None,
        attr.get("gene_name") or attr.get("Name") or attr.get("name") or None,
        attr.get("hgnc_id") or None,
        attr.get("havana_gene") or None,
    )


def _transcript_row(pk, rec):
    attr = rec["attr"]
    return (
        pk,
        attr.get("transcript_id") or None,
        attr.get("transcript_type") or None,
        attr.get("transcript_name") or None,
        attr.get("havana_transcript") or None,
        attr.get("protein_id") or None,
    )


def _parent_ids(attr):
    text = attr.get("Parent")
    if not text:
        return ()
    return tuple(part for part in (item.strip() for item in text.split(",")) if part)


def load(conn, records):
    """Insert features, genes, transcripts, and parent links, then build indexes. Returns the feature count."""
    ids = {}
    links = []
    batch = []
    genes = []
    transcripts = []
    n = 0
    for rec in records:
        n += 1
        row = _row(n, rec)
        gff_id = row[-1]
        if gff_id is not None:
            ids.setdefault(gff_id, []).append(n)
        for parent_id in _parent_ids(rec["attr"]):
            links.append((n, parent_id))
        batch.append(row)
        if "gene_id" in rec["attr"] or "ID" in rec["attr"]:
            genes.append(_gene_row(n, rec))
        if "transcript_id" in rec["attr"]:
            transcripts.append(_transcript_row(n, rec))
        if len(batch) >= BATCH:
            conn.executemany(INSERT_FEATURE, batch)
            batch.clear()
    if batch:
        conn.executemany(INSERT_FEATURE, batch)
    if genes:
        conn.executemany(INSERT_GENE, genes)
    if transcripts:
        conn.executemany(INSERT_TRANSCRIPT, transcripts)

    rels = []
    seen = set()
    for child, parent_id in links:
        for parent in ids.get(parent_id, ()):
            if (parent, child) in seen:
                continue
            seen.add((parent, child))
            rels.append((parent, child))
        if len(rels) >= BATCH:
            conn.executemany(INSERT_RELATION, rels)
            rels.clear()
    if rels:
        conn.executemany(INSERT_RELATION, rels)

    conn.commit()
    conn.executescript(INDEXES)
    return n
