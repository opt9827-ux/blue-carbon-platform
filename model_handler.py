# File: model_handler.py
import ee
import numpy as np
import tensorflow as tf
from tensorflow.keras.models import load_model
import matplotlib.pyplot as plt
import io
import base64
import geemap
from datetime import datetime, timedelta
# Removed web3 and blockchain imports

# --- GEE Authentication ---
try:
    import json
    import os
    if os.path.exists('service_account_key.json'):
        with open('service_account_key.json') as f:
            info = json.load(f)
            creds = ee.ServiceAccountCredentials(info['client_email'], 'service_account_key.json')
            ee.Initialize(creds, project=info.get('project_id', 'blue-carbon-472606'))
            print("GEE authentication successful.")
    else:
        print("❌ Warning: service_account_key.json not found.")
except Exception as e:
    print(f"Error authenticating with GEE: {e}")

# --- Load Model ---
try:
    BANDS = ['B2','B3','B4','B8','B11','NDVI','SAVI','BSI']
    model = load_model('soc_model.h5')
    print("✅ Pre-trained model loaded successfully.")
except Exception as e:
    print(f"❌ Error loading model: {e}")
    model = None

# --- GEE Helper Functions ---
def mask_s2_clouds(image):
    qa = image.select('QA60')
    cloud_bit_mask, cirrus_bit_mask = 1 << 10, 1 << 11
    mask = qa.bitwiseAnd(cloud_bit_mask).eq(0).And(qa.bitwiseAnd(cirrus_bit_mask).eq(0))
    return image.updateMask(mask).divide(10000)

def add_indices(image):
    ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI')
    savi = image.expression('((NIR - RED) / (NIR + RED + 0.5)) * 1.5', {'NIR': image.select('B8'), 'RED': image.select('B4')}).rename('SAVI')
    bsi = image.expression('((SWIR + RED) - (NIR + BLUE)) / ((SWIR + RED) + (NIR + BLUE))', {'SWIR': image.select('B11'), 'RED': image.select('B4'), 'NIR': image.select('B8'), 'BLUE': image.select('B2')}).rename('BSI')
    return image.addBands([ndvi, savi, bsi])

# --- Helper function for single-date prediction ---
def _predict_for_date(roi, date_str):
    if not model: raise RuntimeError("Model is not loaded.")
    center_date = datetime.strptime(date_str, '%Y-%m-%d')
    start_period = (center_date - timedelta(days=15)).strftime('%Y-%m-%d')
    end_period = (center_date + timedelta(days=15)).strftime('%Y-%m-%d')
    collection = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').filterBounds(roi).filterDate(start_period, end_period).filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
    collection_size = collection.size().getInfo()
    print(f"Found {collection_size} images for the period around {date_str}.")
    if collection_size == 0: raise ValueError(f"No satellite images with <20% cloud cover found for {date_str}.")
    image = collection.map(mask_s2_clouds).map(add_indices).median().clip(roi).select(BANDS)
    arr = geemap.ee_to_numpy(image, region=roi, scale=30)
    arr = np.nan_to_num(arr)
    patch_size = 32
    patches = []
    if arr.shape[0] < patch_size or arr.shape[1] < patch_size: return np.zeros((1,1)), 0
    for i in range(0, arr.shape[0] - patch_size + 1, patch_size):
        for j in range(0, arr.shape[1] - patch_size + 1, patch_size):
            patches.append(arr[i:i+patch_size, j:j+patch_size, :])
    if not patches: return np.zeros((arr.shape[0], arr.shape[1])), 0
    predictions = model.predict(np.array(patches))
    soc_map = np.zeros((arr.shape[0], arr.shape[1]))
    k = 0
    for i in range(0, arr.shape[0] - patch_size + 1, patch_size):
        for j in range(0, arr.shape[1] - patch_size + 1, patch_size):
            soc_map[i:i+patch_size, j:j+patch_size] = predictions[k]
            k += 1
    total_carbon_tons = 0
    if np.any(soc_map > 0):
        average_soc = np.mean(soc_map[soc_map > 0])
        area_sq_meters = roi.area().getInfo()
        SOIL_BULK_DENSITY_KG_PER_M3, SOIL_DEPTH_M = 1300, 0.3
        total_soil_mass_kg = (area_sq_meters * SOIL_DEPTH_M) * SOIL_BULK_DENSITY_KG_PER_M3
        total_carbon_kg = total_soil_mass_kg * average_soc
        total_carbon_tons = total_carbon_kg / 1000
    return soc_map, total_carbon_tons

