# Design

Genome browser over one contig at a time. A `View` is the visible window. Tracks paint against a `Scale` that maps that window onto pixels. Sequence comes from a FASTA through pyfaidx. Genes come from a SQLite database built from the GFF.

Coordinates in the view, the GFF, and the database are 1-based and inclusive. pyfaidx slices are 0-based and half-open, so a window `[start, end]` is read as `fa[name][start - 1:end]`.

Limits live in `src/mygv/gui/config.json`: `DRAW_LIMIT`, `MIN_SPAN`, `LABEL_PX`, `GLYPH_PX`, `PAN_PART`, `ZOOM`, `TICK_PX`, and `LOCUS_SPAN`. Colors live under `COLORS`.

## View

`View` (`src/mygv/view.py`) holds `name`, `length`, `start`, and `end`. `span` is `end - start + 1`. The window never shrinks below `MIN_SPAN` and never leaves the contig.

- `zoom(factor, anchor)` keeps the anchor at the same fraction of the window. Factor 2 shows half as many bases.
- `pan(delta)` slides by `delta` bases and keeps the span.
- `jump(start, end)` replaces the window.
- Listeners run after each of those. The track pane repaints. The range label updates.

`Scale` is not stored. Each paint builds one from the view and the current widget width. `to_x` and `to_bp` convert between bases and pixels.

Scroll pans. One wheel notch (120 units) moves about `1 / PAN_PART` of the span. Scroll up moves toward lower coordinates. Scroll down, or a horizontal swipe to the right, moves toward higher ones. The same handler is used on the tracks and on the name gutter. Zoom stays on the buttons and on double-click, which recenters on the cursor and then zooms by `ZOOM`.

## Sequence

`SequenceTrack` reads the FASTA with pyfaidx. The file stays open. A `.fai` index, built by pyfaidx if it is missing, turns a coordinate into a seek. The visible string is cached on `(name, start, end)` so a repaint of the same window does not seek again.

Paint chooses a mode before reading, so a large window never loads the contig:

- **Letters.** Each base is at least as wide as a character. The window is a few hundred bases. Draw a washed base color and the letter.
- **Colors.** `span` is at most `DRAW_LIMIT`. If there is at least one pixel per base, draw one rectangle per base. Otherwise tally bases into pixel columns and paint the majority base, joining equal neighbors into one rectangle.
- **Grey.** `span` is above `DRAW_LIMIT`. Draw one washed grey bar and drop the cached string. A chromosome is not read.

`DRAW_LIMIT` is the largest window that is still read and drawn in detail. It is not specific to base colors. Sampling one base per pixel was rejected. At chromosome scale that base does not represent the column, and one seek per column on every pan costs more than painting nothing. A majority color still requires every base in the column, which is the read `DRAW_LIMIT` avoids.

Hover does not use that cache. Each mouse move seeks the single base under the cursor with `fa[name][bp - 1:bp]`. The detail text is rewritten only when it changes. The seek still happens.

## Genes

`mygv load` always rebuilds the database beside the GFF: `Path(gff).with_suffix(".db")`. `mygv browse` calls `ensure_db`, which opens that file or, if it is missing, runs the same load. A path ending in `.gz` is read with `gzip.open`. The progress bar counts compressed bytes consumed, so it tracks the `.gz` size on disk.

`db.load` stores every feature, plus gene and transcript tables and parent links. Indexes are built after the insert. The one the browser uses is `feature_seqid_start_end`. Gene names stored on the gene table come from `gene_name`, then `Name`, then `name`.

Genes are drawn on two tracks, `gene(+)` and `gene(-)`. Neither keeps the file in memory. `db.genes` returns start, end, strand, and name for `type = 'gene'` rows that overlap the visible window, and takes a strand so each track queries only its own rows. Attributes are not parsed. Each track caches on `(seqid, start, end)`. Changing contig changes `view.name`, so the next paint queries that contig.

Forward genes are a lighter washed red (`PLUS`). Reverse genes are a washed blue (`MINUS`). Labels are ink. Genes with no strand are omitted.

Two ways to draw that list:

- **Sparse.** At most one gene per pixel. Draw each gene as a bar with the 3' corners cut, so that end meets in a point. Forward genes point right. Reverse genes point left. The cut is half the bar height, and never more than half the bar width. A label is drawn when the glyph is wider than `LABEL_PX`. Hover scans this list.
- **Dense.** More genes than pixels. Mark each pixel a gene touches, then join neighboring marked pixels into one bar. Gaps wider than a pixel stay empty, so deserts remain visible. Labels are omitted. Merging only features that overlap each other is not enough: most genes do not overlap, they just share a pixel. Hover asks SQLite for genes overlapping that one base instead of walking the whole list.

The dense query is still every gene on that strand in the window, not a precomputed density. That is cheap for a gene track (thousands of rows) and is what makes the gaps correct.
