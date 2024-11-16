from typing import List, Optional
import geopandas as gpd
import shapely
import pandas as pd
import s2geometry as s2
import streamlit as st
import os
import fsspec
from shapely.wkt import loads
from io import StringIO
import json



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

# def download_data_from_s2_code(s2_code: str, data_dir: str) -> Optional[str]:
#     """Downloads and filters data based on S2 code for building polygons.

#     Args:
#         s2_code (str): S2 code to download building polygons for.

#     Returns:
#         Optional[str]: Path to gzipped CSV file if successful, None otherwise.
#     """

#     output_path = os.path.join(data_dir, f'{s2_code}_buildings.csv.gz')
#     # print(output_path)

#     # skip if file exists and return the path
#     if os.path.exists(output_path):
#         print(f"File already exists: {output_path}")
#         return output_path
    
#     print(f"Downloading data to: {output_path}")
#     try:
#         # Attempt to open and read the file for the provided S2 code.
#         with tf.io.gfile.GFile(
#             os.path.join(BUILDING_DOWNLOAD_PATH, f'{s2_code}_buildings.csv.gz'), 'rb'
#         ) as gf:
#             # Create a progress bar
#             progress_bar = st.sidebar.progress(0)
#             total_rows = 0
#             total_expected_rows = 10_000_000  # Adjust this as per your expected total rows

#             # Process data in chunks and save directly to the output file in data folder
#             with open(output_path, 'wb') as f:
#                 csv_chunks = pd.read_csv(gf, chunksize=1_000, dtype=object, compression='gzip', header=None)
#                 for chunk in csv_chunks:
#                     chunk.to_csv(f, mode='ab', index=False, header=False, compression='gzip')
#                     total_rows += len(chunk)
#                     progress_bar.progress(min(total_rows / total_expected_rows, 1.0))
            
#             progress_bar.empty()
#         return output_path


#     except tf.errors.NotFoundError:
#         return None


    
def download_data_from_s2_code(s2_code: str, data_dir: str) -> Optional[str]:
    """
    Downloads data from Google Cloud Storage based on S2 code for building polygons.

    Args:
        s2_code (str): S2 code to download building polygons for.
        data_dir (str): Directory to save the downloaded data.

    Returns:
        Optional[str]: Path to gzipped CSV file if successful, None otherwise.
    """
    # Define output path
    output_path = os.path.join(data_dir, f'{s2_code}_buildings.csv.gz')

    # Check if the file already exists
    if os.path.exists(output_path):
        st.write(f"File already exists at: {output_path}")
        return output_path

    try:
        # Construct the GCS path
        gcs_path = os.path.join(BUILDING_DOWNLOAD_PATH, f'{s2_code}_buildings.csv.gz')

        # Open GCS file and get its total size
        with fsspec.open(gcs_path, 'rb', anon=True) as source:
            source.seek(0, 2)  # Seek to the end of the file to get its size
            total_size = source.tell()
            source.seek(0)  # Seek back to the start
            
            status_text = st.sidebar.empty()
            status_text.warning(f"Starting download of {total_size / 1e6:.2f} MB...")

            bytes_read = 0

            # Read the file in chunks while updating the status text
            with open(output_path, 'wb') as dest:
                while True:
                    chunk = source.read(8192)  # Read in chunks
                    if not chunk:
                        break
                    dest.write(chunk)
                    bytes_read += len(chunk)

                    # Update status text (reduce frequency of updates to improve performance)
                    if bytes_read % (8192 * 10) == 0 or bytes_read == total_size:
                        progress = min(bytes_read / total_size, 1.0)
                        # transform bytes to MB
                        status_text.warning(f"Downloaded {bytes_read / 1e6:.1f} MB of {total_size / 1e6:.1f} MB ({progress * 100:.0f}%)")
                        # status_text.warning(f"Downloaded {bytes_read} of {total_size} bytes ({progress * 100:.0f}%)")

        # Display final status and remove the status text
        status_text.empty()
        

        return output_path

    except Exception as e:
        st.error(f"Error during download: {str(e)}")
        # Clean up any partial file if it exists
        if os.path.exists(output_path):
            os.remove(output_path)
            st.write(f"Partial file removed: {output_path}")
        return None


def load_and_filter_gob_data(gob_filepath, input_geometry):
    user_warning = st.sidebar.empty()
    try:
        header = ['latitude', 'longitude', 'area_in_meters', 'confidence', 'geometry', 'full_plus_code']
        gob_data = pd.read_csv(gob_filepath)
        gob_data.columns = header
        gob_data['geometry'] = gob_data['geometry'].apply(loads)
        gob_gdf = gpd.GeoDataFrame(gob_data, crs='EPSG:4326')

        user_warning.info("Filtering GOB data...")
        filtered_gob_gdf = gob_gdf[gob_gdf.intersects(input_geometry)]
        # print(filtered_gob_gdf.info())
        user_warning.empty()

        avg_confidence = filtered_gob_gdf['confidence'].mean()

        st.session_state.building_count = len(filtered_gob_gdf)
        st.session_state.avg_confidence = avg_confidence
        st.session_state.filtered_gob_data = filtered_gob_gdf.to_crs('EPSG:4326').to_json()
        st.session_state.info_box_visible = True  # Show info box after data is processed

        # Prepare GeoJSON buffer for download
        geojson_buffer = StringIO()
        json.dump(json.loads(st.session_state.filtered_gob_data), geojson_buffer)
        geojson_buffer.seek(0)
        st.session_state.filtered_gob_geojson = geojson_buffer.getvalue()

        st.rerun()
    except Exception as e:
        user_warning.error(f"Error loading GOB data: {str(e)}")