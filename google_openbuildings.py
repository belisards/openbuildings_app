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

from st_files_connection import FilesConnection

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

########
import os
import streamlit as st
from streamlit.runtime.uploaded_file_manager import UploadedFile
from typing import Optional
from st_files_connection import FilesConnection

def download_data_from_s2_code(s2_code: str, data_dir: str) -> Optional[str]:
    """
    Downloads data from Google Cloud Storage based on S2 code for building polygons.
    Args:
        s2_code (str): S2 code to download building polygons for.
        data_dir (str): Directory to save the downloaded data.
    Returns:
        Optional[str]: Path to gzipped CSV file if successful, None otherwise.
    """
    if not isinstance(s2_code, str) or not isinstance(data_dir, str):
        st.error("Both s2_code and data_dir must be strings")
        return None

    # Define output path
    output_path = os.path.join(data_dir, f'{s2_code}_buildings.csv.gz')
    
    # Ensure data directory exists
    os.makedirs(data_dir, exist_ok=True)
    
    # st.sidebar.write(f"Downloading data to: {output_path}")
    
    # Check if the file already exists
    if os.path.exists(output_path):
        print(f"File already exists: {output_path}")
        return output_path

    try:
        # Construct the GCS path
        conn = st.connection('gcs', type=FilesConnection)
        gcs_path = os.path.join(BUILDING_DOWNLOAD_PATH, f'{s2_code}_buildings.csv.gz')
        # st.sidebar.write(f"Downloading data from: {gcs_path}")
        
        # Open GCS file and get its total size
        with conn.open(gcs_path, 'rb') as f:
            if not hasattr(f, 'size'):
                st.warning("File size information not available")
                total_size = 0
            else:
                total_size = f.size
                # st.sidebar.write(f"Total file size: {total_size} bytes")
            
            # Initialize progress bar
            status_text = st.sidebar.empty()
            progress_bar = st.sidebar.progress(0)
            
            # Download the file in chunks
            with open(output_path, 'wb') as out:
                bytes_downloaded = 0
                chunk_size = 8192  # 8KB chunks
                
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                        
                    out.write(chunk)
                    bytes_downloaded += len(chunk)
                    
                    if total_size > 0:
                        progress = min(1.0, bytes_downloaded / total_size)
                        progress_bar.progress(progress)
                        # status_text.write(f"Downloaded {bytes_downloaded} bytes out of {total_size} bytes")
                        # also show as megabytes
                        status_text.write(f"Downloaded {bytes_downloaded/1e6:.2f} MB out of {total_size/1e6:.2f} MB")
                    else:
                        status_text.write(f"Downloaded {bytes_downloaded} bytes")

        # Clear status elements
        status_text.empty()
        progress_bar.empty()
        
        # Verify the downloaded file exists and is not empty
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            st.success(f"Download completed: {output_path}")
            return str(output_path)
        else:
            st.error("Downloaded file is empty or does not exist")
            return None
            
    except Exception as e:
        st.error(f"Error during download: {str(e)}")
        # Clean up any partial file if it exists
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
                st.write(f"Partial file removed: {output_path}")
            except Exception as cleanup_error:
                st.error(f"Error cleaning up partial file: {str(cleanup_error)}")
        return None

def load_and_filter_gob_data(gob_filepath, input_geometry):
    #user_warning = st.sidebar.empty()
    try:
        header = ['latitude', 'longitude', 'area_in_meters', 'confidence', 'geometry', 'full_plus_code']
        gob_data = pd.read_csv(gob_filepath)
        gob_data.columns = header
        gob_data['geometry'] = gob_data['geometry'].apply(loads)
        gob_gdf = gpd.GeoDataFrame(gob_data, crs='EPSG:4326')

        
        filtered_gob_gdf = gob_gdf[gob_gdf.intersects(input_geometry)]
        # print(filtered_gob_gdf.info())
        # user_warning.empty()

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
        print(e)