# --- Main function called by the server ---
def generate_offset_report(coords, start_date, end_date, farmer_wallet_address):
    roi = ee.Geometry.Rectangle(coords)
    TOKEN_PRICE, TONS_PER_MEGATON = 5, 1_000_000
    start_map, start_tons = _predict_for_date(roi, start_date)
    end_map, end_tons = _predict_for_date(roi, end_date)
    carbon_offset_tons = end_tons - start_tons
    offset_value = carbon_offset_tons * TOKEN_PRICE
    start_megatons = start_tons / TONS_PER_MEGATON
    end_megatons = end_tons / TONS_PER_MEGATON
    carbon_offset_megatons = carbon_offset_tons / TONS_PER_MEGATON

    # --- Blockchain Interaction Block (REMOVED) ---
    transaction_hash = None # Kept as placeholder for API return value clarity

    # --- Image Generation Block ---
    center_date = datetime.strptime(end_date, '%Y-%m-%d')
    start_period = (center_date - timedelta(days=15)).strftime('%Y-%m-%d')
    end_period = (center_date + timedelta(days=15)).strftime('%Y-%m-%d')
    image_for_display = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').filterBounds(roi).filterDate(start_period, end_period).filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)).map(mask_s2_clouds).median().clip(roi).select(['B4', 'B3', 'B2'])
    rgb_arr = geemap.ee_to_numpy(image_for_display, region=roi, scale=30)
    rgb_arr = np.nan_to_num(rgb_arr)
    def get_base64_img(arr, title, cmap=None, vmin=None, vmax=None):
        buf = io.BytesIO()
        # Set a fixed size that fits well in the UI containers
        fig = plt.figure(figsize=(10, 8))
        if cmap:
            plt.imshow(arr, cmap=cmap, vmin=vmin, vmax=vmax)
            plt.colorbar(label='SOC Value')
        else:
            plt.imshow(arr)
        
        plt.title(title, fontsize=14, fontweight='bold', pad=20)
        plt.axis('off')
        # Use bbox_inches='tight' to ensure everything fits
        plt.savefig(buf, format='png', bbox_inches='tight', dpi=100, transparent=True)
        plt.close(fig)
        return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('utf-8')}"

    # Prepare individual images
    min_val = min(np.min(start_map[start_map > 0]), np.min(end_map[end_map > 0])) if np.any(start_map > 0) and np.any(end_map > 0) else 0
    max_val = max(np.max(start_map), np.max(end_map))

    satellite_img = get_base64_img(rgb_arr, f'Satellite View ({end_date})')
    baseline_img = get_base64_img(start_map, f'Baseline SOC ({start_date})', cmap='YlGn', vmin=min_val, vmax=max_val)
    latest_img = get_base64_img(end_map, f'Latest SOC ({end_date})', cmap='YlGn', vmin=min_val, vmax=max_val)

    return {
        "satellite_image": satellite_img,
        "baseline_image": baseline_img,
        "latest_image": latest_img,
        # Keep old key for backward compatibility if any single-image view remains
        "comparison_map_image": satellite_img, 
        "start_megatons": start_megatons,
        "end_megatons": end_megatons,
        "carbon_offset_megatons": carbon_offset_megatons,
        "offset_value": offset_value,
        "transaction_hash": transaction_hash 
    }