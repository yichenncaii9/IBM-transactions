"""Small correctness checks for the temporal tracing primitives."""
import unittest

from validate import pattern_analysis


def edge(time, source, destination, currency):
    return [f'2022/09/01 {time}', '001', source, '001', destination,
            '100', currency, '100', currency, 'ACH', '1']


class TemporalTests(unittest.TestCase):
    def measure(self, edges):
        metrics, endpoints = pattern_analysis([{'type': 'TEST', 'edges': edges}])
        return metrics[0], endpoints

    def test_currency_change_between_same_currency_transfers(self):
        m, ends = self.measure([edge('00:00', 'A', 'B', 'Euro'),
                                edge('00:01', 'B', 'C', 'US Dollar')])
        self.assertEqual(m['max_temporal_hops'], 2)
        self.assertEqual(m['currency_switch_edges'], 1)
        self.assertEqual(m['currencies'], 2)
        self.assertEqual(ends, {('001', 'C')})

    def test_same_minute_does_not_create_order(self):
        m, _ = self.measure([edge('00:00', 'A', 'B', 'Euro'),
                             edge('00:00', 'B', 'C', 'US Dollar')])
        self.assertEqual(m['max_temporal_hops'], 1)
        self.assertEqual(m['currency_switch_edges'], 0)

    def test_cycle_has_hops_but_no_sink(self):
        m, ends = self.measure([edge('00:00', 'A', 'B', 'Euro'),
                                edge('00:01', 'B', 'A', 'Euro')])
        self.assertEqual(m['max_temporal_hops'], 2)
        self.assertEqual(m['currency_switch_edges'], 0)
        self.assertEqual(m['currencies'], 1)
        self.assertFalse(ends)

    def test_reverse_time_cannot_link(self):
        m, _ = self.measure([edge('00:01', 'A', 'B', 'Euro'),
                             edge('00:00', 'B', 'C', 'US Dollar')])
        self.assertEqual(m['max_temporal_hops'], 1)


if __name__ == '__main__':
    unittest.main()
