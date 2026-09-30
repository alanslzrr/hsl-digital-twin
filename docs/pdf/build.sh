#!/usr/bin/env bash
#
# Build a single-column PDF from markdown sources.
#
# Pipeline:
#   1. Convert SVG figures to PDF
#   2. Copy assets and bibliography into _build/
#   3. Concatenate section markdown files in order
#   4. Pandoc: markdown -> LaTeX
#   5. Light post-processing (paths, SVG includes)
#   6. latexmk: pdflatex + bibtex -> PDF
#
# Usage:
#   ./build.sh              Build document.pdf
#   ./build.sh --clean      Remove _build/ and rebuild from scratch
#   ./build.sh --watch      Rebuild on every section edit (needs fswatch)
#   ./build.sh --open       Open the PDF after building (macOS)
#
set -euo pipefail

cd "$(dirname "$0")"

BUILD_DIR="_build"
OUT_PDF="../memoria.pdf"

CLEAN=0
WATCH=0
OPEN=0
for arg in "$@"; do
  case "$arg" in
    --clean) CLEAN=1 ;;
    --watch) WATCH=1 ;;
    --open)  OPEN=1  ;;
    -h|--help)
      sed -n '2,17p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 1
      ;;
  esac
done

for tool in pandoc pdflatex latexmk rsvg-convert; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Missing tool: $tool" >&2
    exit 1
  fi
done

build() {
  mkdir -p figures
  cp ../diagrams/*.svg figures/
  cp ../screenshots/*.jpg figures/
  if [[ $CLEAN -eq 1 ]]; then
    echo "▸ Cleaning $BUILD_DIR"
    rm -rf "$BUILD_DIR"
    CLEAN=0
  fi
  mkdir -p "$BUILD_DIR" "$(dirname "$OUT_PDF")"

  echo "▸ Converting SVG figures to PDF"
  for svg in figures/*.svg; do
    [[ -f "$svg" ]] || continue
    name=$(basename "$svg" .svg)
    out="$BUILD_DIR/${name}.pdf"
    if [[ ! -f "$out" ]] || [[ "$svg" -nt "$out" ]]; then
      rsvg-convert -f pdf "$svg" -o "$out"
    fi
  done

  for png in figures/*.png figures/*.jpg figures/*.jpeg; do
    [[ -f "$png" ]] || continue
    cp -f "$png" "$BUILD_DIR/"
  done

  echo "▸ Copying assets and bibliography"
  mkdir -p "$BUILD_DIR/assets" "$BUILD_DIR/references"
  cp -R assets/. "$BUILD_DIR/assets/"
  cp references/references.bib "$BUILD_DIR/references/"

  echo "▸ Concatenating sections"
  {
    shopt -s nullglob
    for f in sections/*.md; do
      cat "$f"
      printf '\n\n'
    done
    shopt -u nullglob
  } > "$BUILD_DIR/document.md"

  if [[ ! -s "$BUILD_DIR/document.md" ]]; then
    echo "No section files found in sections/*.md" >&2
    exit 1
  fi

  echo "▸ Running pandoc"
  pandoc \
    --from=markdown+yaml_metadata_block+tex_math_dollars+raw_tex+raw_attribute \
    --to=latex \
    --natbib \
    --lua-filter=tipografia.lua \
    --metadata-file=metadata.yaml \
    --include-in-header=preamble.tex \
    --standalone \
    "$BUILD_DIR/document.md" \
    -o "$BUILD_DIR/document.tex"

  echo "▸ Post-processing LaTeX"
  python3 - "$BUILD_DIR/document.tex" <<'PY'
import re, sys, pathlib
p = pathlib.Path(sys.argv[1])
tex = p.read_text()

tex = tex.replace("../figures/", "./")
tex = re.sub(
    r"\\includesvg(?:\[[^\]]*\])?\{([^}]+?)\.svg\}",
    r"\\includegraphics[width=\\linewidth,keepaspectratio]{\1.pdf}",
    tex,
)
tex = re.sub(
    r"\\pandocbounded\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}",
    r"\1",
    tex,
)
tex = re.sub(
    r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}",
    lambda m: (
        m.group(0)
        if "assets/" in m.group(1) or re.search(r"width=|height=", m.group(0))
        else f"\\includegraphics[width=\\linewidth,keepaspectratio]{{{m.group(1)}}}"
    ),
    tex,
)

p.write_text(tex)
PY

  echo "▸ Running latexmk (pdflatex + bibtex)"
  (
    cd "$BUILD_DIR"
    latexmk -pdf -bibtex -interaction=nonstopmode -halt-on-error -quiet document.tex
  )

  cp "$BUILD_DIR/document.pdf" "$OUT_PDF"
  echo "✅ PDF: $(pwd)/$OUT_PDF"
}

build

if [[ $OPEN -eq 1 ]]; then
  open "$OUT_PDF"
fi

if [[ $WATCH -eq 1 ]]; then
  if ! command -v fswatch >/dev/null 2>&1; then
    echo "Watch mode needs fswatch (brew install fswatch)" >&2
    exit 1
  fi
  echo "▸ Watching sections/, figures/, assets/, metadata.yaml for changes (Ctrl-C to stop)"
  fswatch -o sections figures assets metadata.yaml preamble.tex | while read -r _; do
    echo ""
    echo "▸ Change detected — rebuilding"
    build || echo "⚠ Build failed — fix and save again"
  done
fi
