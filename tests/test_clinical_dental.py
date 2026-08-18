import unittest

from app.clinical import medinet_tooth_condition


class DentalConditionTests(unittest.TestCase):
    def test_maps_operator_label_tram_sau_to_current_medinet_label(self):
        self.assertEqual(medinet_tooth_condition("Trám sâu"), "Trám sâu lại")

    def test_keeps_current_medinet_label_and_other_conditions(self):
        self.assertEqual(medinet_tooth_condition("Trám sâu lại"), "Trám sâu lại")
        self.assertEqual(medinet_tooth_condition("Sâu"), "Sâu")


if __name__ == "__main__":
    unittest.main()
