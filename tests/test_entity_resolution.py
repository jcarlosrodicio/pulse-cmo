import unittest

from pulse.entity_resolution import build_entity_profile, deterministic_entity_check


class EntityResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = build_entity_profile(
            {
                "name": "Tally",
                "url": "https://tally-rcuadrado.vercel.app/",
                "description": "Manual-first personal expense tracking app.",
                "brief": {
                    "assets": [
                        "https://apps.apple.com/es/app/tally-control-de-gastos/id6768200630",
                        "https://play.google.com/store/apps/details?id=com.rcuadrado.tally",
                    ]
                },
            }
        )

    def test_accepts_specific_expense_tracker_context(self) -> None:
        cases = [
            {"title": "Tally expense tracker adds faster entry", "url": "https://example.com/a"},
            {"title": "Review of Tally personal finance app", "url": "https://example.com/b"},
            {"title": "Tally mobile app", "url": "https://tally-rcuadrado.vercel.app/en"},
            {"title": "Android app", "url": "https://play.google.com/store/apps/details?id=com.rcuadrado.tally"},
        ]
        for item in cases:
            with self.subTest(item=item):
                self.assertEqual(deterministic_entity_check(item, self.profile)["decision"], "accept")

    def test_rejects_conflicting_tally_entities(self) -> None:
        cases = [
            {"title": "Tally.so launches AI forms", "url": "https://tally.so"},
            {"title": "Tally form builder for surveys", "url": "https://example.com/forms"},
            {"title": "TallyPrime accounting software", "url": "https://tallysolutions.com"},
            {"title": "Tally helps pay off credit card debt", "url": "https://meettally.com"},
        ]
        for item in cases:
            with self.subTest(item=item):
                self.assertEqual(deterministic_entity_check(item, self.profile)["decision"], "reject")

    def test_marks_shared_name_without_context_ambiguous(self) -> None:
        result = deterministic_entity_check(
            {"title": "Tally launches a new feature", "url": "https://example.com/news"},
            self.profile,
        )
        self.assertEqual(result["decision"], "ambiguous")


if __name__ == "__main__":
    unittest.main()
