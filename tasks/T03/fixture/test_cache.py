import unittest
from cache import LRUCache

class TestCache(unittest.TestCase):
    def test_cache_retrieval(self):
        c = LRUCache(capacity=3)
        c.put("a", 1)
        c.put("b", 2)
        
        # Read 'a'
        val1 = c.get("a")
        self.assertEqual(val1, 1)

        # Read 'a' again - should still be in cache!
        val2 = c.get("a")
        self.assertEqual(val2, 1, "Cache key 'a' was prematurely evicted or removed on first read")

    def test_lru_eviction(self):
        c = LRUCache(capacity=2)
        c.put("x", 10)
        c.put("y", 20)
        _ = c.get("x")  # marks 'x' as recently used
        c.put("z", 30)  # should evict 'y', not 'x'
        self.assertEqual(c.get("x"), 10)
        self.assertIsNone(c.get("y"))
        self.assertEqual(c.get("z"), 30)

if __name__ == "__main__":
    unittest.main()
