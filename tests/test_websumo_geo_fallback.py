import math
import sys
import unittest

# websumo_interface lives in the engine's flat src directory and does
# its imports accordingly, so the directory itself goes on the path
sys.path.insert(0, "services/simengine/src")

from websumo_interface import (  # noqa: E402
    EARTH_RADIUS_M,
    SYNTHETIC_PROJECTION,
    geo_reference_net,
    net_offset_from_net,
    synthetic_lonlat,
)

NO_GEO_NET = b"""<?xml version="1.0" encoding="UTF-8"?>
<net version="1.16">
    <location netOffset="10.00,20.00" convBoundary="0.00,0.00,100.00,50.00" origBoundary="-10000000000.00,-10000000000.00,10000000000.00,10000000000.00" projParameter="!"/>
    <edge id="e1"/>
</net>
"""

GEO_NET = b"""<?xml version="1.0" encoding="UTF-8"?>
<net version="1.16">
    <location netOffset="-380370.77,-6669419.92" convBoundary="0.00,0.00,100.00,50.00" origBoundary="24.68,59.44,29.64,60.18" projParameter="+proj=utm +zone=35 +ellps=WGS84 +datum=WGS84 +units=m +no_defs"/>
    <edge id="e1"/>
</net>
"""


class TestGeoReferenceNet(unittest.TestCase):
    def test_no_geo_net_gets_the_synthetic_projection(self):
        served, offset = geo_reference_net(NO_GEO_NET)
        self.assertIn(SYNTHETIC_PROJECTION, served)
        self.assertNotIn(b'projParameter="!"', served)
        self.assertEqual(offset, (10.0, 20.0))

    def test_geo_net_passes_through_unchanged(self):
        served, offset = geo_reference_net(GEO_NET)
        self.assertEqual(served, GEO_NET)
        self.assertIsNone(offset)

    def test_net_offset_defaults_to_zero_without_location(self):
        self.assertEqual(net_offset_from_net(b"<net><edge/></net>"),
                         (0.0, 0.0))


class TestSyntheticLonlat(unittest.TestCase):
    def test_origin_is_null_island(self):
        self.assertEqual(synthetic_lonlat(0.0, 0.0), (0.0, 0.0))

    def test_net_offset_is_removed_first(self):
        self.assertEqual(synthetic_lonlat(10.0, 20.0, (10.0, 20.0)),
                         (0.0, 0.0))

    def test_matches_spherical_mercator_inverse(self):
        # forward spherical web mercator of a known point, then back
        lon_deg, lat_deg = 0.01, -0.02
        x = EARTH_RADIUS_M * math.radians(lon_deg)
        y = EARTH_RADIUS_M * math.log(
            math.tan(math.pi / 4 + math.radians(lat_deg) / 2))
        lon, lat = synthetic_lonlat(x, y)
        self.assertAlmostEqual(lon, lon_deg, places=12)
        self.assertAlmostEqual(lat, lat_deg, places=12)

    def test_meter_scale_near_the_anchor(self):
        # one meter is about 1/111320 degrees at the equator
        lon, lat = synthetic_lonlat(1.0, 1.0)
        self.assertAlmostEqual(lon * 111320, 1.0, places=2)
        self.assertAlmostEqual(lat * 111320, 1.0, places=2)


if __name__ == "__main__":
    unittest.main()
