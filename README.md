
# My Genome Viewer: myGV

`myGV` the little genome browser that could.

![myGV logo](https://github.com/ialbert/mygv-central/blob/main/docs/myGV-genomic-steam-engine.png)

## What is myGV?

myGV is an experimental genome browser in the style of IGV. I am building it with AI agents, starting with features I have always wanted. For example it has `WASD` control to zoom and pan, and full control over glyphs. I am still figuring out the rest, and that is the fun of it.

## Installation

We assume you have the [pixi package manager][pixi] installed. If not, you should.

[pixi]: https://pixi.prefix.dev/

```bash
# Add tpython and pyside6 to your pixi environment
pixi add python pyside6
```

Now you can install myGV with:

```bash
# Install myGV in your pixi environment
pip install mygv
```

## Run

Run `mygv` to see what it can do.

```
mygv 
```

To run the browser with default settings, run:

```bash
mygv browse
```

Pass your genome fasta and gff files to the browser.

```bash
mygv browse \
    --fasta genome_sequence.fa \
    --gff genome_annotations.gff
```

![myGV screenshot][screenshot1]

[screenshot1]: https://github.com/ialbert/mygv-central/blob/main/docs/images/mygv-example-1.jpg?raw=true

Enjoy!




