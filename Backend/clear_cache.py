from cache_manager import clear_cache

if __name__ == "__main__":
    print("Clearing semantic cache...")
    try:
        clear_cache()
        print("Cache cleared successfully.")
    except Exception as e:
        print(f"Error clearing cache: {e}")
