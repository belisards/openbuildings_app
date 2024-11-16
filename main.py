import os
import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.plugins import Fullscreen
import geojson
from shapely.geometry import shape
from shapely.wkt import loads
from pyproj import Transformer
from openbuildings import *
from map_features import *
import pandas as pd
import geopandas as gpd
import json
from io import StringIO

data_dir = './data'
APP_TITLE = "Open Buildings Explorer"
st.set_page_config(page_title=APP_TITLE, layout="wide")

# ------------------------- Setup Functions -------------------------

def setup_app():
    st.title(APP_TITLE)
    st.sidebar.title("Controls")

def initialize_session_state():
    if 'map_data' not in st.session_state:
        st.session_state.map_data = None
    if 'filtered_gob_data' not in st.session_state:
        st.session_state.filtered_gob_data = None
    if 'building_count' not in st.session_state:
        st.session_state.building_count = 0
    if 'avg_confidence' not in st.session_state:
        st.session_state.avg_confidence = 0.0
    if 'imagery_dates' not in st.session_state:
        st.session_state.imagery_dates = []
    if 'selected_feature_name' not in st.session_state:
        st.session_state.selected_feature_name = None
    if 'info_box_visible' not in st.session_state:
        st.session_state.info_box_visible = False
    # lat long
    if 'lat' not in st.session_state:
        st.session_state.lat = 0
    if 'lon' not in st.session_state:
        st.session_state.lon = 0

# ------------------------- Processing Functions -------------------------

def process_uploaded_file(uploaded_file):
    try:
        geojson_data = geojson.load(uploaded_file)
        features = geojson_data['features']
        feature_names = [feature['properties'].get('name', f'Feature {i}') for i, feature in enumerate(features)]
        selected_feature_name = st.sidebar.selectbox("Select a feature to display", feature_names)

        # Check if the selected feature has changed
        if st.session_state.selected_feature_name != selected_feature_name:
            # Reset the session state variables when the feature changes
            st.session_state.filtered_gob_data = None
            st.session_state.building_count = 0
            st.session_state.avg_confidence = 0.0
            st.session_state.imagery_dates = []
            st.session_state.info_box_visible = False

        # Save name of the new feature in the session
        st.session_state.selected_feature_name = selected_feature_name

        selected_feature = next(
            (feature for feature in features if feature['properties'].get('name') == selected_feature_name),
            None
        )

        if selected_feature:
            display_selected_feature(selected_feature)

    except Exception as e:
        st.sidebar.error(f"Error processing GeoJSON file: {str(e)}")
        st.sidebar.error("Please make sure your GeoJSON file is properly formatted.")

# ------------------------- Display Functions -------------------------

def display_selected_feature(selected_feature):
    input_geometry = shape(selected_feature['geometry'])
    wkt_representation = input_geometry.wkt
    s2_tokens = wkt_to_s2(wkt_representation)

    center_lat, center_lon = get_geometry_center(input_geometry)
    # update session state
    st.session_state.lat = center_lat
    st.session_state.lon = center_lon
    #create basemap
    m = create_base_map(center_lat, center_lon)
    folium.GeoJson(selected_feature).add_to(m)
    folium.plugins.Fullscreen(
        position="topright",
        title="Expand me",
        title_cancel="Exit me",
        force_separate_button=True,
    ).add_to(m)

    if st.session_state.filtered_gob_data is not None:
        folium.GeoJson(st.session_state.filtered_gob_data).add_to(m)

    st.session_state.map_data = st_folium(m, width=1200, height=800)

    # Separate the download action from the map
    if len(s2_tokens) > 0 and st.sidebar.button("Fetch GOB Data", key="download_gob_button"):
        download_and_process_gob_data(s2_tokens, input_geometry)

    # Display imagery dates if zoom level is sufficient
    if st.session_state.map_data and 'zoom' in st.session_state.map_data and 'bounds' in st.session_state.map_data:
        zoom_level = st.session_state.map_data['zoom']
        bounds = st.session_state.map_data['bounds']
        if zoom_level >= 12 and bounds:
            transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
            sw_x, sw_y = transformer.transform(bounds['_southWest']['lng'], bounds['_southWest']['lat'])
            ne_x, ne_y = transformer.transform(bounds['_northEast']['lng'], bounds['_northEast']['lat'])

            dates = get_imagery_dates((sw_x, sw_y, ne_x, ne_y), zoom_level)

            if dates:
                st.session_state.imagery_dates = sorted(dates.keys())
        else:
            st.session_state.imagery_dates = f"Current zoom level: {zoom_level} (imagery dates load at level 12+)"
            # st.write()

