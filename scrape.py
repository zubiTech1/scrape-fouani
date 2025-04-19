from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup
import json
import time
import re
from urllib.parse import urljoin
import sys

# Base URL of the Fouani website
base_url = "https://fouanistore.com"

def setup_driver():
    """Set up and return a configured Chrome WebDriver instance."""
    chrome_options = Options()
    chrome_options.add_argument('--start-maximized')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # Add additional options to avoid detection
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    
    driver = webdriver.Chrome(options=chrome_options)
    driver.set_window_size(1920, 1080)
    
    # Add custom JavaScript to avoid detection
    driver.execute_cdp_cmd('Network.setUserAgentOverride', {
        "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })
    
    return driver

def clean_text(text):
    """Clean and normalize text content."""
    return text.strip() if text else None

def wait_for_element(driver, selector, timeout=20, by=By.CSS_SELECTOR):
    """Wait for an element to be present and return it."""
    try:
        wait = WebDriverWait(driver, timeout)
        element = wait.until(EC.presence_of_element_located((by, selector)))
        return element
    except TimeoutException:
        print(f"Timeout waiting for element: {selector}", flush=True)
        return None
    except Exception as e:
        print(f"Error waiting for element {selector}: {str(e)}", flush=True)
        return None

def get_product_links(driver, url):
    product_links = []
    product_stock_status = {}  # Dictionary to store product URLs and their stock status
    try:
        print(f"\nVisiting category: {url}", flush=True)
        driver.get(url)
        time.sleep(5)  # Wait for initial load
        
        # First try to find the main product container
        main_container = wait_for_element(driver, "div.col-span-9", timeout=10)
        if main_container:
            print("Main product container found. Looking for product links...", flush=True)
            
            # Try different selectors for product divs
            selectors = [
                "div.RSingleProduct_mainDiv__42N9L",
                "div[data-testid='product-card']",
                ".product-card",
                ".product-item",
                ".product",
                "article"
            ]
            
            product_found = False
            for selector in selectors:
                try:
                    print(f"Trying selector: {selector}", flush=True)
                    
                    # Handle pagination
                    while True:
                        # Get all product links from current page
                        print("Extracting product links from current page...", flush=True)
                        
                        # Find all product divs
                        product_divs = driver.find_elements(By.CSS_SELECTOR, selector)
                        
                        for product_div in product_divs:
                            try:
                                # Get the product link
                                link_elem = product_div.find_element(By.CSS_SELECTOR, "a.RSingleProduct_imageLink__t72ga")
                                if not link_elem:
                                    link_elem = product_div.find_element(By.TAG_NAME, "a")
                                
                                href = link_elem.get_attribute('href')
                                
                                # Check for out of stock indicator
                                is_out_of_stock = False
                                try:
                                    stock_span = product_div.find_element(By.CSS_SELECTOR, "span.label-small.RSingleProduct_ribbon__KFgvr")
                                    if stock_span and "Out of Stock" in stock_span.text:
                                        is_out_of_stock = True
                                except:
                                    # If the span is not found, the product is in stock
                                    is_out_of_stock = False
                                
                                if href and href not in product_links:
                                    product_links.append(href)
                                    product_stock_status[href] = is_out_of_stock
                                    print(f"Found product link: {href} (Stock status: {'Out of Stock' if is_out_of_stock else 'In Stock'})", flush=True)
                            except Exception as e:
                                print(f"Error processing product div: {str(e)}", flush=True)
                                continue
                        
                        if product_divs:
                            product_found = True
                            print(f"Found {len(product_links)} unique product links with selector '{selector}'", flush=True)
                            
                            # Check for next page
                            try:
                                # Wait for pagination to be present
                                pagination = wait_for_element(driver, "div.flex.items-center.justify-center.lg\\:justify-end.gap-2.my-4", timeout=5)
                                if not pagination:
                                    print("No pagination found", flush=True)
                                    break
                                
                                # Find the current page number
                                current_page = None
                                page_links = pagination.find_elements(By.TAG_NAME, "a")
                                for page_link in page_links:
                                    if "bg-[var(--md-sys-color-primary)]" in page_link.get_attribute("class"):
                                        current_page = int(page_link.text)
                                        break
                                
                                if current_page:
                                    # Look for the next page link
                                    next_page = None
                                    for page_link in page_links:
                                        try:
                                            page_num = int(page_link.text)
                                            if page_num == current_page + 1:
                                                next_page = page_link
                                                break
                                        except ValueError:
                                            continue
                                    
                                    if next_page:
                                        print(f"Moving to page {current_page + 1}", flush=True)
                                        try:
                                            # Scroll the pagination into view
                                            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", pagination)
                                            time.sleep(2)  # Wait for scroll to complete
                                            
                                            # Try to click using JavaScript
                                            driver.execute_script("arguments[0].click();", next_page)
                                            time.sleep(3)  # Wait for page load
                                        except Exception as click_error:
                                            print(f"Error clicking next page: {str(click_error)}", flush=True)
                                            # Try alternative method - get the href and navigate directly
                                            try:
                                                next_page_url = next_page.get_attribute('href')
                                                if next_page_url:
                                                    print(f"Navigating directly to next page URL: {next_page_url}", flush=True)
                                                    driver.get(next_page_url)
                                                    time.sleep(3)
                                            except Exception as nav_error:
                                                print(f"Error navigating to next page: {str(nav_error)}", flush=True)
                                                break
                                    else:
                                        print("No more pages to process", flush=True)
                                        break
                                else:
                                    print("Could not determine current page", flush=True)
                                    break
                                    
                            except Exception as e:
                                print(f"No pagination found or error: {str(e)}", flush=True)
                                break
                        else:
                            break
                    
                    if product_found:
                        break
                        
                except Exception as e:
                    print(f"Error with selector '{selector}': {str(e)}", flush=True)
                    continue
            
            if not product_found:
                print("No product elements found with any selector", flush=True)
        else:
            print("Main product container not found", flush=True)
            
    except Exception as e:
        print(f"Error getting product links: {str(e)}", flush=True)
    
    return product_links, product_stock_status

def extract_product_details(driver, url, is_out_of_stock=False):
    """Extract product details using Selenium."""
    print(f"\nExtracting details for: {url}", flush=True)
    try:
        driver.get(url)
        time.sleep(5)  # Wait for dynamic content
        
        # Print page source for debugging
        print("Page title:", driver.title, flush=True)
        
        product_detail = {}
        product_detail['url'] = url
        product_detail['stock_status'] = "Out of Stock" if is_out_of_stock else "In Stock"
        
        # Extract title
        try:
            title_elem = wait_for_element(driver, "h1.headline-large")
            if title_elem:
                product_detail['title'] = clean_text(title_elem.text)
                print(f"Found title: {product_detail['title']}", flush=True)
        except Exception as e:
            print(f"Error extracting title: {str(e)}", flush=True)
            product_detail['title'] = None

        # Extract manufacturer
        try:
            # Find the manufacturer span inside the div with class "body-large undefined"
            manufacturer_elem = driver.find_element(By.CSS_SELECTOR, "div.body-large.undefined span")
            if manufacturer_elem:
                # Extract the manufacturer name by removing "By " and "." from the text
                manufacturer_text = clean_text(manufacturer_elem.text)
                if manufacturer_text:
                    # Remove "By " prefix and "." suffix if they exist
                    manufacturer_text = manufacturer_text.replace("By ", "").replace(".", "").strip()
                    product_detail['manufacturer'] = manufacturer_text
                    print(f"Found manufacturer: {product_detail['manufacturer']}", flush=True)
        except Exception as e:
            print(f"Error extracting manufacturer: {str(e)}", flush=True)
            product_detail['manufacturer'] = None

        # Extract SKU
        try:
            sku_elem = driver.find_element(By.XPATH, "//div[contains(text(), 'SKU:')]")
            if sku_elem:
                sku_text = clean_text(sku_elem.text)
                product_detail['sku'] = sku_text.replace('SKU:', '').strip()
                print(f"Found SKU: {product_detail['sku']}", flush=True)
        except Exception as e:
            print(f"Error extracting SKU: {str(e)}", flush=True)
            product_detail['sku'] = None

        # Extract price
        try:
            price_elem = wait_for_element(driver, "h4.title-large")
            if price_elem:
                price_text = clean_text(price_elem.text)
                # Remove currency symbol and convert to float
                price_value = float(re.sub(r'[^\d.]', '', price_text))
                product_detail['price'] = price_value
                print(f"Found price: {price_value}", flush=True)
            else:
                product_detail['price'] = None
                print("Price element not found", flush=True)
        except Exception as e:
            print(f"Error extracting price: {str(e)}", flush=True)
            product_detail['price'] = None

        # Extract images
        product_detail['images'] = []
        try:
            # Get all image elements
            image_elements = driver.find_elements(By.CSS_SELECTOR, "img.RProduct_swiperImage__y1ZsF")
            for img in image_elements:
                src = img.get_attribute('src')
                if src and src not in product_detail['images']:
                    product_detail['images'].append(src)
            print(f"Found {len(product_detail['images'])} images", flush=True)
        except Exception as e:
            print(f"Error extracting images: {str(e)}", flush=True)

        # Extract description and related PDFs
        try:
            desc_elem = wait_for_element(driver, "#desc")
            if desc_elem:
                # Get the HTML content
                desc_html = desc_elem.get_attribute('innerHTML')
                
                # Split the content at "Related PDFs:"
                parts = desc_html.split("<h4>Related PDFs:</h4>")
                
                # Extract description (everything before "Related PDFs:")
                description_text = parts[0].replace("<h4>Description:</h4>", "").strip()
                product_detail['description'] = clean_text(description_text)
                print("Found description", flush=True)
                
                # Extract related PDFs if they exist
                if len(parts) > 1:
                    pdfs_html = parts[1]
                    # Use BeautifulSoup to parse the PDF links
                    soup = BeautifulSoup(pdfs_html, 'html.parser')
                    pdf_links = soup.find_all('a')
                    
                    product_detail['related_pdfs'] = []
                    for link in pdf_links:
                        pdf_info = {
                            'title': clean_text(link.text),
                            'url': link.get('href')
                        }
                        if pdf_info['url'] and pdf_info['title']:
                            product_detail['related_pdfs'].append(pdf_info)
                    
                    print(f"Found {len(product_detail['related_pdfs'])} related PDFs", flush=True)
                else:
                    product_detail['related_pdfs'] = []
                    print("No related PDFs found", flush=True)
        except Exception as e:
            print(f"Error extracting description and PDFs: {str(e)}", flush=True)
            product_detail['description'] = None
            product_detail['related_pdfs'] = []

        # Extract attributes/specifications
        specs = {}
        try:
            # Find all attribute rows
            attr_rows = driver.find_elements(By.CSS_SELECTOR, "div.RProduct_divAtt__Z4Pc0")
            for row in attr_rows:
                try:
                    title = row.find_element(By.CSS_SELECTOR, "span.RProduct_spanTitle__CZ1Ab").text
                    value = row.find_element(By.CSS_SELECTOR, "span.RProduct_spanValue__J8CAs").text
                    if title and value:
                        specs[clean_text(title)] = clean_text(value)
                except:
                    continue
            print(f"Found {len(specs)} specifications", flush=True)
        except Exception as e:
            print(f"Error extracting specifications: {str(e)}", flush=True)
            
        product_detail['specifications'] = specs

        print(f"Successfully extracted details for: {product_detail.get('title', 'Unknown Product')}", flush=True)
        return product_detail

    except Exception as e:
        print(f"Error extracting details from {url}: {str(e)}", flush=True)
        return None

def save_products_to_json(products, filename='products.json'):
    """Save products to JSON file."""
    try:
        # Try to read existing products
        existing_products = []
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                existing_products = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        
        # Append new products
        all_products = existing_products + products
        
        # Write back to file
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(all_products, f, ensure_ascii=False, indent=4)
            
        print(f"\nSuccessfully saved {len(products)} new products. Total products: {len(all_products)}", flush=True)
        
    except Exception as e:
        print(f"Error saving products to JSON: {e}", flush=True)

def main():
    # Load menu structure
    with open('menu_structure.json', 'r', encoding='utf-8') as f:
        menu_data = json.load(f)
    
    # Initialize the driver
    print("\nInitializing Chrome WebDriver...", flush=True)
    driver = setup_driver()
    
    try:
        all_products = []
        total_processed = 0
        
        # Process each category's subcategories
        for category in menu_data['categories']:
            print(f"\nProcessing category: {category['title']}", flush=True)
            
            # Process each subcategory except "All"
            for subcategory in category['subcategories']:
                if subcategory['title'].lower() == 'all':
                    print(f"Skipping 'All' subcategory in {category['title']}", flush=True)
                    continue
                    
                print(f"\nProcessing subcategory: {subcategory['title']}", flush=True)
                subcategory_url = subcategory['link']
                
                # Get product links from subcategory
                product_links, product_stock_status = get_product_links(driver, subcategory_url)
                
                if not product_links:
                    print(f"No products found in subcategory: {subcategory['title']}", flush=True)
                    continue
                
                # Extract details for each product
                for product_index, product_url in enumerate(product_links, 1):
                    print(f"\nProcessing product {product_index}/{len(product_links)} in subcategory {subcategory['title']}", flush=True)
                    is_out_of_stock = product_stock_status.get(product_url, False)
                    product_details = extract_product_details(driver, product_url, is_out_of_stock)
                    
                    if product_details:
                        # Add category and subcategory information
                        product_details['category'] = category['title']
                        product_details['subcategory'] = subcategory['title']
                        product_details['subcategory_id'] = subcategory['category_id']
                        all_products.append(product_details)
                        total_processed += 1
                    
                    # Save products periodically
                    if len(all_products) % 5 == 0:  # Save every 5 products
                        save_products_to_json(all_products)
                        all_products = []  # Clear the list after saving
                        print(f"\nTotal products processed so far: {total_processed}", flush=True)
        
        # Save any remaining products
        if all_products:
            save_products_to_json(all_products)
            
        print(f"\nScraping completed! Total products processed: {total_processed}", flush=True)
            
    except Exception as e:
        print(f"\nError in main process: {str(e)}", flush=True)
    finally:
        print("\nClosing Chrome WebDriver...", flush=True)
        driver.quit()

if __name__ == "__main__":
    # Force immediate output flushing
    sys.stdout.flush()
    main()