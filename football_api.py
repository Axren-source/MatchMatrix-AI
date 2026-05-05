import os
import json

# Ensure these are at the top of your file
CACHE_DIR = "cache"
os.makedirs(CACHE_DIR, exist_ok=True)

def load_cache(filename):
    """Load cached data from the cache directory"""
    path = os.path.join(CACHE_DIR, filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return None
    return None

def save_cache(filename, data):
    """Save data to a JSON file in the cache directory"""
    path = os.path.join(CACHE_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)