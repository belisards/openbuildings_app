# Relevant changes:
# - Only display the number of buildings after GOB data is loaded.
# - Move the display of imagery dates below the map instead of in the sidebar.

import os
import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.plugins import Fullscreen
import geojson
from shapely.geometry import shape
from pyproj import Transformer
from io import BytesIO
import json
from google_openbuildings import *
from map_features import *
from file_manager import *

data_dir = './data/'
APP_TITLE = "Open Buildings Explorer"
st.set_page_config(page_title=APP_TITLE, layout="wide")

def setup_app():
    # st.title(APP_TITLE)
    st.sidebar.title("Open Buildings Explorer")

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
        'progress_message': "",
        'input_geometry': None,
        'bounds': None,
        'zoom': 0,
        's2_tokens': [],
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

    st.session_state.map_data = st_folium(m, width=1200, height=800)#, returned_objects=[])
    # print(st.session_state.map_data)

    st.session_state.s2_tokens = s2_tokens
    st.session_state.input_geometry = input_geometry

    # Update info box visibility whenever we display a feature
    # st.session_state.info_box_visible = True

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

    for s2_token in s2_tokens:
        st.session_state.progress_message = f"Downloading GOB data for S2 token: {s2_token}. Please wait..."
        user_warning.info(st.session_state.progress_message)

        try:
            gob_data_compressed = download_data_from_s2_code(s2_token, data_dir)
            gob_filepath = uncompress(gob_data_compressed, delete_compressed=False)
        except Exception as e:
            st.error(f"Detailed error: {str(e)}")
            print(e)
            raise

    user_warning.info("Filtering GOB data...")
    st.session_state.filtered_gob_data = load_and_filter_gob_data(gob_filepath, input_geometry)
    st.session_state.building_count = len(st.session_state.filtered_gob_data['features'])
    user_warning.empty()
    st.session_state.info_box_visible = True

def display_fixed_info_box():
    with st.sidebar.expander("GOB Data Summary", expanded=True):
        st.metric(label="Location", value=st.session_state.selected_feature_name, label_visibility="hidden")
        st.write(f"Lat/long: {st.session_state.lat:.6f}, {st.session_state.lon:.6f}")
        st.metric(label="Total of buildings (% confidence level)", 
                 value=f"{st.session_state.building_count} ({st.session_state.avg_confidence:.2f})")
        
        if st.session_state.filtered_gob_data is not None:
            geojson_str = json.dumps(st.session_state.filtered_gob_data, indent=2)
            geojson_bytes = BytesIO(geojson_str.encode("utf-8"))
            st.download_button(
                label="Download GeoJSON",
                data=geojson_bytes,
                file_name="filtered_gob_data.geojson",
                mime="application/geo+json"
            )


    # Display imagery dates if zoom level is sufficient


def main():
    setup_app()
    uploaded_file = st.sidebar.file_uploader("Upload a GeoJSON file", type="geojson")
    initialize_session_state()

    if uploaded_file:
        process_uploaded_file(uploaded_file)
        # get imagery dates
        bounds = st.session_state.map_data['bounds']
        # print(bounds)
        zoom_level = st.session_state.map_data['zoom']
        if zoom_level >= 12 and bounds:
            transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
            sw_x, sw_y = transformer.transform(bounds['_southWest']['lng'], bounds['_southWest']['lat'])
            ne_x, ne_y = transformer.transform(bounds['_northEast']['lng'], bounds['_northEast']['lat'])
            # print(sw_x, sw_y, ne_x, ne_y)

            dates = get_imagery_dates((sw_x, sw_y, ne_x, ne_y), zoom_level)
            if dates:
                # change to str
                dates = ", ".join(dates)
                print(dates)
                st.session_state.imagery_dates = dates
                # write
                st.sidebar.write(f"Imagery dates: {dates}")
        else:
            st.session_state.imagery_dates = f"Curent zoom level: {zoom_level} - Imagery dates are only available at zoom level 12 or higher."
            # write
        #st.sidebar.write(st.session_state.imagery_dates)

        if st.sidebar.button("Fetch GOB Data", key="download_gob_button"):
            download_and_process_gob_data(st.session_state.s2_tokens, st.session_state.input_geometry)
            
        if st.session_state.info_box_visible:
            display_fixed_info_box()
    
    # Display imagery dates below the map
    

if __name__ == "__main__":
    main()