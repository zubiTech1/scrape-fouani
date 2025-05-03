from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import json
import time
from urllib.parse import urljoin
import sys
import os

# Base URL of the Fouani website
base_url = "https://fouanistore.com"

def setup_driver():
    """Setup and return a Chrome WebDriver instance"""
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    
    # Detect Chrome binary path for Windows
    chrome_binary = None
    if os.name == 'nt':  # Windows
        paths = [
            os.path.expandvars(r'%ProgramFiles%\Google\Chrome\Application\chrome.exe'),
            os.path.expandvars(r'%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe'),
            os.path.expandvars(r'%LocalAppData%\Google\Chrome\Application\chrome.exe')
        ]
        for path in paths:
            if os.path.exists(path):
                chrome_binary = path
                break
    else:  # Linux/Unix
        chrome_binary = os.getenv('CHROME_BINARY_PATH', '/usr/bin/google-chrome')
    
    if chrome_binary:
        chrome_options.binary_location = chrome_binary
    
    # Set up Chrome user data directory with unique session ID
    import uuid
    session_id = str(uuid.uuid4())
    chrome_data_dir = os.path.join(os.path.expanduser('~'), f'chrome-data-{session_id}')
    os.makedirs(chrome_data_dir, exist_ok=True)
    chrome_options.add_argument(f'--user-data-dir={chrome_data_dir}')
    
    # Clean up the user data directory when the driver is done
    import atexit
    import shutil
    def cleanup_user_data_dir():
        try:
            if os.path.exists(chrome_data_dir):
                shutil.rmtree(chrome_data_dir)
        except Exception as e:
            print(f"Error cleaning up user data directory: {e}", flush=True)
    atexit.register(cleanup_user_data_dir)
    
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

def extract_categories(driver):
    """Extract main categories and their subcategories from the dropdown menu."""
    categories = []
    
    try:
        # Click the "All Categories" button to open the dropdown
        all_categories_button = wait_for_element(driver, "button.flex.items-center.gap-2.flex-shrink-0.on-surface-text.label-large.pr-6")
        if all_categories_button:
            print("Found All Categories button, clicking...", flush=True)
            driver.execute_script("arguments[0].click();", all_categories_button)
            time.sleep(2)  # Wait for dropdown to appear
            
            # Wait for the dropdown menu to be visible
            dropdown = wait_for_element(driver, "div.absolute.top-10.left-0.surface-1-background.on-surface-text.flex.transition-all.gap-4.z-30.shadow-2xl.rounded-lg.overflow-hidden")
            if dropdown:
                print("Dropdown menu found, extracting categories...", flush=True)
                
                # Print the dropdown HTML for debugging
                print("\nDropdown HTML:", flush=True)
                print(dropdown.get_attribute('outerHTML'), flush=True)
                
                # Find all main category items
                main_categories = dropdown.find_elements(By.CSS_SELECTOR, "div.flex.items-center.justify-between.cursor-pointer.hover\\:primary-text.label-large")
                print(f"\nFound {len(main_categories)} main categories", flush=True)
                
                for category in main_categories:
                    try:
                        # Get the category name
                        category_name = category.text.strip()
                        if not category_name:
                            print("Skipping empty category name", flush=True)
                            continue
                            
                        print(f"\nProcessing category: {category_name}", flush=True)
                        
                        # Hover over the category to show subcategories
                        print("Hovering over category...", flush=True)
                        driver.execute_script("arguments[0].dispatchEvent(new MouseEvent('mouseover', {bubbles: true}));", category)
                        time.sleep(1)  # Wait for submenu to appear
                        
                        # Find the submenu container
                        submenu = wait_for_element(driver, "div.flex.flex-col.gap-4.w-72.surface-1-background.p-5")
                        if submenu:
                            print("Submenu found, extracting subcategories...", flush=True)
                            # Print submenu HTML for debugging
                            print("\nSubmenu HTML:", flush=True)
                            print(submenu.get_attribute('outerHTML'), flush=True)
                            
                            # Find all subcategory links
                            subcategories = submenu.find_elements(By.TAG_NAME, "a")
                            print(f"Found {len(subcategories)} subcategories", flush=True)
                            
                            subcategory_list = []
                            for subcategory in subcategories:
                                try:
                                    href = subcategory.get_attribute('href')
                                    text = subcategory.text.strip()
                                    print(f"Processing subcategory: {text} ({href})", flush=True)
                                    
                                    if href and text:
                                        # Extract category_id and category_name from href
                                        category_id = None
                                        category_name = None
                                        if 'category_id=' in href and 'category_name=' in href:
                                            category_id = href.split('category_id=')[1].split('&')[0]
                                            category_name = href.split('category_name=')[1].split('&')[0]
                                        
                                        subcategory_info = {
                                            'title': text,
                                            'link': href,
                                            'category_id': category_id,
                                            'category_name': category_name
                                        }
                                        print(f"Adding subcategory: {subcategory_info}", flush=True)
                                        subcategory_list.append(subcategory_info)
                                except Exception as e:
                                    print(f"Error processing subcategory: {str(e)}", flush=True)
                                    continue
                            
                            if subcategory_list:
                                # Add the category with its subcategories
                                category_info = {
                                    'title': category_name,
                                    'subcategories': subcategory_list
                                }
                                print(f"Adding category: {category_info}", flush=True)
                                categories.append(category_info)
                            else:
                                print(f"No subcategories found for {category_name}", flush=True)
                            
                            # Move mouse away to close submenu
                            print("Moving mouse away from category...", flush=True)
                            driver.execute_script("arguments[0].dispatchEvent(new MouseEvent('mouseout', {bubbles: true}));", category)
                            time.sleep(0.5)
                        else:
                            print(f"No submenu found for category: {category_name}", flush=True)
                            
                    except Exception as e:
                        print(f"Error processing category {category_name}: {str(e)}", flush=True)
                        continue
                
                print(f"\nSuccessfully extracted {len(categories)} categories with subcategories", flush=True)
                if categories:
                    print("\nExtracted categories:", flush=True)
                    for cat in categories:
                        print(f"- {cat['title']} ({len(cat['subcategories'])} subcategories)", flush=True)
            else:
                print("Dropdown menu not found", flush=True)
        else:
            print("All Categories button not found", flush=True)
            
    except Exception as e:
        print(f"Error extracting categories: {str(e)}", flush=True)
    
    return categories

def save_categories_to_json(categories, filename='menu_structure.json'):
    """Save categories to JSON file."""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump({'categories': categories}, f, ensure_ascii=False, indent=4)
        print(f"\nSuccessfully saved {len(categories)} categories to {filename}", flush=True)
    except Exception as e:
        print(f"Error saving categories to JSON: {e}", flush=True)

def main():
    # Initialize the driver
    print("\nInitializing Chrome WebDriver...", flush=True)
    driver = setup_driver()
    
    try:
        # Navigate to the main page
        print("\nNavigating to main page...", flush=True)
        driver.get(base_url)
        time.sleep(5)  # Wait for page to load
        
        # Extract categories
        categories = extract_categories(driver)
        
        if categories:
            # Save categories to JSON file
            save_categories_to_json(categories)
        else:
            print("No categories were extracted", flush=True)
            
    except Exception as e:
        print(f"\nError in main process: {str(e)}", flush=True)
    finally:
        print("\nClosing Chrome WebDriver...", flush=True)
        driver.quit()

if __name__ == "__main__":
    # Force immediate output flushing
    sys.stdout.flush()
    main()
