import io
import json
import unittest
from urllib.parse import parse_qs, urlparse

import thumbnail_generator as tg


class FakeResponse:
    def __init__(self, payload=None, body=None, status=200):
        self.payload = payload
        self.body = body
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        return False

    def read(self):
        if self.body is not None:
            return self.body
        return json.dumps(self.payload).encode("utf-8")


class FakeOpener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request, timeout=0):
        self.requests.append((request, timeout))
        response = self.responses.pop(0)
        if response.status >= 400:
            raise tg.ScryfallError(f"HTTP {response.status}")
        return response


class HelperTests(unittest.TestCase):
    def test_prompt_required_reprompts_until_non_empty(self):
        answers = iter(["", "  ", "Legacy Showcase"])
        prompts = []

        def fake_input(prompt):
            prompts.append(prompt)
            return next(answers)

        output = io.StringIO()

        result = tg.prompt_required("Tournament?", input_func=fake_input, output=output)

        self.assertEqual(result, "Legacy Showcase")
        self.assertEqual(prompts, ["Tournament?", "Tournament?", "Tournament?"])
        self.assertIn("Please enter a value.", output.getvalue())

    def test_slugify_collapses_unsafe_characters(self):
        self.assertEqual(tg.slugify(" SCG CON: $20K Modern! "), "scg-con-20k-modern")

    def test_build_export_filename_uses_required_format(self):
        self.assertEqual(
            tg.build_export_filename("SCG CON", "Round 4", "Dimir Reanimator", "Izzet Phoenix"),
            "scg-con-round-4-dimir-reanimator-vs-izzet-phoenix.png",
        )

    def test_extract_art_crop_prefers_top_level_image_uri(self):
        card = {
            "name": "Lightning Bolt",
            "image_uris": {
                "art_crop": "https://img.scryfall.io/cards/art_crop/front/bolt.jpg"
            },
        }

        self.assertEqual(
            tg.extract_art_crop_uri(card),
            "https://img.scryfall.io/cards/art_crop/front/bolt.jpg",
        )

    def test_extract_art_crop_uses_first_face_with_art_crop(self):
        card = {
            "name": "Fire // Ice",
            "card_faces": [
                {"name": "Fire", "image_uris": {}},
                {
                    "name": "Ice",
                    "image_uris": {
                        "art_crop": "https://img.scryfall.io/cards/art_crop/front/ice.jpg"
                    },
                },
            ],
        }

        self.assertEqual(
            tg.extract_art_crop_uri(card),
            "https://img.scryfall.io/cards/art_crop/front/ice.jpg",
        )

    def test_build_original_print_query_uses_oracle_id_and_not_reprint(self):
        self.assertEqual(
            tg.build_original_print_query("abc-123"),
            "oracleid:abc-123 not:reprint",
        )

    def test_cover_crop_scales_to_cover_and_centres_source(self):
        crop = tg.cover_crop(source_width=1000, source_height=500, target_width=400, target_height=400)

        self.assertEqual(crop.scaled_width, 800)
        self.assertEqual(crop.scaled_height, 400)
        self.assertEqual(crop.offset_x, -200)
        self.assertEqual(crop.offset_y, 0)


class ScryfallClientTests(unittest.TestCase):
    def test_resolve_original_art_crop_uses_fuzzy_then_original_print_search(self):
        opener = FakeOpener(
            [
                FakeResponse({"name": "Lightning Bolt", "oracle_id": "oracle-bolt"}),
                FakeResponse(
                    {
                        "data": [
                            {
                                "name": "Lightning Bolt",
                                "image_uris": {
                                    "art_crop": "https://img.scryfall.io/cards/art_crop/bolt.jpg"
                                },
                            }
                        ]
                    }
                ),
            ]
        )
        client = tg.ScryfallClient(opener=opener)

        result = client.resolve_original_art_crop("lightnig blot")

        self.assertEqual(result.input_name, "lightnig blot")
        self.assertEqual(result.resolved_name, "Lightning Bolt")
        self.assertEqual(result.art_crop_uri, "https://img.scryfall.io/cards/art_crop/bolt.jpg")

        named_url = urlparse(opener.requests[0][0].full_url)
        self.assertEqual(named_url.path, "/cards/named")
        self.assertEqual(parse_qs(named_url.query)["fuzzy"], ["lightnig blot"])

        search_url = urlparse(opener.requests[1][0].full_url)
        self.assertEqual(search_url.path, "/cards/search")
        self.assertEqual(parse_qs(search_url.query)["q"], ["oracleid:oracle-bolt not:reprint"])

    def test_scryfall_requests_include_required_headers(self):
        opener = FakeOpener(
            [
                FakeResponse({"name": "Brainstorm", "oracle_id": "oracle-brainstorm"}),
                FakeResponse(
                    {
                        "data": [
                            {
                                "name": "Brainstorm",
                                "image_uris": {
                                    "art_crop": "https://img.scryfall.io/cards/art_crop/brainstorm.jpg"
                                },
                            }
                        ]
                    }
                ),
            ]
        )
        client = tg.ScryfallClient(opener=opener)

        client.resolve_original_art_crop("brainstorm")

        for request, _timeout in opener.requests:
            self.assertIn("dxc-thumbnail-generator", request.headers["User-agent"])
            self.assertEqual(request.headers["Accept"], "application/json;q=0.9,*/*;q=0.8")

    def test_download_art_writes_response_bytes(self):
        opener = FakeOpener([FakeResponse(body=b"fake-jpg-bytes")])
        client = tg.ScryfallClient(opener=opener)
        output = io.BytesIO()

        client.download_art("https://img.scryfall.io/cards/art_crop/bolt.jpg", output)

        self.assertEqual(output.getvalue(), b"fake-jpg-bytes")
        self.assertEqual(opener.requests[0][0].full_url, "https://img.scryfall.io/cards/art_crop/bolt.jpg")

    def test_resolve_original_art_crop_errors_when_no_art_crop_exists(self):
        opener = FakeOpener(
            [
                FakeResponse({"name": "No Art Card", "oracle_id": "oracle-no-art"}),
                FakeResponse({"data": [{"name": "No Art Card", "image_uris": {}}]}),
            ]
        )
        client = tg.ScryfallClient(opener=opener)

        with self.assertRaisesRegex(tg.ScryfallError, "No art_crop"):
            client.resolve_original_art_crop("no art")


