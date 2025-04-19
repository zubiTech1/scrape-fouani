import requests
from bs4 import BeautifulSoup
import json
import os
from urllib.parse import urljoin, urlparse, unquote, parse_qs
import time
import logging
from datetime import datetime
from selenium import webdriver
import signal
import sys

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('carousel_scraper.log'),
        logging.StreamHandler()
    ]
)

class WebDriverManager:
    def __init__(self):
        self.driver = None
    
    def init_driver(self):
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument('--headless')  # Optional: run in headless mode
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        self.driver = webdriver.Chrome(options=chrome_options)
        return self.driver
    
    def cleanup(self):
        """Safely quit the webdriver"""
        try:
            if self.driver:
                self.driver.quit()
                self.driver = None
        except Exception as e:
            logging.error(f"Error cleaning up webdriver: {str(e)}")

class CarouselScraper:
    def __init__(self, base_url):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.carousel_data = []
        self.output_dir = 'carousel_data'
        self.output_file = os.path.join(self.output_dir, 'carousel_images.json')
        os.makedirs(self.output_dir, exist_ok=True)
        self.driver_manager = WebDriverManager()

    def extract_image_url(self, img_tag):
        """Extract the original image URL from Next.js optimized image srcset"""
        try:
            if not img_tag:
                return None

            # Get the srcset attribute
            srcset = img_tag.get('srcset', '')
            if not srcset:
                return None

            # Find the highest resolution URL in srcset
            urls = []
            for src in srcset.split(','):
                url = src.strip().split(' ')[0]
                if url.startswith('/_next/image'):
                    # Extract the original URL from the Next.js image URL
                    params = urlparse(url).query
                    for param in params.split('&'):
                        if param.startswith('url='):
                            original_url = unquote(param[4:])  # Decode the URL
                            urls.append(original_url)
                            break

            # Return the highest resolution URL
            return urls[-1] if urls else None
        except Exception as e:
            logging.error(f"Error extracting image URL: {str(e)}")
            return None

    def extract_link_params(self, link):
        """Extract all parameters from the link without assumptions"""
        try:
            if not link:
                return {}
                
            # Parse the URL and get all query parameters
            parsed = urlparse(link)
            params = parse_qs(parsed.query)
            
            # Convert all parameter values from lists to single values
            # parse_qs returns values as lists, we want single values
            return {
                key: values[0] if values else ''
                for key, values in params.items()
            }
            
        except Exception as e:
            logging.error(f"Error parsing link parameters: {str(e)}")
            return {}

    def scrape_carousel(self):
        try:
            self.driver = self.driver_manager.init_driver()
            logging.info(f"Starting to scrape carousel from {self.base_url}")
            response = self.session.get(self.base_url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # First find the main carousel container
            carousel = soup.find('div', class_='swiper-wrapper')
            if not carousel:
                logging.warning("Carousel wrapper not found")
                return
            
            # Then find slides only within this carousel
            carousel_slides = carousel.find_all('div', class_='swiper-slide')
            
            if not carousel_slides:
                logging.warning("No carousel slides found within carousel wrapper")
                return

            for slide in carousel_slides:
                try:
                    # Get both image containers from within this slide
                    desktop_img = slide.select_one('a.hidden.lg\\:block img')
                    mobile_img = slide.select_one('a.block.lg\\:hidden img')
                    
                    if not desktop_img or not mobile_img:
                        logging.warning("Missing images in carousel slide")
                        continue
                    
                    # Get the link and extract whatever parameters it has
                    raw_link = slide.find('a').get('href', '')
                    link_params = self.extract_link_params(raw_link)
                    
                    slide_data = {
                        'desktop': {
                            'url': self.extract_image_url(desktop_img),
                            'alt': desktop_img.get('alt', ''),
                            'title': desktop_img.get('title', ''),
                            'aspect_ratio': '3:1'
                        },
                        'mobile': {
                            'url': self.extract_image_url(mobile_img),
                            'alt': mobile_img.get('alt', ''),
                            'title': mobile_img.get('title', ''),
                            'aspect_ratio': '9:16'
                        },
                        'params': link_params,  # Store whatever parameters we find
                        'raw_link': raw_link,   # Also store the original link for reference
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    if slide_data['desktop']['url'] and slide_data['mobile']['url']:
                        self.carousel_data.append(slide_data)
                        logging.info("Successfully scraped desktop and mobile images from carousel slide")
                    else:
                        logging.warning("Failed to extract image URLs from carousel slide")
                    
                except Exception as e:
                    logging.error(f"Error processing carousel slide: {str(e)}")
                    continue

            self.save_data()
            logging.info("Carousel scraping completed successfully")

        except requests.RequestException as e:
            logging.error(f"Request failed: {str(e)}")
        except Exception as e:
            logging.error(f"Unexpected error: {str(e)}")
        finally:
            self.driver_manager.cleanup()

    def save_data(self):
        try:
            with open(self.output_file, 'w', encoding='utf-8') as f:
                json.dump(self.carousel_data, f, indent=2, ensure_ascii=False)
            
            logging.info(f"Data saved to {self.output_file}")
            
        except Exception as e:
            logging.error(f"Error saving data: {str(e)}")

if __name__ == "__main__":
    def signal_handler(signum, frame):
        logging.info("Received shutdown signal, cleaning up...")
        if 'scraper' in locals():
            scraper.driver_manager.cleanup()
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        base_url = "https://fouanistore.com"
        scraper = CarouselScraper(base_url)
        scraper.scrape_carousel()
    except Exception as e:
        logging.error(f"Error in main: {str(e)}")
    finally:
        if 'scraper' in locals():
            scraper.driver_manager.cleanup()