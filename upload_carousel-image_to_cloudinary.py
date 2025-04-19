import json
import requests
import logging
from datetime import datetime

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('cloudinary_upload.log'),
        logging.StreamHandler()
    ]
)

class CloudinaryUploader:
    def __init__(self, cloud_name, upload_preset):
        self.cloud_name = cloud_name
        self.upload_preset = upload_preset
        self.upload_url = f"https://api.cloudinary.com/v1_1/{cloud_name}/image/upload"
        logging.info(f"Initialized Cloudinary uploader with cloud name: {cloud_name}")
        
    def upload_image(self, image_url):
        """Upload image to Cloudinary using unsigned upload preset"""
        try:
            logging.info(f"Attempting to upload image: {image_url}")
            
            # Prepare the upload data
            data = {
                'file': image_url,
                'upload_preset': self.upload_preset
            }
            
            # Make the upload request
            logging.info("Sending upload request to Cloudinary...")
            response = requests.post(self.upload_url, data=data)
            response.raise_for_status()
            
            # Get the response data
            result = response.json()
            cloudinary_url = result['secure_url']
            logging.info(f"Successfully uploaded image to Cloudinary: {cloudinary_url}")
            return cloudinary_url
            
        except Exception as e:
            logging.error(f"Failed to upload image {image_url}: {str(e)}")
            return None

    def process_carousel_data(self, input_file, output_file):
        try:
            logging.info(f"Reading carousel data from {input_file}")
            # Read the carousel data
            with open(input_file, 'r', encoding='utf-8') as f:
                carousel_data = json.load(f)
            
            logging.info(f"Found {len(carousel_data)} slides to process")
            
            # Process each slide
            successful_uploads = 0
            failed_uploads = 0
            
            for index, slide in enumerate(carousel_data, 1):
                logging.info(f"\nProcessing slide {index}/{len(carousel_data)}")
                
                # Upload desktop image
                if 'desktop' in slide and 'url' in slide['desktop']:
                    logging.info("Processing desktop image...")
                    cloudinary_url = self.upload_image(slide['desktop']['url'])
                    if cloudinary_url:
                        slide['desktop']['cloudinary_url'] = cloudinary_url
                        successful_uploads += 1
                    else:
                        failed_uploads += 1
                
                # Upload mobile image
                if 'mobile' in slide and 'url' in slide['mobile']:
                    logging.info("Processing mobile image...")
                    cloudinary_url = self.upload_image(slide['mobile']['url'])
                    if cloudinary_url:
                        slide['mobile']['cloudinary_url'] = cloudinary_url
                        successful_uploads += 1
                    else:
                        failed_uploads += 1
            
            # Save the updated data
            logging.info(f"\nSaving updated data to {output_file}")
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(carousel_data, f, indent=2, ensure_ascii=False)
                
            logging.info("\nUpload Summary:")
            logging.info(f"Total images processed: {successful_uploads + failed_uploads}")
            logging.info(f"Successfully uploaded: {successful_uploads}")
            logging.info(f"Failed uploads: {failed_uploads}")
            logging.info(f"Updated data saved to: {output_file}")
            
        except Exception as e:
            logging.error(f"Error processing carousel data: {str(e)}")

if __name__ == "__main__":
    # Configuration
    CLOUD_NAME = "dztt3ldiy"
    UPLOAD_PRESET = "ml_default"
    INPUT_FILE = "carousel_data/carousel_images.json"
    OUTPUT_FILE = "carousel_data/carousel_images_with_cloudinary.json"
    
    logging.info("Starting Cloudinary upload process...")
    
    # Create uploader and process images
    uploader = CloudinaryUploader(CLOUD_NAME, UPLOAD_PRESET)
    uploader.process_carousel_data(INPUT_FILE, OUTPUT_FILE)
    
    logging.info("Process completed!") 