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

    try:
        # Attempt to open and read the file for the provided S2 code.
        with tf.io.gfile.GFile(
            os.path.join(BUILDING_DOWNLOAD_PATH, f'{s2_code}_buildings.csv.gz'), 'rb'
        ) as gf:
            # Create a progress bar
            progress_bar = st.sidebar.progress(0)
            total_rows = 0

            # Process data in chunks and save directly to the output file in data folder
            with open(output_path, 'wb') as f:
                csv_chunks = pd.read_csv(gf, chunksize=1_000, dtype=object, compression='gzip', header=None)
                for chunk in csv_chunks:
                    chunk.to_csv(f, mode='ab', index=False, header=False, compression='gzip')
                    total_rows += len(chunk)
                    progress_bar.progress(total_rows / 100_000)  # Assuming 10 million total rows

            progress_bar.empty()
            return output_path

    except tf.errors.NotFoundError:
        return None

def uncompress(gzipped_file: str, delete_compressed: bool = True) -> Optional[str]:
    """Uncompresses a gzipped CSV file and returns the path to the uncompressed file.

    Args:
        gzipped_file (str): Path to the gzipped CSV file.

    Returns:
        Optional[str]: Path to the uncompressed CSV file if successful, None otherwise.
    """

    try:
        with tf.io.gfile.GFile(gzipped_file, 'rb') as gf:
            with open(gzipped_file.replace('.gz', ''), 'wb') as f:
                shutil.copyfileobj(gf, f)

        if delete_compressed:
            os.remove(gzipped_file)

        return gzipped_file.replace('.gz', '')

    except tf.errors.NotFoundError:
        return None
