import os 
import streamlit as st
import folium
from streamlit_folium import st_folium

import geojson
from shapely.geometry import shape
from shapely.wkt import loads
from pyproj import Transformer

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
                input_geometry = shape(selected_feature['geometry'])
           
                # Convert geometry to WKT format
                wkt_representation = input_geometry.wkt
                          
                s2_tokens = wkt_to_s2(wkt_representation)

                if input_geometry.geom_type == 'Point':
                    center_lat, center_lon = input_geometry.y, input_geometry.x
                else:
                    centroid = input_geometry.centroid
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
            
                ################################ DOWNLOAD GOB DATA ################################
                if len(s2_tokens) > 0:
                    # st.sidebar.button("Download GOB Data")
                    if st.sidebar.button("Download GOB Data",key="download_gob_button"):

                        # create a placeholder for warning msgs to the user
                        user_warning = st.sidebar.empty()
                        # create dir if don't exist
                        os.makedirs(data_dir, exist_ok=True)

                        # empty the folder
                        for file in os.listdir(data_dir):
                            os.remove(os.path.join(data_dir, file))
                        # download data
                        for s2_token in s2_tokens:
                            # st.sidebar.info(f"Downloading GOB data for S2 token: {s2_token}")
                            user_warning.info(f"Downloading GOB data for S2 token: {s2_token}")
                            try:
                                gob_data_compressed = download_data_from_s2_code(s2_token,data_dir)
                                gob_filepath = uncompress(gob_data_compressed, delete_compressed=False)
                                st.sidebar.success(f"GOB data for {s2_token} downloaded successfully.")
                            except Exception as e:
                                st.sidebar.error(f"Error downloading GOB data for S2 token: {s2_token}")
                                st.sidebar.error(str(e))
                                continue
                        

                        ##################################### load gob data
                        # st.sidebar.info("Loading GOB data...")
                        user_warning.info("Loading GOB data...")
                        print(gob_filepath)

                        # col names taken from the official gob notebook
                        header = ['latitude', 'longitude', 'area_in_meters', 'confidence', 'geometry','full_plus_code']
                        try: 
                            # create a gpd.GeoDataFrame()
                            # gob_data = gpd.read_file(gob_filepath)
                            
                            gob_data = pd.read_csv(gob_filepath)
                            # add header
                            gob_data.columns = header
                            gob_data['geometry'] = gob_data['geometry'].apply(loads) # convert WKT to shapely geometry
                            gob_gdf = gpd.GeoDataFrame(gob_data, crs='EPSG:4326') # transform to gpd.GeoDataFrame
                                 # st.sidebar.success("GOB data loaded successfully.")
                            user_warning.success("GOB data loaded successfully.")

                        except Exception as e:
                            st.sidebar.error(f"Error loading GOB data: {str(e)}")
                            st.sidebar.error("Please make sure the downloaded file is a valid CSV file.")
                            return

                   
                        # filter and plot gob data
                        user_warning.info("Filtering GOB data...")
                        # filter gob_gdf and the geojson input selected by the user
                        filtered_gob_gdf = gob_gdf[gob_gdf.intersects(input_geometry)]
                        user_warning.warning(f"Filtered {len(filtered_gob_gdf)} GOB data points.")
################################################################################# 
                        # plot in the map the filtered_gob_df



        except Exception as e:
            st.sidebar.error(f"Error processing GeoJSON file: {str(e)}")
            st.sidebar.error("Please make sure your GeoJSON file is properly formatted.")

if __name__ == "__main__":
    main()