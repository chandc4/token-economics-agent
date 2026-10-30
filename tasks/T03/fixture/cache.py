import time

class LRUCache:
    def __init__(self, capacity: int = 5):
        self.capacity = capacity
        self.store = {}
        self.access_times = {}

    def put(self, key: str, value: any):
        if len(self.store) >= self.capacity and key not in self.store:
            oldest = min(self.access_times, key=self.access_times.get)
            del self.store[oldest]
            del self.access_times[oldest]
        self.store[key] = value
        self.access_times[key] = time.time()

    def get(self, key: str):
        if key not in self.store:
            return None
        # Misleading / buggy implementation: accidentally pops key on read!
        val = self.store.pop(key)
        del self.access_times[key]
        return val
