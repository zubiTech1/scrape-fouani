import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs, urlencode
import json
import time
import re
from pymongo import MongoClient, UpdateOne, ASCENDING
import ijson
from typing import Set
from collections import defaultdict

def scrape_and_process():
    # Move imports inside the function to prevent automatic execution
    try:
        # Only import when function is called
        from category import parse_menu, save_menu_to_json
        from scrape import visit_links
        from deduplicate import deduplicate_products
        from upload_products_streaming import upload_products_streaming

        print("Step 1: Parsing menu structure...")
        menu_structure = parse_menu('https://fouanistore.com/public/ng/en')
        save_menu_to_json(menu_structure)
        print("Menu structure saved successfully\n")

        print("Step 2: Scraping products...")
        categories = menu_structure.get("main_menu", [])
        all_products = visit_links(categories)
        print(f"Total products scraped: {len(all_products)}\n")

        print("Step 3: Deduplicating products...")
        deduplicate_products('products.json', 'products_dedup.json')
        print("Deduplication complete\n")

        print("Step 4: Uploading products to MongoDB...")
        upload_products_streaming('products_dedup.json')
        print("Upload complete\n")

        print("All operations completed successfully!")
        return True

    except Exception as e:
        print(f"An error occurred during execution: {str(e)}")
        return False

# This function is just a wrapper now
def main():
    return scrape_and_process()

if __name__ == "__main__":
    main() 