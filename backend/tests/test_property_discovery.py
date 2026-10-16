"""Property discovery (PRD FR-7–FR-10): location matching, strict filters, ranges, alternatives, live-feed parsing."""
import unittest
from unittest import mock

from app.gateways.grid_gateway import GridOffPlanGateway, normalise_project
from app.services import location_service as L
from app.services.property_service import PropertyDiscoveryService as P, SearchFilters as F
from tests.fakes import listing

FEED = [
    listing(id="offplan-1", title="JVC Studio Tower", community="Jumeirah Village Circle", beds_min=0, beds_max=2, price_from=700_000, price_to=1_800_000),
    listing(id="offplan-2", title="Marina Heights", community="Dubai Marina", beds_min=1, beds_max=3, price_from=1_900_000, price_to=5_000_000, developer="Select Group"),
    listing(id="offplan-3", title="Price TBA Project", community="Business Bay", beds_min=1, beds_max=2, price_from=None, price_to=None, developer=None),
    listing(id="offplan-4", title="Saadiyat Villas", community="Saadiyat Island", city="Abu Dhabi", emirate="abu_dhabi", property_type="villa",
            beds_min=4, beds_max=5, price_from=9_000_000, price_to=12_000_000, developer="Aldar"),
]


class TestLocations(unittest.TestCase):

    def test_aliases_resolve_to_canonical(self):
        self.assertEqual(L.resolve("JVC")["name"], "Jumeirah Village Circle")
        self.assertEqual(L.resolve("2 bed in the Palm")["name"], "Palm Jumeirah")
        self.assertEqual(L.resolve("Damac Hills")["name"], "Damac Hills")        # not Dubai Hills
        self.assertEqual(L.resolve("Dubai Hills")["name"], "Dubai Hills Estate")
        self.assertEqual(L.resolve("Sharjah")["kind"], "emirate")
        self.assertEqual(L.resolve("anywhere in the UAE")["kind"], "nationwide")
        self.assertEqual(L.resolve("alt")["kind"], "unknown")

    def test_emirate_matching(self):
        loc = L.resolve("Abu Dhabi")
        self.assertTrue(L.matches(loc, "Saadiyat Island", "Abu Dhabi"))
        self.assertFalse(L.matches(loc, "Dubai Marina", "Dubai"))


class TestLiveFeedNormalisation(unittest.TestCase):

    def test_ranges_price_on_request_and_developer(self):
        item = {"id": 1, "name": "Barari Gate by ADE", "slug": "barari-gate", "bedrooms": "0 - 3.5 Bedrooms", "min_price": 0, "max_price": 0,
                "location": {"district": "Majan", "city": "Dubai"}, "property_type": "apartments", "construction_status": "under_construction"}
        l = normalise_project(item)
        self.assertEqual((l.beds_min, l.beds_max), (0, 3.5))
        self.assertIsNone(l.price_from)            # never an invented price
        self.assertTrue(l.price_on_request)
        self.assertEqual(l.developer, "ADE")
        self.assertEqual(l.property_type, "apartment")
        self.assertIsNone(l.listing_url)           # no URL unless a template is configured
        self.assertIsNone(l.size_sqft)


class TestSearch(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        patcher = mock.patch.object(GridOffPlanGateway, "all", new=mock.AsyncMock(return_value=FEED))
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_bedroom_range_matches(self):
        r = await P.search(F(location="JVC", bedrooms=2, status="off-plan"))
        self.assertEqual([l.id for l in r["results"]], ["offplan-1"])

    async def test_budget_excludes_price_on_request_and_over_budget(self):
        r = await P.search(F(location="Dubai", budget_max=2_000_000, status="off-plan"))
        ids = [l.id for l in r["results"]]
        self.assertIn("offplan-1", ids)
        self.assertIn("offplan-2", ids)
        self.assertNotIn("offplan-3", ids)

    async def test_type_is_strict_and_alternatives_are_explicit(self):
        r = await P.search(F(location="Dubai Marina", property_type="villa"))
        self.assertEqual(r["status"], "no_exact_matches")
        self.assertEqual(r["results"], [])
        self.assertTrue(r["alternatives"])
        self.assertIn(r["alternatives"][0]["relaxed_filter"], ("type", "location", "budget", "bedrooms"))

    async def test_developer_fuzzy_match(self):
        r = await P.search(F(developer="Selekt Group", status="off-plan"))
        self.assertEqual([l.id for l in r["results"]], ["offplan-2"])

    async def test_rent_is_honest(self):
        r = await P.search(F(location="Business Bay", purpose="rent"))
        self.assertEqual(r["status"], "no_rental_inventory")
        self.assertIn("not an outage", r["instruction"])

    async def test_unknown_location(self):
        r = await P.search(F(location="Atlantis Bay"))
        self.assertEqual(r["status"], "unknown_location")
        self.assertEqual(r["results"], [])

    async def test_results_capped(self):
        r = await P.search(F(location="UAE"))
        self.assertLessEqual(len(r["results"]), 5)

    async def test_sample_inventory_has_no_offplan_and_no_fake_urls(self):
        from app.gateways.inventory_gateway import SampleInventoryGateway
        sample = SampleInventoryGateway.all()
        self.assertTrue(sample)
        self.assertTrue(all(l.status == "ready" and l.listing_url is None and l.source == "sample" for l in sample))

    async def test_compare_has_no_invented_size_or_yield(self):
        cmp = P.compare(FEED[:2])
        for row in cmp["compared"]:
            self.assertNotIn("price_per_sqft_aed", row)       # no size in the feed -> no fabricated price/sqft
            self.assertNotIn("estimated_rental_yield", row)


if __name__ == "__main__":
    unittest.main()
