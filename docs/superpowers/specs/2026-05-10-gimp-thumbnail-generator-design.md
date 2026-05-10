# GIMP Thumbnail Generator Design

Date: 2026-05-10

## Goal

Build a Python command-line script that generates a Magic: The Gathering gameplay thumbnail from a GIMP template named `thumbnail-template.xcf` in the project root. The script prompts for tournament, round, deck, and card information, downloads card art from Scryfall, updates known template layers, and exports a PNG into `exports/`.

## Inputs

The script prompts for:

1. Tournament name
2. Round name
3. Player 1 deck name
4. Player 1 card name
5. Player 2 deck name
6. Player 2 card name

All answers are required. Blank answers are rejected and re-prompted.

## Scryfall Lookup

The script uses Scryfall in two stages for each submitted card name:

1. Resolve the intended card with fuzzy matching via the named-card endpoint.
2. Use the resolved card's `oracle_id` to search for the original non-reprint printing with a query equivalent to `oracleid:<oracle_id> not:reprint`.

The selected card object must provide an `art_crop` image URI. For normal single-faced cards this is read from `image_uris.art_crop`. For card objects without top-level image URIs, the script checks card faces and uses the first face with an `art_crop`.

Requests include a relevant `User-Agent` header and an `Accept` header. The flow only performs a small number of requests per run and stays well below Scryfall's guidance of fewer than 10 API requests per second.

The script prints the resolved card names so the user can see what fuzzy matching selected before the GIMP export completes.

## Template Contract

The GIMP template must be named `thumbnail-template.xcf` and live next to the script. The script expects these exact layer names:

- `Event Title`
- `Player 1 Deck Image`
- `Player 2 Deck Image`
- `Player 1 Deck Name`
- `Player 2 Deck Name`

`Event Title` is updated to the tournament name followed by a newline and the round name. The player deck-name text layers are updated to the deck names.

The two deck-image layers are replaced visually with the downloaded Scryfall `art_crop` images. Each art image preserves its aspect ratio, scales to cover the original layer bounds, and is center-cropped to the placeholder's size and position. This avoids stretching while keeping the template layout stable.

## Export

The script creates `exports/` if it does not already exist. The PNG filename is based on:

`[event-name]-[round-name]-[deck-1-name]-vs-[deck-2-name].png`

Each filename component is converted to a filesystem-safe slug: lowercase, trimmed, non-alphanumeric runs replaced by hyphens, and leading or trailing hyphens removed.

## Error Handling

The script exits with clear messages when:

- `thumbnail-template.xcf` is missing.
- GIMP is unavailable or returns an error.
- Scryfall cannot resolve a card name.
- The original non-reprint printing cannot be found.
- No usable `art_crop` URI exists.
- A required template layer is missing.
- Image download or PNG export fails.

Temporary downloaded card-art files may be stored under a local temporary directory and cleaned up after export.

## Architecture

The implementation is a small Python CLI with testable pure-Python helpers and a thin GIMP integration layer.

Core units:

- Prompt collection: asks questions and validates non-empty answers.
- Slug generation: converts user-facing labels into safe filename components.
- Scryfall client: resolves fuzzy card names, searches original non-reprint printings, and downloads art crops.
- Crop math: computes aspect-preserving cover scale and center-crop placement for replacing placeholder layers.
- GIMP runner: invokes GIMP headlessly against the template and performs layer updates/export.

## Testing

Automated tests cover the pure-Python pieces without launching GIMP:

- Required prompt answers are validated.
- Filename slugging produces the expected export names.
- Scryfall response parsing selects `image_uris.art_crop` or a face-level `art_crop`.
- Original-print search query uses `oracle_id` and `not:reprint`.
- Center-crop math preserves aspect ratio and covers target bounds.

The GIMP execution path is verified manually or with a focused integration run against the local `thumbnail-template.xcf`, because it depends on the installed GIMP runtime and the actual layer structure of the XCF file.
