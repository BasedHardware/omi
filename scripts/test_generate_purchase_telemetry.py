"""Focused generator/privacy contract, no services or customer data."""
import json
import unittest
from generate_purchase_telemetry import ROOT, render


class PurchaseGenerationTest(unittest.TestCase):
    def test_outputs_are_current_and_shared(self):
        outputs = render(json.loads((ROOT / 'contracts/analytics/events.json').read_text()))
        for path, expected in outputs.items():
            self.assertEqual((ROOT / path).read_text(), expected, path)
        ts = [content for path, content in outputs.items() if path.endswith('.ts')]
        self.assertEqual(ts[0], ts[1])

    def test_new_properties_cannot_become_free_text(self):
        doc = json.loads((ROOT / 'contracts/analytics/events.json').read_text())
        event = next(e for e in doc['events'] if e['id'] == 'paywallViewed')
        event['properties']['url'] = {'type': 'String', 'wire_name': 'url'}
        with self.assertRaises(AssertionError):
            render(doc)

    def test_wire_names_require_the_ingestion_prefix(self):
        doc = json.loads((ROOT / 'contracts/analytics/events.json').read_text())
        next(e for e in doc['events'] if e['id'] == 'checkoutOpened')['wire_name'] = 'Checkout Opened'
        with self.assertRaises(AssertionError):
            render(doc)


if __name__ == '__main__':
    unittest.main()
