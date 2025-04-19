import json
import sys

def calculate_new_price(original_price):
    """Calculate new price based on the original price and specified ranges."""
    if original_price is None:
        return None
        
    if original_price < 40000:
        return original_price + 5000
    elif 40000 <= original_price <= 80000:
        return original_price + 10000
    elif 81000 <= original_price <= 99000:
        return original_price + 15000
    elif 100000 <= original_price <= 150000:
        return original_price + 20000
    elif 151000 <= original_price <= 200000:
        return original_price + 30000
    elif 201000 <= original_price <= 450000:
        return original_price + 40000
    elif 451000 <= original_price <= 700000:
        return original_price + 50000
    elif 701000 <= original_price <= 900000:
        return original_price + 60000
    elif 901000 <= original_price <= 999000:
        return original_price + 80000
    elif 1000000 <= original_price <= 1990000:
        return original_price + 100000
    elif 1991000 <= original_price <= 2000000:
        return original_price + 200000
    else:
        # For prices above 2M, add 100k for each additional million
        additional_millions = (original_price - 2000000) // 1000000
        return original_price + (100000 * (additional_millions + 2))

def update_product_prices(input_file='products.json', output_file='products_updated_prices.json'):
    """Update product prices in the JSON file according to the specified logic."""
    try:
        # Read the input file
        print(f"Reading products from {input_file}...", flush=True)
        with open(input_file, 'r', encoding='utf-8') as f:
            products = json.load(f)
            
        print(f"Found {len(products)} products to update", flush=True)
        
        # Update each product
        for index, product in enumerate(products, 1):
            try:
                # Store original price
                original_price = product.get('price')
                if original_price is not None:
                    # Rename current price field to original_price
                    product['original_price'] = original_price
                    # Calculate and add new price
                    product['price'] = calculate_new_price(original_price)
                    print(f"Updated product {index}/{len(products)}: {original_price} -> {product['price']}", flush=True)
                else:
                    print(f"Product {index}/{len(products)} has no price", flush=True)
            except Exception as e:
                print(f"Error updating product {index}: {str(e)}", flush=True)
                continue
        
        # Write updated products to output file
        print(f"\nWriting updated products to {output_file}...", flush=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(products, f, ensure_ascii=False, indent=4)
            
        print(f"\nSuccessfully updated {len(products)} products", flush=True)
        print(f"Original prices are stored in 'original_price' field", flush=True)
        print(f"New prices are stored in 'price' field", flush=True)
        
    except Exception as e:
        print(f"Error updating product prices: {str(e)}", flush=True)
        sys.exit(1)

if __name__ == "__main__":
    # Force immediate output flushing
    sys.stdout.flush()
    update_product_prices() 