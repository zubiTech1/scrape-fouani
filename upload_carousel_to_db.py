from pymongo import MongoClient, UpdateOne
import json
import logging
from datetime import datetime

# MongoDB connection settings
MONGO_URI = "mongodb+srv://pascalazubike100:yfiRzC02rO9HDwcl@cluster0.d62sy.mongodb.net/"
DB_NAME = "abc_electronics"
COLLECTION_NAME = "carousel"

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('carousel_upload.log'),
        logging.StreamHandler()
    ]
)

class CarouselUploader:
    def __init__(self):
        self.client = MongoClient(MONGO_URI)
        self.db = self.client[DB_NAME]
        self.collection = self.db[COLLECTION_NAME]
        logging.info("Connected to MongoDB successfully")

    def ensure_indexes(self):
        """Create or update necessary indexes"""
        try:
            logging.info("\nDropping existing indexes...")
            self.collection.drop_indexes()
            
            logging.info("Creating new indexes...")
            # Index on timestamp for sorting
            self.collection.create_index("timestamp")
            logging.info("Created index on 'timestamp'")
            
            # Index on category_id for filtering
            self.collection.create_index("params.category_id")
            logging.info("Created index on 'params.category_id'")
            
            logging.info("Index creation completed")
        except Exception as e:
            logging.error(f"Error managing indexes: {str(e)}")

    def upload_carousel_data(self, input_file='carousel_data/carousel_images_with_cloudinary.json'):
        try:
            logging.info(f"Reading carousel data from {input_file}")
            
            # Read the carousel data
            with open(input_file, 'r', encoding='utf-8') as f:
                carousel_data = json.load(f)
            
            logging.info(f"Found {len(carousel_data)} slides to process")
            
            # Get existing slides from database for comparison
            existing_slides = list(self.collection.find({}, {'_id': 0}))
            logging.info(f"Found {len(existing_slides)} existing slides in database")
            
            # Track metrics
            updates = 0
            inserts = 0
            
            # Process each slide
            update_batch = []
            insert_batch = []
            
            for slide in carousel_data:
                # Add last_updated timestamp
                slide['last_updated'] = datetime.now().isoformat()
                
                # Check if slide exists (based on image URLs)
                existing_slide = next(
                    (
                        s for s in existing_slides 
                        if (s['desktop']['url'] == slide['desktop']['url'] and 
                            s['mobile']['url'] == slide['mobile']['url'])
                    ), 
                    None
                )
                
                if existing_slide:
                    # Slide exists - queue for update
                    update_batch.append(
                        UpdateOne(
                            {
                                'desktop.url': slide['desktop']['url'],
                                'mobile.url': slide['mobile']['url']
                            },
                            {'$set': slide}
                        )
                    )
                else:
                    # New slide - queue for insert
                    insert_batch.append(slide)
                
                # Process batches
                if len(update_batch) >= 100:  # Smaller batch size for carousel
                    if update_batch:
                        self.collection.bulk_write(update_batch)
                        updates += len(update_batch)
                        logging.info(f"Updated {updates} slides so far")
                    update_batch = []
                
                if len(insert_batch) >= 100:
                    if insert_batch:
                        self.collection.insert_many(insert_batch)
                        inserts += len(insert_batch)
                        logging.info(f"Inserted {inserts} new slides so far")
                    insert_batch = []
            
            # Process remaining batches
            if update_batch:
                self.collection.bulk_write(update_batch)
                updates += len(update_batch)
            
            if insert_batch:
                self.collection.insert_many(insert_batch)
                inserts += len(insert_batch)
            
            logging.info("\nUpload Summary:")
            logging.info(f"Updated: {updates} slides")
            logging.info(f"Inserted: {inserts} new slides")
            logging.info(f"Total slides in database: {self.collection.count_documents({})}")
            
            # Ensure indexes after upload
            self.ensure_indexes()
            
        except Exception as e:
            logging.error(f"An error occurred: {str(e)}")
        finally:
            # Close connection
            self.client.close()
            logging.info("MongoDB connection closed")

if __name__ == "__main__":
    uploader = CarouselUploader()
    uploader.upload_carousel_data() 