import os
import tempfile
import unittest

import worker


class TestClean(unittest.TestCase):
    def test_limits_words(self):
        out = worker.clean(" ".join(["word"] * 100))
        self.assertLessEqual(len(out.split()), worker.WORD_LIMIT)
        self.assertTrue(out.endswith("."))

    def test_strips_quotes_and_newlines(self):
        self.assertEqual(
            worker.clean('"Take the card.\nThen go north."'),
            "Take the card. Then go north."
        )

    def test_short_text_unchanged(self):
        self.assertEqual(worker.clean("Go north."), "Go north.")


class TestHelpers(unittest.TestCase):
    def test_cosine(self):
        self.assertAlmostEqual(worker.cosine([1, 0], [1, 0]), 1.0)
        self.assertAlmostEqual(worker.cosine([1, 0], [0, 1]), 0.0)
        self.assertEqual(worker.cosine([0, 0], [1, 0]), 0.0)

    def test_load_chunks_uses_headings(self):
        with tempfile.TemporaryDirectory() as folder:
            with open(os.path.join(folder, "walkthrough.md"), "w") as f:
                f.write(
                    "# Title\n\n## Reception\n\nTake the card first.\n\n"
                    "## Archive\n\nTake fragment 1.\n"
                )
            with open(os.path.join(folder, "notes.txt"), "w") as f:
                f.write("ignored")

            chunks = worker.load_chunks(folder)

        self.assertEqual(
            [c["text"] for c in chunks],
            ["Reception: Take the card first.", "Archive: Take fragment 1."]
        )

    def test_load_chunks_missing_folder(self):
        self.assertEqual(worker.load_chunks("/no/such/folder"), [])

    def test_has_model(self):
        self.assertTrue(worker.has_model({"nomic-embed-text:latest"}, "nomic-embed-text"))
        self.assertTrue(worker.has_model({"qwen2.5:1.5b"}, "qwen2.5:1.5b"))
        self.assertFalse(worker.has_model(set(), "qwen2.5:1.5b"))


class TestPrompt(unittest.TestCase):
    def test_build_messages_contains_facts_and_guidance(self):
        payload = {
            "text": "take the card",
            "action": "TAKE_ITEM",
            "success": True,
            "result_message": "You collected access card.",
            "state": {
                "location": "reception",
                "inventory": ["access_card"],
                "unlocked": [],
                "status": "IN_PROGRESS",
                "room": {"name": "Reception", "description": "A console.",
                         "exits": ["north"], "items": []}
            }
        }

        messages = worker.build_messages(payload, ["Use British English."])
        user = messages[1]["content"]

        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("You collected access card.", user)
        self.assertIn("Inventory: access card", user)
        self.assertIn("Use British English.", user)
        self.assertIn("45 words", user)

    def test_fallback(self):
        self.assertEqual(
            worker.fallback({"result_message": "The door is locked."}),
            "The door is locked."
        )
        self.assertEqual(worker.fallback({}), "Please try another command.")


if __name__ == "__main__":
    unittest.main()