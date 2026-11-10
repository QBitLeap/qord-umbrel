# Retained dependency license texts

The locked registry archives listed in manifest.json omit full license files.
Each entry preserves the original published package metadata and records the
archive checksum, source URLs and retained text hashes. Where the archive
identifies an upstream source revision with license files, those complete files
are retained. Otherwise the entry records the declared license and supplies its
standard SPDX text, selecting Apache-2.0 for Apache-2.0 OR MIT declarations.
Upstream authorship remains in the retained Cargo.toml files; standard license
text is not represented as a license file shipped in the original archive.

The collector uses these entries only for exact name/version/archive checksum
matches among packages for which Cargo emitted build artifacts. Other targets
and development-only packages are outside this Linux binary inventory.
