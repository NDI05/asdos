import unittest

from packages.asdos_domain.geometry import inverse_rotate_point, rotate_point, transform_polygon, display_to_normalized
from packages.asdos_domain.scoring import DomainError


class GeometryTests(unittest.TestCase):
    def test_right_angle_transform_is_reversible(self):
        point = (0.23, 0.71)
        for degrees in (0, 90, 180, 270):
            transformed = rotate_point(point, degrees)
            restored = inverse_rotate_point(transformed, degrees)
            self.assertAlmostEqual(restored[0], point[0])
            self.assertAlmostEqual(restored[1], point[1])

    def test_polygon_and_display_mapping(self):
        polygon = ((0.1,0.2),(0.8,0.2),(0.8,0.9),(0.1,0.9))
        self.assertEqual(len(transform_polygon(polygon,90)),4)
        self.assertEqual(display_to_normalized((60,80),left=10,top=20,width=100,height=120), (0.5,0.5))
        with self.assertRaises(DomainError): rotate_point((1.2,0.2),90)


if __name__ == "__main__":
    unittest.main()
