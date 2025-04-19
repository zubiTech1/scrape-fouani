from pymongo import MongoClient, UpdateOne, ASCENDING
import ijson
from typing import Set
import os
import numpy as np
from decimal import Decimal
import json
from sentence_transformers import SentenceTransformer

# MongoDB connection settings
MONGO_URI = "mongodb+srv://pascalazubike100:yfiRzC02rO9HDwcl@cluster0.d62sy.mongodb.net/"
DB_NAME = "abc_electronics"
COLLECTION_NAME = "products"

# Model settings
MODEL_NAME = 'sentence-transformers/all-MiniLM-L6-v2'

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

def get_embedding(text, model):
    """Generate embedding for text using Sentence Transformer."""
    try:
        # Convert text to list if it's a string
        if isinstance(text, str):
            text = [text]
        
        print("\nGenerating embedding for text:")
        print(f"Input text: {text[0]}")
        
        # Generate embeddings
        print("Generating embeddings...")
        embeddings = model.encode(text)
        
        # Convert to list for MongoDB storage
        embedding_list = embeddings[0].tolist()
        
        print("Embedding generated successfully!")
        print(f"Embedding length: {len(embedding_list)}")
        print(f"First 5 values: {embedding_list[:5]}")
        print(f"Last 5 values: {embedding_list[-5:]}")
        
        return embedding_list
    except Exception as e:
        print(f"Error generating embedding: {str(e)}")
        print("Returning zero vector as fallback")
        return np.zeros(384).tolist()  # Return zero vector as fallback

def ensure_indexes(collection):
    """Create or update indexes with proper error handling"""
    try:
        # Drop existing indexes except _id
        print("\nDropping existing indexes...")
        collection.drop_indexes()
        
        # Recreate all indexes without unique constraint on SKU
        print("Creating new indexes...")
        try:
            collection.create_index("title")
            print("Created index on 'title'")
        except Exception as e:
            print(f"Error creating index on 'title': {str(e)}")
            
        try:
            collection.create_index("sku")  # Removed unique=True
            print("Created index on 'sku'")
        except Exception as e:
            print(f"Error creating index on 'sku': {str(e)}")
            
        try:
            collection.create_index("main_category")
            print("Created index on 'main_category'")
        except Exception as e:
            print(f"Error creating index on 'main_category': {str(e)}")
            
        try:
            collection.create_index("sub_category")
            print("Created index on 'sub_category'")
        except Exception as e:
            print(f"Error creating index on 'sub_category': {str(e)}")
            
        try:
            collection.create_index("product_type")
            print("Created index on 'product_type'")
        except Exception as e:
            print(f"Error creating index on 'product_type': {str(e)}")
            
        try:
            collection.create_index("availability")
            print("Created index on 'availability'")
        except Exception as e:
            print(f"Error creating index on 'availability': {str(e)}")
            
        try:
            collection.create_index("deleted")
            print("Created index on 'deleted'")
        except Exception as e:
            print(f"Error creating index on 'deleted': {str(e)}")
            
        print("\nIndex creation process completed")
    except Exception as e:
        print(f"Error managing indexes: {str(e)}")
        # Print more detailed error information
        if hasattr(e, 'details'):
            print(f"Error details: {e.details}")
        if hasattr(e, 'code'):
            print(f"Error code: {e.code}")
        if hasattr(e, 'codeName'):
            print(f"Error code name: {e.codeName}")

def upload_products_streaming(input_file='products_updated_prices.json'):
    try:
        # Connect to MongoDB
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
        collection = db[COLLECTION_NAME]
        
        # Initialize Sentence Transformer model
        print("Loading Sentence Transformer model...")
        model = SentenceTransformer(MODEL_NAME)
        print("Model loaded successfully")
        
        print("Connected to MongoDB successfully")

        # Get existing SKUs from database
        existing_skus: Set[str] = {doc['sku'] for doc in collection.find({}, {'sku': 1})}
        print(f"Found {len(existing_skus)} existing products in database")

        # Track metrics
        updates = 0
        inserts = 0
        marked_deleted = 0
        processed_skus: Set[str] = set()

        # Process JSON file in chunks
        batch_size = 1000
        update_batch = []
        insert_batch = []

        with open(input_file, 'rb') as file:
            # Create a parser for the JSON array
            parser = ijson.items(file, 'item')
            
            # Process each product
            for product in parser:
                sku = product.get('sku')
                if not sku:
                    continue

                processed_skus.add(sku)
                
                # Add deleted=false to all current products
                product['deleted'] = False
                
                # Convert Decimal to float for MongoDB compatibility
                if 'price' in product and isinstance(product['price'], Decimal):
                    product['price'] = float(product['price'])
                if 'original_price' in product and isinstance(product['original_price'], Decimal):
                    product['original_price'] = float(product['original_price'])
                
                # Generate embedding for the product
                text_for_embedding = f"{product.get('title', '')}, {product.get('description', '')}"
                product['embedding'] = get_embedding(text_for_embedding, model)
                
                if sku in existing_skus:
                    # Product exists - queue for update
                    update_batch.append(
                        UpdateOne(
                            {'sku': sku},
                            {'$set': product}
                        )
                    )
                else:
                    # New product - queue for insert
                    insert_batch.append(product)

                # Process update batch if it reaches batch size
                if len(update_batch) >= batch_size:
                    if update_batch:
                        collection.bulk_write(update_batch)
                        updates += len(update_batch)
                        print(f"Updated {updates} products so far")
                    update_batch = []

                # Process insert batch if it reaches batch size
                if len(insert_batch) >= batch_size:
                    if insert_batch:
                        collection.insert_many(insert_batch)
                        inserts += len(insert_batch)
                        print(f"Inserted {inserts} new products so far")
                    insert_batch = []

            # Process remaining batches
            if update_batch:
                collection.bulk_write(update_batch)
                updates += len(update_batch)
            
            if insert_batch:
                collection.insert_many(insert_batch)
                inserts += len(insert_batch)

            # Mark products as deleted if they're not in new data
            skus_to_mark_deleted = existing_skus - processed_skus
            if skus_to_mark_deleted:
                result = collection.update_many(
                    {'sku': {'$in': list(skus_to_mark_deleted)}},
                    {'$set': {'deleted': True}}
                )
                marked_deleted = result.modified_count
                print(f"Marked {marked_deleted} products as deleted")

        print(f"\nSync Complete:")
        print(f"Updated: {updates} products")
        print(f"Inserted: {inserts} new products")
        print(f"Marked as deleted: {marked_deleted} products")
        print(f"Total products in database: {collection.count_documents({})}")
        print(f"Active products: {collection.count_documents({'deleted': False})}")
        print(f"Deleted products: {collection.count_documents({'deleted': True})}")

        # Ensure indexes after all operations are complete
        ensure_indexes(collection)

        # Close connection
        client.close()
        print("MongoDB connection closed")

    except Exception as e:
        print(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    upload_products_streaming() 

   