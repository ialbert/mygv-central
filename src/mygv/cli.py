import json
import os
import sys
from pathlib import Path

import click

from mygv import db
from mygv.data import fasta as default_fasta
from mygv.data import gff as default_gff
from mygv.gff import parse_gff

DEFAULT_GFF = "data/chr22.gff3"


def db_path(gff):
    """Database path beside the GFF file, with a .db suffix."""
    return str(Path(gff).with_suffix(".db"))


def load_db(gff):
    """Replace the database beside `gff` and return the open connection."""
    path = db_path(gff)
    size = os.path.getsize(gff)
    conn = db.create(path)
    try:
        with click.progressbar(length=size, label="Loading", file=sys.stderr) as bar:
            n = db.load(conn, parse_gff(gff, on_bytes=bar.update))
    except Exception:
        conn.close()
        raise
    click.echo(f"{n} features written to {path}", err=True)
    return conn


def ensure_db(gff):
    """Open the database beside `gff`, building it when the file is missing."""
    path = db_path(gff)
    if os.path.exists(path):
        return db.connect(path)
    return load_db(gff)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(package_name="mygv")
def main():
    """mygv the little genome browser that could.

   \b
      ~~~  ~~~
        |    |
    ____|____|___
   |   myGV      |====\\
   |_____________|____/
     O--O--O   O--O
"""


@main.command()
@click.option("--gff", default=DEFAULT_GFF, show_default=True, type=click.Path(exists=True, dir_okay=False), help="GFF3 file to parse.")
def parse(gff):
    """Parse a GFF3 file and print records as indented JSON."""
    size = os.path.getsize(gff)
    prefix = "[\n"
    with click.progressbar(length=size, label="Parsing", file=sys.stderr) as bar:
        for rec in parse_gff(gff, on_bytes=bar.update):
            click.echo(prefix, nl=False)
            click.echo(json.dumps(rec, indent=2), nl=False)
            prefix = ",\n"
    click.echo("\n]" if prefix != "[\n" else "[]")


@main.command("load")
@click.option("--gff", default=DEFAULT_GFF, show_default=True, type=click.Path(exists=True, dir_okay=False), help="GFF3 file to load.")
def load_gff(gff):
    """Load a GFF3 file into a new SQLite database beside that file."""
    load_db(gff).close()


@main.command("query")
@click.option("--db", "path", default=db_path(DEFAULT_GFF), show_default=True, type=click.Path(exists=True, dir_okay=False), help="SQLite database to query.")
@click.option("--seqid", default="chr22", show_default=True, help="Sequence name, such as a chromosome.")
@click.option("--start", default=15528192, show_default=True, type=int, help="Range start. A single coordinate when --end is omitted.")
@click.option("--end", "end", type=int, help="Range end. Defaults to --start.")
@click.option("--type", "kind", help="Feature type. Omit to keep every type.")
def query_features(path, seqid, start, end, kind):
    """Print features that overlap a chromosome interval."""
    if end is None:
        end = start
    conn = db.connect(path)
    try:
        prefix = "[\n"
        for rec in db.overlap(conn, seqid, start, end, kind):
            click.echo(prefix, nl=False)
            click.echo(json.dumps(rec, indent=2), nl=False)
            prefix = ",\n"
    finally:
        conn.close()
    click.echo("\n]" if prefix != "[\n" else "[]")


@main.command("browse")
@click.option("--fasta", default=default_fasta, show_default="staphylococcus-aureus (packaged)", type=click.Path(exists=True, dir_okay=False), help="FASTA file.")
@click.option("--gff", default=default_gff, show_default="staphylococcus-aureus (packaged)", type=click.Path(exists=True, dir_okay=False), help="GFF3 file. Gene rows are drawn as a track.")
def browse(fasta, gff):
    """Open the genome browser."""
    from mygv.gui.window import run

    sys.exit(run(fasta, gff))


if __name__ == "__main__":
    main()
