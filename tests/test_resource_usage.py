"""Tests for resource_usage() helper (issue #27)."""

import unittest
import sdev


class TestResourceUsage(unittest.TestCase):
    def test_returns_dict_with_expected_keys(self):
        usage = sdev.resource_usage()
        self.assertIn("cpu_percent", usage)
        self.assertIn("memory_bytes", usage)
        self.assertIn("memory_mb", usage)

    def test_memory_is_positive(self):
        usage = sdev.resource_usage()
        self.assertGreater(usage["memory_bytes"], 0)
        self.assertGreater(usage["memory_mb"], 0)

    def test_cpu_percent_is_reasonable(self):
        usage = sdev.resource_usage()
        # Should not be absurdly high for a short-running test
        self.assertLess(usage["cpu_percent"], 100)

    def test_consistent_values(self):
        # Two calls close together should return similar memory usage
        u1 = sdev.resource_usage()
        u2 = sdev.resource_usage()
        self.assertEqual(u1["memory_bytes"], u2["memory_bytes"])


if __name__ == "__main__":
    unittest.main()
