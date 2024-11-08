import streamlit as st
import folium
from streamlit_folium import st_folium
import geojson
from shapely.geometry import shape

from datetime import datetime
from pyproj import Transformer
import tensorflow as tf
import s2geometry as s2


from openbuildings import *
from map_features import *

data_dir = './data'

    
##############################################################################

def main():

    st.title("Open Buildings Explorer")
    
    # Create sidebar
    st.sidebar.title("Controls")
    
    # Move file uploader to sidebar
    uploaded_file = st.sidebar.file_uploader("Upload a GeoJSON file", type="geojson")
    
    if uploaded_file is not None:
        try:
            geojson_data = geojson.load(uploaded_file)
            features = geojson_data['features']
            feature_names = [feature['properties'].get('name', f'Feature {i}') for i, feature in enumerate(features)]
            
            # Move feature selection to sidebar
            selected_feature_name = st.sidebar.selectbox("Select a feature to display", feature_names)
            selected_feature = next(
                (feature for feature in features if feature['properties'].get('name') == selected_feature_name), 
                None
            )
            
            if selected_feature:
                geometry = shape(selected_feature['geometry'])
           
                # Convert geometry to WKT format
                wkt_representation = geometry.wkt
                          
                s2_tokens = wkt_to_s2(wkt_representation)
                

                if len(s2_tokens) > 0:
                    # st.sidebar.button("Download GOB Data")
                    if st.sidebar.button("Download GOB Data",key="download_gob_button"):
                        os.makedirs(data_dir, exist_ok=True)
                        for s2_token in s2_tokens:
                            gob_data_compressed = download_data_from_s2_code(s2_token,data_dir)
                            gob_data = uncompress(gob_data_compressed)
                            print(gob_data)

                if geometry.geom_type == 'Point':
                    center_lat, center_lon = geometry.y, geometry.x
                else:
                    centroid = geometry.centroid
                    center_lat, center_lon = centroid.y, centroid.x
                
                # Main area: Display map
                m = folium.Map(location=[center_lat, center_lon], zoom_start=12)
                
                folium.TileLayer(
                    tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
                    attr='ArcGIS World Imagery'
                ).add_to(m)
                
                folium.GeoJson(geojson_data).add_to(m)
                
                map_data = st_folium(m, width=700, height=500)
                
                if map_data and 'zoom' in map_data and 'bounds' in map_data:
                    zoom_level = map_data['zoom']
                    bounds = map_data['bounds']
                    
                    # Move zoom level info to sidebar
                    st.write(f"Current zoom level: {zoom_level} (imagery dates load at level 12+)")
                    
                    if zoom_level >= 12 and bounds:
                        transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
                        sw_x, sw_y = transformer.transform(bounds['_southWest']['lng'], bounds['_southWest']['lat'])
                        ne_x, ne_y = transformer.transform(bounds['_northEast']['lng'], bounds['_northEast']['lat'])
                        
                        dates = get_imagery_dates((sw_x, sw_y, ne_x, ne_y), zoom_level)
                        
                        if dates:
                            # Display dates in sidebar
                            date_list = sorted(dates.keys())
                            st.markdown("---")  # Add a separator
                            st.write("**Imagery dates:**")
                            st.write(", ".join(date_list))
                            
        except Exception as e:
            st.sidebar.error(f"Error processing GeoJSON file: {str(e)}")
            st.sidebar.error("Please make sure your GeoJSON file is properly formatted.")

if __name__ == "__main__":
    main()