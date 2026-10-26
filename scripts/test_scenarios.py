import unittest
from scenario_report import capacity,new_margin

class ScenarioTests(unittest.TestCase):
    def test_capacity_is_a_window_benchmark_and_never_exceeds_registered_stock(self):
        self.assertEqual(capacity(100,120,30),4)
        self.assertEqual(capacity(3,120,30),3)
        self.assertEqual(capacity(100,0,30),0)
        with self.assertRaises(ValueError):capacity(100,120,0)

    def test_break_even_and_preference_extremes(self):
        self.assertEqual(new_margin(100,0,0),100)
        self.assertEqual(new_margin(100,200,.5),100)
        self.assertEqual(new_margin(100,200,.25),0)
        self.assertEqual(new_margin(100,101,0),-1)
        self.assertEqual(new_margin(100,101,1),201)

if __name__=='__main__':unittest.main()
