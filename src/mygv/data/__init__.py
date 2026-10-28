from importlib.resources import files
from pathlib import Path

FASTA_NAME = "fasta/staphylococcus-aureus.fa.gz"
FAI_NAME = "fasta/staphylococcus-aureus.fa.gz.fai"
GZI_NAME = "fasta/staphylococcus-aureus.fa.gz.gzi"
GFF_NAME = "gff/staphylococcus-aureus.gff3"


def config_dir():
    return Path.home() / ".config" / "mygv"


def materialize(name):
    """Copy one packaged file into ~/.config/mygv. Return that path."""
    src = files("mygv.data").joinpath(name)
    dest = config_dir() / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        dest.write_bytes(src.read_bytes())
    return dest


def fasta():
    path = materialize(FASTA_NAME)
    materialize(FAI_NAME)
    materialize(GZI_NAME)
    return path


def gff():
    return materialize(GFF_NAME)
