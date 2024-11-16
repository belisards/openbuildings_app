import os
import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.plugins import Fullscreen
import geojson
from shapely.geometry import shape
from pyproj import Transformer

from google_openbuildings import *
from map_features import *
from file_manager import *

data_dir = './data'
APP_TITLE = "Open Buildings Explorer"
st.set_page_config(page_title=APP_TITLE, layout="wide")

def setup_app():
    st.title(APP_TITLE)
    st.sidebar.title("Controls")

def initialize_session_state():
    for key, default in {
        'map_data': None,
        'filtered_gob_data': None,
        'building_count': 0,
        'avg_confidence': 0.0,
        'imagery_dates': [],
        'selected_feature_name': None,
        'info_box_visible': False,
        'lat': 0,
        'lon': 0,
        'progress_message': ""
    }.items():
        if key not in st.session_state:
            st.session_state[key] = default

def process_uploaded_file(uploaded_file):
    try:
        geojson_data = geojson.load(uploaded_file)
        features = geojson_data['features']
        feature_names = [feature['properties'].get('name', f'Feature {i}') for i, feature in enumerate(features)]
        selected_feature_name = st.sidebar.selectbox("Select a feature to display", feature_names)

        if st.session_state.selected_feature_name != selected_feature_name:
            st.session_state.filtered_gob_data = None
            st.session_state.building_count = 0
            st.session_state.avg_confidence = 0.0
            st.session_state.imagery_dates = []
            st.session_state.info_box_visible = False

        st.session_state.selected_feature_name = selected_feature_name
        selected_feature = next((feature for feature in features if feature['properties'].get('name') == selected_feature_name), None)

        if selected_feature:
            display_selected_feature(selected_feature)

    except Exception as e:
        st.sidebar.error(f"Error processing GeoJSON file: {str(e)}")
        st.sidebar.error("Please make sure your GeoJSON file is properly formatted.")

def display_selected_feature(selected_feature):
    input_geometry = shape(selected_feature['geometry'])
    wkt_representation = input_geometry.wkt
    s2_tokens = wkt_to_s2(wkt_representation)

    center_lat, center_lon = get_geometry_center(input_geometry)
    st.session_state.lat = center_lat
    st.session_state.lon = center_lon
    
    m = create_base_map(center_lat, center_lon)
    folium.GeoJson(selected_feature).add_to(m)
    Fullscreen(position="topright", title="Expand me", title_cancel="Exit me", force_separate_button=True).add_to(m)

    if st.session_state.filtered_gob_data is not None:
        folium.GeoJson(st.session_state.filtered_gob_data).add_to(m)

    st.session_state.map_data = st_folium(m, width=1200, height=800, returned_objects=[])

    st.session_state.s2_tokens = s2_tokens
    st.session_state.input_geometry = input_geometry

def get_geometry_center(geometry):
    if geometry.geom_type == 'Point':
        return geometry.y, geometry.x
    else:
        centroid = geometry.centroid
        return centroid.y, centroid.x

def create_base_map(lat, lon):
    m = folium.Map(location=[lat, lon], zoom_start=12)
    folium.TileLayer(
        name='ArcGIS World Imagery',
        control=True,
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='ArcGIS World Imagery'
    ).add_to(m)
    return m

def download_and_process_gob_data(s2_tokens, input_geometry):
    user_warning = st.sidebar.empty()  
    os.makedirs(data_dir, exist_ok=True)

    for s2_token in s2_tokens:
        st.session_state.progress_message = f"Downloading GOB data for S2 token: {s2_token}. Please wait..."
        user_warning.info(st.session_state.progress_message)

        try:
            gob_data_compressed = download_data_from_s2_code(s2_token, data_dir)
            gob_filepath = uncompress(gob_data_compressed, delete_compressed=False)
            # st.session_state.progress_message = f"GOB data for {s2_token} downloaded successfully."
            user_warning.info(st.session_state.progress_message)
        except Exception as e:
            st.session_state.progress_message = f"Error downloading GOB data for S2 token: {s2_token}"
            user_warning.error(st.session_state.progress_message)
            user_warning.error(str(e))
            continue

    user_warning.info(st.session_state.progress_message)
    load_and_filter_gob_data(gob_filepath, input_geometry, user_warning)

def display_fixed_info_box():
    with st.sidebar.expander("GOB Data Summary", expanded=True):
        st.metric(label="Location", value=st.session_state.selected_feature_name, label_visibility="hidden")
        st.write(f"Lat/long: {st.session_state.lat:.6f}, {st.session_state.lon:.6f}")
        st.metric(label="Total of buildings (% confidence level)", value=f"{st.session_state.building_count} ({st.session_state.avg_confidence:.2f})")
        if st.session_state.imagery_dates:
            st.markdown("**Imagery dates:**")
            st.write(", ".join(st.session_state.imagery_dates) if isinstance(st.session_state.imagery_dates, list) else st.session_state.imagery_dates)
        if st.session_state.filtered_gob_data is not None:
            st.download_button(
                label="Download GeoJSON",
                data=st.session_state.filtered_gob_geojson,
                file_name="filtered_gob_data.geojson",
                mime="application/geo+json"
            )

def main():
    setup_app()
    uploaded_file = st.sidebar.file_uploader("Upload a GeoJSON file", type="geojson")
    initialize_session_state()

    if uploaded_file:
        process_uploaded_file(uploaded_file)
        if st.session_state.info_box_visible:
            display_fixed_info_box()

        if st.session_state.s2_tokens and st.sidebar.button("Fetch GOB Data", key="download_gob_button"):
            remove_folder_contents(data_dir)
            download_and_process_gob_data(st.session_state.s2_tokens, st.session_state.input_geometry)

    if st.session_state.progress_message:
        st.sidebar.info(st.session_state.progress_message)

if __name__ == "__main__":
    main()