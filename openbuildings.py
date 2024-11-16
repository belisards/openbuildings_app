from typing import List
import geopandas as gpd
import shapely
import os
import pandas as pd
import s2geometry as s2
import tensorflow as tf
import shutil
from typing import Optional
import streamlit as st
import gzip
os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'

BUILDING_DOWNLOAD_PATH = 'gs://open-buildings-data/v3/polygons_s2_level_6_gzip_no_header'

def wkt_to_s2(your_own_wkt_polygon: str) -> List[str]:
    """Takes a WKT polygon, converts to a geopandas GeoDataFrame, and returns S2 covering tokens."""

    # Convert WKT polygon to GeoDataFrame
    region_df = gpd.GeoDataFrame(
        geometry=gpd.GeoSeries.from_wkt([your_own_wkt_polygon]),
        crs='EPSG:4326'
    )
    
    # Validate the geometry type
    if not isinstance(region_df.iloc[0].geometry, (shapely.geometry.polygon.Polygon, shapely.geometry.multipolygon.MultiPolygon)):
        raise ValueError("`your_own_wkt_polygon` must be a POLYGON or MULTIPOLYGON.")
    
    # Get bounds of the region
    region_bounds = region_df.iloc[0].geometry.bounds
    
    # Create S2LatLngRect for covering
    s2_lat_lng_rect = s2.S2LatLngRect_FromPointPair(
        s2.S2LatLng_FromDegrees(region_bounds[1], region_bounds[0]),
        s2.S2LatLng_FromDegrees(region_bounds[3], region_bounds[2])
    )
    
    # Cover the region using S2RegionCoverer
    coverer = s2.S2RegionCoverer()
    coverer.set_fixed_level(6)
    coverer.set_max_cells(1000000)
    
    # Return the covering tokens
    return [cell.ToToken() for cell in coverer.GetCovering(s2_lat_lng_rect)]

def download_data_from_s2_code(s2_code: str, data_dir: str) -> Optional[str]:
    """Downloads and filters data based on S2 code for building polygons.

    Args:
        s2_code (str): S2 code to download building polygons for.

    Returns:
        Optional[str]: Path to gzipped CSV file if successful, None otherwise.
    """

    output_path = os.path.join(data_dir, f'{s2_code}_buildings.csv.gz')
    # print(output_path)

    # skip if file exists and return the path
    if os.path.exists(output_path):
        print(f"File already exists: {output_path}")
        return output_path
    
    print(f"Downloading data to: {output_path}")
    try:
        # Attempt to open and read the file for the provided S2 code.
        with tf.io.gfile.GFile(
            os.path.join(BUILDING_DOWNLOAD_PATH, f'{s2_code}_buildings.csv.gz'), 'rb'
        ) as gf:
            # Create a progress bar
            progress_bar = st.sidebar.progress(0)
            total_rows = 0
            total_expected_rows = 10_000_000  # Adjust this as per your expected total rows

            # Process data in chunks and save directly to the output file in data folder
            with open(output_path, 'wb') as f:
                csv_chunks = pd.read_csv(gf, chunksize=1_000, dtype=object, compression='gzip', header=None)
                for chunk in csv_chunks:
                    chunk.to_csv(f, mode='ab', index=False, header=False, compression='gzip')
                    total_rows += len(chunk)
                    progress_bar.progress(min(total_rows / total_expected_rows, 1.0))
            
            progress_bar.empty()
        return output_path


    except tf.errors.NotFoundError:
        return None
# import os
# from typing import Optional
# from google.cloud import storage
# import os
# from typing import Optional
# import fsspec
# import gcsfs

# def download_data_from_s2_code(s2_code: str, data_dir: str) -> Optional[str]:
#     """Downloads data from Google Cloud Storage based on S2 code for building polygons.
    
#     Args:
#         s2_code (str): S2 code to download building polygons for.
#         data_dir (str): Directory to save the downloaded data.
    
#     Returns:
#         Optional[str]: Path to gzipped CSV file if successful, None otherwise.
#     """
#     output_path = os.path.join(data_dir, f'{s2_code}_buildings.csv.gz')
    
#     # Skip if file exists and return the path
#     if os.path.exists(output_path):
#         print(f"File already exists: {output_path}")
#         return output_path
    
#     try:
#         # Construct the GCS path
#         gcs_path = os.path.join(BUILDING_DOWNLOAD_PATH, f'{s2_code}_buildings.csv.gz')
        
#         # Create a progress bar
#         progress_bar = st.sidebar.progress(0)
        
#         # Open and read the file using fsspec
#         with fsspec.open(gcs_path, 'rb', anon=True) as source:
#             with open(output_path, 'wb') as dest:
#                 # Get total size
#                 source.seek(0, 2)  # Seek to end
#                 total_size = source.tell()
#                 source.seek(0)  # Back to start
                
#                 # Copy in chunks with progress
#                 chunk_size = 8192
#                 bytes_read = 0
                
#                 while True:
#                     chunk = source.read(chunk_size)
#                     if not chunk:
#                         break
                    
#                     dest.write(chunk)
#                     bytes_read += len(chunk)
                    
#                     # Update progress
#                     if total_size:
#                         progress = min(bytes_read / total_size, 1.0)
#                         progress_bar.progress(progress)
        
#         progress_bar.empty()
#         return output_path
        
#     except Exception as e:
#         print(f"Error downloading file: {e}")
#         if os.path.exists(output_path):
#             os.remove(output_path)
#         return None
    
def uncompress(gzipped_file: str, delete_compressed: bool = True) -> Optional[str]:
    """Uncompresses a gzipped CSV file and returns the path to the uncompressed file.

    Args:
        gzipped_file (str): Path to the gzipped CSV file.
        delete_compressed (bool): Whether to delete the compressed file after uncompressing.

    Returns:
        Optional[str]: Path to the uncompressed CSV file if successful, None otherwise.
    """

    try:
        with gzip.open(gzipped_file, 'rb') as gf:
            with open(gzipped_file.replace('.gz', ''), 'wb') as f:
                shutil.copyfileobj(gf, f)

        if delete_compressed:
            os.remove(gzipped_file)

        return gzipped_file.replace('.gz', '')

    except FileNotFoundError:
        return None