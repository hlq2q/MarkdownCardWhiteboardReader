# Bundled web assets (spike 3 / D14)

Vendored for the offscreen formula + diagram renderer. Both are MIT-licensed; the full
license text shipped by each upstream package is kept next to the files.

| File(s) | Package | Version | License | Source |
|---|---|---|---|---|
| `katex/katex.min.js`, `katex/katex.min.css`, `katex/fonts/*.woff2` (20 files) | [KaTeX](https://katex.org/) | **0.19.0** | MIT (see `katex/LICENSE.txt`) | `https://registry.npmjs.org/katex/-/katex-0.19.0.tgz` (`package/dist/…`), fetched 2026-10-12 |
| `mermaid/dist/mermaid.min.js` | [Mermaid](https://mermaid.js.org/) | **12.1.0** | MIT (see `mermaid/LICENSE.txt`) | `https://registry.npmjs.org/mermaid/-/mermaid-12.1.0.tgz` (`package/dist/mermaid.min.js`), fetched 2026-10-12 |

Notes

- Downloaded by `spikes/spike_web_render.py --fetch-assets` (see that file for the exact
  keep-list); nothing else from either tarball is vendored.
- `katex.min.css` is post-processed: the `woff`/`ttf` fallback sources are stripped, because
  Qt WebEngine (Chromium) always picks the `woff2` face. Fonts are otherwise unmodified.
- Total on disk: ~5.9 MB (Mermaid's single minified bundle is 5.5 MB of it; KaTeX + fonts ~600 KB).
- Mermaid is required for Mermaid diagrams only; KaTeX for math only. A build that can drop
  one of them saves the corresponding size.
