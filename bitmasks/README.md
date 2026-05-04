# RXTE PCA Bitmask Files

Bitmask files filter `seextrct` events on the EVENT column bit pattern. The
right bitmask depends on the PCA data mode of your observation; the wrong one
will silently give you the wrong events. This collection mirrors the HEASARC
RXTE Cook Book layout:

  https://heasarc.gsfc.nasa.gov/docs/xte/recipes/bitmasks.html

Three categories cover almost every PCA event-mode configuration:

- `bitfiles_d/` — D-token modes (most `E_*us_*` event modes)
- `bitfiles_gx/` — Good Xenon modes (event-by-event)
- `bitfiles_z/` — Z-token modes (`E_1ms_128` and similar)

`bitmask_event` at the top level is a duplicate of `bitfiles_d/bitfile_M`,
kept under the canonical name that downstream tools (`extraction_06`) expect.
The `bitmask` CLI subcommand renames whatever bitmask you pick to
`bitmask_event` when copying it into each `Analysis/` directory.

## Picking the right bitmask: by data mode

Look at the `DATAMODE` of your data (HEASARC ABC, `fits_data_summary.csv`
written by the `organize` step, or the `DATAMODE` keyword of the FITS file).

| Data mode pattern | Bitmask family |
|---|---|
| `E_1us_1`, `E_2us_2`, `E_4us_4`, `E_8us_8`, `E_16us_16`, `E_31us_16`, `E_62us_32`, `E_62us_64`, `E_125us_64`, `E_250us_128` | `bitfiles_d/` |
| `E_1us_4`, `E_2us_8`, `E_4us_16`, `E_8us_32`, `E_16us_64` | `bitfiles_d/bitfile_M` (time-marker filter only) |
| `E_1ms_128` | `bitfiles_z/` |
| `GoodXenon`, `B_*` modes | `bitfiles_gx/` |

## Picking the right bitmask: by selection (within a family)

Within each family you also pick a detector/layer combination. PCU labels
(`d012`, `d0123`, `d0124`) and layer labels (`lr1`, `lr12`, `lr3`) refer to
which PCUs and which xenon layers are kept.

`bitfile_M` is the most permissive: it keeps everything except the
time-marker bit. Use it when you want all events. The detector/layer
variants further restrict.

| Suffix | Selection |
|---|---|
| `_M` | All detectors, all layers (drops only the time marker) |
| `_d012` | PCUs 0, 1, 2 only |
| `_d0123` | PCUs 0, 1, 2, 3 only |
| `_d0124` | PCUs 0, 1, 2, 4 only (HEASARC notes this case is OR-mode, see below) |
| `_lr1` | Top xenon layer only (LR1) |
| `_lr12` | Top + middle xenon layers (LR1 + LR2) |
| `_lr3` | Bottom xenon layer only (LR3) |
| `_lrN_dXYZ` | Combination: layer N restricted to PCUs X, Y, Z |

## AND vs OR (Good Xenon and Z-token only)

The `bitfiles_gx/` and `bitfiles_z/` directories split into `and/` and `or/`
subdirectories.

- `and/` files use `&&` between bit-pattern conditions. `seextrct` can
  apply them directly.
- `or/` files use `||` and are not directly accepted by `seextrct`. You
  need to pre-filter the FITS rows with `fselect` first; see the HEASARC
  recipe for the exact workflow:

    https://heasarc.gsfc.nasa.gov/docs/xte/recipes/bitmasks.html

The `_d0124` selection ends up in `or/` for both GX and Z because PCU 4 is
not contiguous with PCUs 0, 1, 2 in the bit layout, so it cannot be
expressed as a single AND mask.

## Common defaults

- Most users analysing event-mode data want
  `bitfiles_d/bitfile_M` (= the top-level `bitmask_event`).
- For Good Xenon, the most common pick is `bitfiles_gx/and/bitfile_gx_d012`
  (PCUs 0, 1, 2 are the most reliable across the mission lifetime).
- For Z-mode data, the most common pick is `bitfiles_z/and/bitfile_z_d012`.

## File format

Each bitmask is a one- or two-line text file:

```
 Event <= bx010xxxxxxxxxxxx &&
 Event == b1xxxxxxxxxxxxxxx
```

`b` introduces a binary literal. `x` is a "don't care" bit. `==` is exact
match; `<=` is bitwise mask comparison (each `0` or `1` must match in the
corresponding bit; `x` bits are ignored).

## Listing what's available

```bash
# Show every bitmask shipped with the repo
autorxte bitmask --list

# Copy a specific named one into every Analysis/ as bitmask_event
autorxte bitmask --bitmask bitfile_gx_d012 --directory ./data
```

## Source

All files in this directory come from
https://heasarc.gsfc.nasa.gov/docs/xte/recipes/bitmasks.html
