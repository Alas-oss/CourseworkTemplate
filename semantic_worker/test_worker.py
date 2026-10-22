import unittest

import worker

class TestPredict(unittest.TestCase):
    def test_take_item(self):
        action, confidence = worker.predict("collect fragment")
        self.assertEqual(action, "TAKE_ITEM")
        self.assertGreater(confidence, 0.35)

    def test_move(self):
        action, _ = worker.predict("go to the south")
        self.assertEqual(action, "MOVE")

    def test_hint(self):
        action, _ = worker.predict("give me a hint")
        self.assertEqual(action, "ASK_FOR_HINT")

    def test_inventory(self):
        action, _ = worker.predict("show my inventory")
        self.assertEqual(action, "CHECK_INVENTORY")

    def test_empty_text_is_unknown(self):
        self.assertEqual(worker.predict("    "), ("UNKOWN", 0.0))

    def test_confidence_range(self):
        _, confidence = worker.predict("look around")
        self.assertTrue(0.0 <= confidence <= 1.0)

class TestEntities(unittest.TestCase):
    def test_item_tyoe(self):
        self.assertEqual(
            worker.entities("collect fragment"),
            {"item_type": "fragment"}
        )

    def test_direction(self):
        self.assertEqual(
            worker.entities("go to the south"),
            {"direction": "south"}
        )

    def test_specific_item(self):
        self.assertEqual(
            worker.entities("take the access card"),
            {"item": "access_card"}
        )

    def test_numbered_fragment(self):
        self.assertEqual(
            worker.entities("take fragment 2"),
            {"item": "fragment_2"}
        )

    def test_nothing_found(self):
        self.assertEqual(worker.entities("hello there"), {})


if __name__ == "__main__":
    unittest.main()