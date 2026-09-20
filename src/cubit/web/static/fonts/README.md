# Fonts

Cubit bundles its fonts; nothing is loaded from the internet (FR-35, FR-58).

## What is here

- `JetBrainsMono-Regular.woff2` — the one font cubit ships. It sets navigation,
  durations, totals, entry ids and `#categories`, so columns of numbers line up.
  This is the same file the [IceCube Solutions site](https://icecubesol.no) uses
  (from the [SpaceIceWeb repo](https://github.com/Microttus/SpaceIceWeb)), so the
  two look related.
- `OFL.txt` — the SIL Open Font License, Version 1.1, which JetBrains Mono is
  released under and which permits bundling it here.

## What is deliberately not here

**A bold weight.** Only the regular is bundled, so a browser synthesizes bold
from it. Cubit's interface uses mono for labels and figures rather than for
emphasis, so the difference barely shows. To use the real thing, drop
`JetBrainsMono-Bold.woff2` in beside the regular and add a second `@font-face`
to `../theme.css` with `font-weight: 700`.

**JetBrains Sans.** Its licence does not clearly allow redistribution, so body
text falls back to Inter if the machine has it and the system UI font otherwise.
