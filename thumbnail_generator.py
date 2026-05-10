#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
import json
import shutil
import subprocess
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class CropPlacement:
    scaled_width: int
    scaled_height: int
    offset_x: int
    offset_y: int


@dataclass(frozen=True)
class CardArt:
    input_name: str
    resolved_name: str
    art_crop_uri: str


class ScryfallError(RuntimeError):
    pass


class ThumbnailError(RuntimeError):
    pass


def prompt_required(prompt: str, input_func=input, output=sys.stdout) -> str:
    while True:
        value = input_func(prompt).strip()
        if value:
            return value
        print("Please enter a value.", file=output)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return slug.strip("-") or "untitled"


def build_export_filename(event_name: str, round_name: str, deck_1_name: str, deck_2_name: str) -> str:
    parts = [
        slugify(event_name),
        slugify(round_name),
        slugify(deck_1_name),
        "vs",
        slugify(deck_2_name),
    ]
    return "-".join(parts) + ".png"


def extract_art_crop_uri(card: dict) -> str | None:
    image_uris = card.get("image_uris") or {}
    if image_uris.get("art_crop"):
        return image_uris["art_crop"]

    for face in card.get("card_faces") or []:
        face_image_uris = face.get("image_uris") or {}
        if face_image_uris.get("art_crop"):
            return face_image_uris["art_crop"]

    return None


def build_original_print_query(oracle_id: str) -> str:
    return f"oracleid:{oracle_id} not:reprint"


def cover_crop(source_width: int, source_height: int, target_width: int, target_height: int) -> CropPlacement:
    if source_width <= 0 or source_height <= 0 or target_width <= 0 or target_height <= 0:
        raise ValueError("source and target dimensions must be positive")

    scale = max(target_width / source_width, target_height / source_height)
    scaled_width = round(source_width * scale)
    scaled_height = round(source_height * scale)
    offset_x = round((target_width - scaled_width) / 2)
    offset_y = round((target_height - scaled_height) / 2)

    return CropPlacement(
        scaled_width=scaled_width,
        scaled_height=scaled_height,
        offset_x=offset_x,
        offset_y=offset_y,
    )


