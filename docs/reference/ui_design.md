# Interface design notes

The user requested one simple Streamlit page, with most effort on coordinates and
experiments. This is an engineering inspection tool for a local desktop browser.
Refero live style searches (scientific software, healthcare, Linear typography)
returned NO_SUBSCRIPTION. The bundled Refero typography and craft-details references
provide the fallback research: neutral type for work tools, a single system font,
clear text hierarchy, labeled controls, visible focus states, and real images.

| Decision | Source | Reason |
|---|---|---|
| Native Streamlit light canvas and system sans | Refero typography, context-first | Make dense results easy to scan; no extra font download |
| Overview beside inspector, table underneath | User's inspect/export workflow | Keep slide location visible while reading the selected crop |
| Real slide image is the main visual | User brief; Refero image guidance | Tissue evidence takes priority over decoration |
| Green outline + check for accepted; orange hatching + X for candidates | User accessibility requirement | Status survives grayscale and color vision differences |
| Labels, metrics, downloadable evidence, explicit partial coverage | User brief; Refero forms/accessibility | Make analysis scope and uncertainty visible |

Preserve a white canvas, compact native controls, thin borders, a restrained green
action accent, and unobstructed slide imagery. Reserve status colors for tile
states. Use no generated imagery, decorative cards, gradients, or animations.
Validate the rendered app with a real slide, and test state changes using Streamlit
AppTest. A selectable table provides keyboard access to every visited tile.
