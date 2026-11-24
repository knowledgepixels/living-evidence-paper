# Living Evidence Paper

*Accelerating Frontier Science with a Living, Probabilistic Evidence Graph* (Joel Dietz): the Probknow paper. It was converted from the LaTeX/PDF version dated June 19, 2026. The manuscript is written in [dokieli](https://dokie.li/), as a single HTML file that is also the rendered article. The setup follows [nanopub-ecosystem-paper](https://github.com/knowledgepixels/nanopub-ecosystem-paper).

## Top-level layout

- **`index.html`**: the paper itself, always the latest version. Open it in a browser to read it, and edit it in dokieli to write.
- **`paper.pdf`**: `index.html` rendered to PDF by `scripts/make-pdf.sh`.
- **`paper.rtf`**: `index.html` rendered to RTF by `scripts/make-rtf.sh`, for co-authors who want Word.
- **`README.md`**: this file.
- **`.gitignore`**: local ignore rules.

## Folders

- **`media/`**: assets used to render `index.html`.
  - `css/`: `lncs.css` (the default style), `acm.css` (an alternate style that dokieli can switch to), and `draft.css` (styles `<mark class="todo">` and `<mark class="note">` for draft comments). Changes made for this project are at the end of `lncs.css` and `acm.css`, under "Project tweaks".
  - `fonts/`: the Computer Modern Unicode fonts that the stylesheets use.
  - `images/`: the figures, as hand-written SVG redrawn from the TikZ originals. Edit them directly. Each one has a white background panel, so it stays readable when the page is in dark mode.
- **`scripts/`**: build scripts. Both need Chrome, plus network access to load dokieli from dokie.li. The RTF script also needs `pandoc` and ImageMagick (`convert`).
  - `make-pdf.sh`: writes `paper.pdf` (A4).
  - `make-rtf.sh`: writes `paper.rtf`, with the figures rasterised to PNG. pandoc cannot convert equations 3 and 4 into RTF math, so they appear as TeX source.
- **`local/`**: git-ignored working material, including the original PDF (`local/original-2026-06-19.pdf`).

## Authoring conventions

- Section, figure, table, listing and equation numbers come from CSS counters. In-text references such as "Section 4", "Figure 1" or "Eq. (3)" are typed by hand and link to the element's `id`. If you reorder anything, update those references too.
- Displayed equations are MathML inside `<figure class="equation">`. Inline variables are written as `<em>p</em>`, `<em>K</em><sub>combined</sub>`, and so on.
- Citations are written as `[<a class="ref" href="#ref-N">N</a>]`. The references keep the numbering and text of the original PDF.
- Versions: when a version is released, follow the nanopub-ecosystem-paper convention. Add a version line and a change log entry to `index.html`, then freeze a copy in `v<version>/` along with its figures. The copy's stylesheet links point one level up (`../media/css/`).
