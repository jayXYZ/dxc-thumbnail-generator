# DxC Thumbnail Generator

Generate Magic: The Gathering tournament thumbnails from a GIMP template.

The script prompts for tournament, round, deck, and card names, downloads original-print card art from Scryfall, updates `thumbnail-template.xcf`, and exports a PNG into `exports/`.

## Requirements

- Python 3
- GIMP 3 available as `gimp` on your `PATH`
- `thumbnail-template.xcf` in this folder
- Internet access for Scryfall card lookup and art download
- The `Beleren Small Caps Bold` font installed for the intended text styling

## Usage

Run:

```bash
python3 thumbnail_generator.py
```

Answer the prompts:

1. Tournament name
2. Round name
3. Player 1 deck name
4. Player 1 card name
5. Player 2 deck name
6. Player 2 card name

The script uses fuzzy Scryfall lookup, then searches for the original non-reprint printing. The final file is exported to:

```text
exports/[event-name]-[round-name]-[deck-1-name]-vs-[deck-2-name].png
```

## Template Layer Names

The GIMP template must include these layer names:

- `Event Title`
- `Player 1 Deck Image`
- `Player 2 Deck Image`
- `Player 1 Deck Name`
- `Player 2 Deck Name`

Deck names longer than 11 characters are split across two lines on whole-word boundaries before being placed in the thumbnail.