class ScryfallClient:
    API_BASE_URL = "https://api.scryfall.com"
    USER_AGENT = "dxc-thumbnail-generator/1.0"
    ACCEPT = "application/json;q=0.9,*/*;q=0.8"

    def __init__(self, opener=urlopen, timeout: int = 20):
        self.opener = opener
        self.timeout = timeout

    def resolve_original_art_crop(self, card_name: str) -> CardArt:
        resolved = self._get_json("/cards/named", {"fuzzy": card_name})
        oracle_id = resolved.get("oracle_id")
        resolved_name = resolved.get("name") or card_name
        if not oracle_id:
            raise ScryfallError(f"Scryfall did not return an oracle_id for {card_name!r}.")

        original_prints = self._get_json(
            "/cards/search",
            {"q": build_original_print_query(oracle_id), "order": "released", "unique": "prints"},
        )
        for card in original_prints.get("data") or []:
            art_crop_uri = extract_art_crop_uri(card)
            if art_crop_uri:
                return CardArt(
                    input_name=card_name,
                    resolved_name=resolved_name,
                    art_crop_uri=art_crop_uri,
                )

        raise ScryfallError(f"No art_crop found for original non-reprint printing of {resolved_name}.")

    def download_art(self, art_crop_uri: str, output) -> None:
        request = self._request(art_crop_uri)
        with self.opener(request, timeout=self.timeout) as response:
            output.write(response.read())

    def _get_json(self, path: str, params: dict[str, str]) -> dict:
        url = f"{self.API_BASE_URL}{path}?{urlencode(params)}"
        request = self._request(url)
        try:
            with self.opener(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except ScryfallError:
            raise
        except Exception as exc:
            raise ScryfallError(f"Scryfall request failed for {path}: {exc}") from exc

    def _request(self, url: str) -> Request:
        return Request(
            url,
            headers={
                "User-Agent": self.USER_AGENT,
                "Accept": self.ACCEPT,
            },
        )


def build_gimp_command(gimp_executable: str, batch_script_path: str) -> list[str]:
    return [
        gimp_executable,
        "-i",
        "--batch-interpreter=python-fu-eval",
        "-b",
        f"exec(compile(open({batch_script_path!r}, 'r', encoding='utf-8').read(), {batch_script_path!r}, 'exec'))",
        "--quit",
    ]


def build_gimp_batch_script(
    *,
    template_path: str,
    output_path: str,
    event_title: str,
    player_1_deck_name: str,
    player_2_deck_name: str,
    player_1_art_path: str,
    player_2_art_path: str,
) -> str:
    values = {
        "template_path": template_path,
        "output_path": output_path,
        "event_title": event_title,
        "player_1_deck_name": player_1_deck_name,
        "player_2_deck_name": player_2_deck_name,
        "player_1_art_path": player_1_art_path,
        "player_2_art_path": player_2_art_path,
    }
    return f"""
import xml.etree.ElementTree as ET

from gi.repository import Gio

TEMPLATE_PATH = {values["template_path"]!r}
OUTPUT_PATH = {values["output_path"]!r}
EVENT_TITLE = {values["event_title"]!r}
PLAYER_1_DECK_NAME = {values["player_1_deck_name"]!r}
PLAYER_2_DECK_NAME = {values["player_2_deck_name"]!r}
PLAYER_1_ART_PATH = {values["player_1_art_path"]!r}
PLAYER_2_ART_PATH = {values["player_2_art_path"]!r}

TEXT_BOXES = {{
    "Event Title": {{"box_layer": "NEPM Summer background", "padding_x": 32, "padding_y": 0, "align": "center"}},
    "Player 1 Deck Name": {{"x": 92, "y": 895, "width": 620, "height": 121, "align": "left"}},
    "Player 2 Deck Name": {{"x": 1180, "y": 895, "width": 650, "height": 121, "align": "right"}},
}}
TEXT_FONT = "Beleren Small Caps Bold"


def fail(message):
    raise RuntimeError(message)


def layer_children(layer):
    try:
        return list(layer.get_children() or [])
    except Exception:
        return []


def find_layer(image, layer_name):
    stack = list(image.get_layers())
    while stack:
        layer = stack.pop(0)
        if layer.get_name() == layer_name:
            return layer
        stack[0:0] = layer_children(layer)
    fail("Required layer not found: " + layer_name)


def ensure_markup_font(root):
    spans = list(root.iter("span"))
    font_spans = [element for element in spans if "font" in element.attrib]
    targets = font_spans or spans
    for element in targets:
        element.set("font", TEXT_FONT)


def replace_markup_text(markup, text):
    root = ET.fromstring(markup)
    ensure_markup_font(root)
    text_holder = None
    for element in root.iter():
        if element.text:
            text_holder = element

    if text_holder is None:
        spans = list(root.iter("span"))
        text_holder = spans[-1] if spans else root

    for element in root.iter():
        element.text = None
        element.tail = None
    text_holder.text = text
    return ET.tostring(root, encoding="unicode")


def set_text_preserving_markup(layer, text):
    existing_markup = layer.get_markup()
    if existing_markup:
        layer.set_markup(replace_markup_text(existing_markup, text))
        return
    layer.set_text(text)


def layer_box(layer):
    has_offsets, x, y = layer.get_offsets()
    if not has_offsets:
        x = 0
        y = 0
    return x, y, layer.get_width(), layer.get_height()


def text_box(image, layer, layer_name):
    box = TEXT_BOXES.get(layer_name, {{}})
    if box.get("box_layer"):
        x, y, width, height = layer_box(find_layer(image, box["box_layer"]))
    else:
        x = box.get("x")
        y = box.get("y")
        width = box.get("width")
        height = box.get("height")
        if x is None or y is None or width is None or height is None:
            x, y, width, height = layer_box(layer)

    padding_x = box.get("padding_x", 0)
    padding_y = box.get("padding_y", 0)
    return (
        x + padding_x,
        y + padding_y,
        width - (padding_x * 2),
        height - (padding_y * 2),
        box.get("align", "left"),
    )


def fit_text_layer(image, layer, layer_name):
    box_x, box_y, box_width, box_height, align = text_box(image, layer, layer_name)
    text_width = layer.get_width()
    text_height = layer.get_height()
    if text_width <= 0 or text_height <= 0:
        fail("Text layer has invalid dimensions after update: " + layer_name)

    scale = min(1, box_width / text_width, box_height / text_height)
    scaled_width = round(text_width * scale)
    scaled_height = round(text_height * scale)
    if scaled_width != text_width or scaled_height != text_height:
        layer.scale(scaled_width, scaled_height, False)

    if align == "center":
        target_x = round(box_x + ((box_width - scaled_width) / 2))
    elif align == "right":
        target_x = round(box_x + box_width - scaled_width)
    else:
        target_x = round(box_x)
    target_y = round(box_y + ((box_height - scaled_height) / 2))
    layer.set_offsets(target_x, target_y)


def set_text_layer(image, layer_name, text):
    layer = find_layer(image, layer_name)
    if not hasattr(layer, "set_text"):
        fail("Required layer is not a text layer: " + layer_name)
    set_text_preserving_markup(layer, text)
    fit_text_layer(image, layer, layer_name)


def replace_image_layer(image, layer_name, art_path):
    old_layer = find_layer(image, layer_name)
    target_width = old_layer.get_width()
    target_height = old_layer.get_height()
    has_offsets, target_x, target_y = old_layer.get_offsets()
    if not has_offsets:
        target_x = 0
        target_y = 0
    parent = old_layer.get_parent()
    position = image.get_item_position(old_layer)

    new_layer = Gimp.file_load_layer(
        Gimp.RunMode.NONINTERACTIVE,
        image,
        Gio.File.new_for_path(art_path),
    )
    source_width = new_layer.get_width()
    source_height = new_layer.get_height()
    scale = max(target_width / source_width, target_height / source_height)
    scaled_width = round(source_width * scale)
    scaled_height = round(source_height * scale)
    offset_x = round((target_width - scaled_width) / 2)
    offset_y = round((target_height - scaled_height) / 2)

    image.insert_layer(new_layer, parent, position)
    new_layer.scale(scaled_width, scaled_height, False)
    new_layer.resize(target_width, target_height, offset_x, offset_y)
    new_layer.set_offsets(target_x, target_y)
    new_layer.set_name(layer_name)
    image.remove_layer(old_layer)


image = Gimp.file_load(
    Gimp.RunMode.NONINTERACTIVE,
    Gio.File.new_for_path(TEMPLATE_PATH),
)
set_text_layer(image, "Event Title", EVENT_TITLE)
set_text_layer(image, "Player 1 Deck Name", PLAYER_1_DECK_NAME)
set_text_layer(image, "Player 2 Deck Name", PLAYER_2_DECK_NAME)
replace_image_layer(image, "Player 1 Deck Image", PLAYER_1_ART_PATH)
replace_image_layer(image, "Player 2 Deck Image", PLAYER_2_ART_PATH)
Gimp.file_save(
    Gimp.RunMode.NONINTERACTIVE,
    image,
    Gio.File.new_for_path(OUTPUT_PATH),
)
image.delete()
""".strip()


def run_gimp_export(
    *,
    template_path: Path,
    output_path: Path,
    event_title: str,
    player_1_deck_name: str,
    player_2_deck_name: str,
    player_1_art_path: Path,
    player_2_art_path: Path,
    gimp_executable: str | None = None,
) -> None:
    gimp = gimp_executable or shutil.which("gimp")
    if not gimp:
        raise ThumbnailError("GIMP executable not found on PATH.")

    script = build_gimp_batch_script(
        template_path=str(template_path),
        output_path=str(output_path),
        event_title=event_title,
        player_1_deck_name=player_1_deck_name,
        player_2_deck_name=player_2_deck_name,
        player_1_art_path=str(player_1_art_path),
        player_2_art_path=str(player_2_art_path),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp_dir:
        batch_script_path = Path(temp_dir) / "gimp-thumbnail-export.py"
        batch_script_path.write_text(script, encoding="utf-8")
        command = build_gimp_command(gimp, str(batch_script_path))
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        if completed.returncode != 0:
            details = (completed.stderr or completed.stdout).strip()
            raise ThumbnailError(f"GIMP export failed: {details}")


def collect_answers() -> dict[str, str]:
    return {
        "event_name": prompt_required("What is the name of the tournament? "),
        "round_name": prompt_required("What round is the video of? "),
        "player_1_deck_name": prompt_required("What is Player 1's deck name? "),
        "player_1_card_name": prompt_required("What card should be used for Player 1? "),
        "player_2_deck_name": prompt_required("What is Player 2's deck name? "),
        "player_2_card_name": prompt_required("What card should be used for Player 2? "),
    }


def generate_thumbnail(base_dir: Path | None = None) -> Path:
    base_dir = base_dir or Path(__file__).resolve().parent
    template_path = base_dir / "thumbnail-template.xcf"
    if not template_path.exists():
        raise ThumbnailError(f"Template not found: {template_path}")

    answers = collect_answers()
    client = ScryfallClient()
    player_1_art = client.resolve_original_art_crop(answers["player_1_card_name"])
    player_2_art = client.resolve_original_art_crop(answers["player_2_card_name"])
    print(f"Player 1 card resolved to: {player_1_art.resolved_name}")
    print(f"Player 2 card resolved to: {player_2_art.resolved_name}")

    export_filename = build_export_filename(
        answers["event_name"],
        answers["round_name"],
        answers["player_1_deck_name"],
        answers["player_2_deck_name"],
    )
    output_path = base_dir / "exports" / export_filename

    with tempfile.TemporaryDirectory() as temp_dir:
        player_1_art_path = Path(temp_dir) / "player-1-art.jpg"
        player_2_art_path = Path(temp_dir) / "player-2-art.jpg"
        with player_1_art_path.open("wb") as output:
            client.download_art(player_1_art.art_crop_uri, output)
        with player_2_art_path.open("wb") as output:
            client.download_art(player_2_art.art_crop_uri, output)

        run_gimp_export(
            template_path=template_path,
            output_path=output_path,
            event_title=f"{answers['event_name']}\n{answers['round_name']}",
            player_1_deck_name=answers["player_1_deck_name"],
            player_2_deck_name=answers["player_2_deck_name"],
            player_1_art_path=player_1_art_path,
            player_2_art_path=player_2_art_path,
        )

    return output_path


def main() -> int:
    try:
        output_path = generate_thumbnail()
    except (ScryfallError, ThumbnailError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Exported thumbnail: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