# ------------------------- Helper Functions -------------------------

def get_geometry_center(geometry):
    if geometry.geom_type == 'Point':
        return geometry.y, geometry.x
    else:
        centroid = geometry.centroid
        return centroid.y, centroid.x

def create_base_map(lat, lon):
    m = folium.Map(location=[lat, lon], zoom_start=12)
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='ArcGIS World Imagery'
    ).add_to(m)
    return m

# ------------------------- Data Download Functions -------------------------

def download_and_process_gob_data(s2_tokens, input_geometry):
    user_warning = st.sidebar.empty()
    os.makedirs(data_dir, exist_ok=True)

    for s2_token in s2_tokens:
        user_warning.info(f"Downloading GOB data for S2 token: {s2_token}. Please wait...")
        try:
            gob_data_compressed = download_data_from_s2_code(s2_token, data_dir)
            # gob_filepath = gob_data_compressed
            
            gob_filepath = uncompress(gob_data_compressed, delete_compressed=False)
            # st.sidebar.info(f"GOB data for {s2_token} downloaded successfully.")
        except Exception as e:
            st.sidebar.error(f"Error downloading GOB data for S2 token: {s2_token}")
            st.sidebar.error(str(e))
            continue

    user_warning.info("Loading GOB data...")
    load_and_filter_gob_data(gob_filepath, input_geometry, user_warning)

# Save the filtered GOB data as CSV in a temporary buffer for download


def load_and_filter_gob_data(gob_filepath, input_geometry, user_warning):
    try:
        header = ['latitude', 'longitude', 'area_in_meters', 'confidence', 'geometry', 'full_plus_code']
        gob_data = pd.read_csv(gob_filepath)
        gob_data.columns = header
        gob_data['geometry'] = gob_data['geometry'].apply(loads)
        gob_gdf = gpd.GeoDataFrame(gob_data, crs='EPSG:4326')

        user_warning.info("Filtering GOB data...")
        filtered_gob_gdf = gob_gdf[gob_gdf.intersects(input_geometry)]
        print(filtered_gob_gdf.info())
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

# ------------------------- Fixed Info Box Function -------------------------

def display_fixed_info_box():
    with st.sidebar.expander("GOB Data Summary", expanded=True):
        st.metric(label="Location", value=st.session_state.selected_feature_name, label_visibility="hidden")
        st.write(f"Lat/long: {st.session_state.lat:.6f}, {st.session_state.lon:.6f}")

        st.metric(label="Total of buildings (% confidence level)", value=f"{st.session_state.building_count} ({st.session_state.avg_confidence:.2f})")
        if st.session_state.imagery_dates:
            st.markdown("**Imagery dates:**")
            if isinstance(st.session_state.imagery_dates, list):
                st.write(", ".join(st.session_state.imagery_dates))
            else:
                st.write(st.session_state.imagery_dates)

            # Add download button for filtered GOB data as GeoJSON
        if st.session_state.filtered_gob_data is not None:
            st.download_button(
                label="Download GeoJSON",
                data=st.session_state.filtered_gob_geojson,
                file_name="filtered_gob_data.geojson",
                mime="application/geo+json"
            )
        # st.metric(label="Average Confidence Level", value=f"{st.session_state.avg_confidence:.2f}")
        
# ------------------------- Main Functions -------------------------

def main():
    setup_app()
    uploaded_file = st.sidebar.file_uploader("Upload a GeoJSON file", type="geojson")
    initialize_session_state()

    if uploaded_file:
        process_uploaded_file(uploaded_file)
        if st.session_state.info_box_visible:
            display_fixed_info_box()

# ------------------------- Run Application -------------------------

if __name__ == "__main__":
    main()
