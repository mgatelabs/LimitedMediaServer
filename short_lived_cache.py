import time
import secrets
from collections import OrderedDict
from typing import Optional


class ShortLivedCache:
    def __init__(self, max_size=50):
        self.cache = OrderedDict()
        self.max_size = max_size

    def _purge_oldest(self):
        # Remove the oldest accessed item (first in the OrderedDict)
        if len(self.cache) > self.max_size:
            self.cache.popitem(last=False)

    def add_item(self, file_id: str):
        key = secrets.token_urlsafe(80)
        timestamp = time.time()
        self.cache[key] = {
            "file_id": file_id,
            "last_access": timestamp,
            "created": timestamp
        }
        self._purge_oldest()
        return key

    def get_item(self, key) -> Optional[dict]:
        item = self.cache.get(key)
        if item:
            item["last_access"] = time.time()
            # Reinsert the key to mark it as recently accessed
            self.cache.move_to_end(key)
            return item
        return None

if __name__ == '__main__':

    # Example usage
    cache = ShortLivedCache(max_size=50)

    # Add items to the cache
    key1 = cache.add_item("file1")
    key2 = cache.add_item("file2")

    # Retrieve items
    print("Item for key1:", cache.get_item(key1))
    print("Item for key2:", cache.get_item(key2))

    # Attempt to retrieve a non-existent key
    print("Non-existent key:", cache.get_item("non_existent_key"))

    # Simulate adding more than 50 items
    for i in range(51):
        cache.add_item(f"file_{i}")

    print("Cache size after adding 51 items:", len(cache.cache))
