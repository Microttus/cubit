# Fonts

Cubit bundles its fonts; nothing is loaded from the internet (FR-35, FR-58).

**JetBrains Mono** is the one font cubit uses beyond the system stack: it sets
navigation, durations, totals, entry ids and `#categories`, so columns of
numbers line up. It is licensed under the SIL Open Font License, so it can ship
with the app.

Put these two files here:

- `JetBrainsMono-Regular.woff2`
- `JetBrainsMono-Bold.woff2`

Copy them from the `fonts/` folder of the
[SpaceIceWeb repo](https://github.com/Microttus/SpaceIceWeb), or from a
[JetBrains Mono release](https://github.com/JetBrains/JetBrainsMono/releases).

Until they are here the app falls back to the system monospace font
(`ui-monospace`, SF Mono, Menlo, Consolas), so everything still works and lines
up — it just looks less like cubit.

JetBrains **Sans** is deliberately not bundled: its licence does not clearly
allow redistribution, so body text uses Inter if the machine has it and the
system UI font otherwise.