class GimpRunnerTests(unittest.TestCase):
    def test_build_gimp_batch_script_targets_required_layers_and_exports_png(self):
        script = tg.build_gimp_batch_script(
            template_path="/project/thumbnail-template.xcf",
            output_path="/project/exports/event-round-deck-vs-deck.png",
            event_title="Legacy 5K\nRound 2",
            player_1_deck_name="Dimir Reanimator",
            player_2_deck_name="Izzet Phoenix",
            player_1_art_path="/tmp/player-1.jpg",
            player_2_art_path="/tmp/player-2.jpg",
        )

        self.assertIn("Event Title", script)
        self.assertIn("Player 1 Deck Name", script)
        self.assertIn("Player 2 Deck Name", script)
        self.assertIn("Player 1 Deck Image", script)
        self.assertIn("Player 2 Deck Image", script)
        self.assertIn("Legacy 5K\\nRound 2", script)
        self.assertIn("Dimir Reanimator", script)
        self.assertIn("Izzet Phoenix", script)
        self.assertIn("max(target_width / source_width, target_height / source_height)", script)
        self.assertIn("new_layer.resize(target_width, target_height, offset_x, offset_y)", script)
        self.assertIn("Gimp.file_save", script)
        self.assertIn("/project/exports/event-round-deck-vs-deck.png", script)

    def test_build_gimp_batch_script_replaces_text_inside_existing_markup(self):
        script = tg.build_gimp_batch_script(
            template_path="/project/thumbnail-template.xcf",
            output_path="/project/exports/event-round-deck-vs-deck.png",
            event_title="Legacy 5K\nRound 2",
            player_1_deck_name="Dimir Reanimator",
            player_2_deck_name="Izzet Phoenix",
            player_1_art_path="/tmp/player-1.jpg",
            player_2_art_path="/tmp/player-2.jpg",
        )

        self.assertIn("import xml.etree.ElementTree as ET", script)
        self.assertIn("def replace_markup_text(markup, text):", script)
        self.assertIn("existing_markup = layer.get_markup()", script)
        self.assertIn("layer.set_markup(replace_markup_text(existing_markup, text))", script)
        self.assertNotIn("display_text = text.upper()", script)

    def test_build_gimp_batch_script_sets_beleren_font_in_markup(self):
        script = tg.build_gimp_batch_script(
            template_path="/project/thumbnail-template.xcf",
            output_path="/project/exports/event-round-deck-vs-deck.png",
            event_title="Legacy 5K\nRound 2",
            player_1_deck_name="Dimir Reanimator",
            player_2_deck_name="Izzet Phoenix",
            player_1_art_path="/tmp/player-1.jpg",
            player_2_art_path="/tmp/player-2.jpg",
        )

        self.assertIn('TEXT_FONT = "Beleren Small Caps Bold"', script)
        self.assertIn('element.set("font", TEXT_FONT)', script)
        self.assertIn("ensure_markup_font(root)", script)

    def test_build_gimp_batch_script_fits_styled_text_into_layout_boxes(self):
        script = tg.build_gimp_batch_script(
            template_path="/project/thumbnail-template.xcf",
            output_path="/project/exports/event-round-deck-vs-deck.png",
            event_title="Legacy 5K\nRound 2",
            player_1_deck_name="Dimir Reanimator",
            player_2_deck_name="Izzet Phoenix",
            player_1_art_path="/tmp/player-1.jpg",
            player_2_art_path="/tmp/player-2.jpg",
        )

        self.assertIn("TEXT_BOXES = {", script)
        self.assertIn('"Event Title": {"box_layer": "NEPM Summer background"', script)
        self.assertIn('"Player 1 Deck Name": {"x": 92, "y": 895, "width": 620', script)
        self.assertIn('"Player 2 Deck Name": {"x": 1180, "y": 895, "width": 650', script)
        self.assertIn("def fit_text_layer(image, layer, layer_name):", script)
        self.assertIn("scale = min(1, box_width / text_width, box_height / text_height)", script)
        self.assertIn("layer.scale(scaled_width, scaled_height, False)", script)

    def test_build_gimp_command_uses_python_batch_interpreter(self):
        command = tg.build_gimp_command("/opt/homebrew/bin/gimp", "/tmp/batch.py")

        self.assertEqual(
            command,
            [
                "/opt/homebrew/bin/gimp",
                "-i",
                "--batch-interpreter=python-fu-eval",
                "-b",
                "exec(compile(open('/tmp/batch.py', 'r', encoding='utf-8').read(), '/tmp/batch.py', 'exec'))",
                "--quit",
            ],
        )


if __name__ == "__main__":
    unittest.main()
