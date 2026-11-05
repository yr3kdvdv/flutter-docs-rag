"""Cleaning, normalization and chunking of Markdown documents with provenance metadata."""

# Bump whenever cleaning or chunking output can change. It is part of the index state,
# so documents are re-chunked (embeddings still come from the cache when text is equal).
# 2: docs.flutter.dev anchor rules (dots, duplicates, {:.class} attributes).
PREPROCESS_VERSION = 2
