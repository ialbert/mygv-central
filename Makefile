
# Human gencode
# FASTA_URL=https://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_human/release_50/GRCh38.p14.genome.fa.gz
# GFF_URL=https://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_human/release_50/gencode.v50.basic.annotation.gff3.gz

#  Staphylococcus aureus
FASTA_URL = https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/013/465/GCF_000013465.1_ASM1346v1/GCF_000013465.1_ASM1346v1_genomic.fna.gz
GFF_URL = https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/013/465/GCF_000013465.1_ASM1346v1/GCF_000013465.1_ASM1346v1_genomic.gff.gz

GENOME_NAME = staphylococcus-aureus

FASTA = data/fasta/$(GENOME_NAME).fa.gz
GFF = data/gff/$(GENOME_NAME).gff3

usage:
	@echo "# Read the source, Luke!"

$(FASTA):
	mkdir -p $(dir $@)
	curl -L $(FASTA_URL) | gunzip -c | bgzip > $@
	samtools faidx $@

$(GFF):
	mkdir -p $(dir $@)
	curl -L $@ $(GFF_URL) | gunzip -c > $@


gff: $(GFF)
	ls -lh $(GFF)

fasta: $(FASTA)
	ls -lh $(FASTA)

genomes: fasta gff

# Build Python package.
build:
	rm -rf build dist
	uv build
	ls -lh dist

# Publish the package
publish: build
	uv publish