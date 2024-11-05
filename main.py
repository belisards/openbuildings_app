import streamlit as st
import folium
from streamlit_folium import st_folium
import geojson
from shapely.geometry import shape
import requests
import json
from datetime import datetime
from pyproj import Transformer

def convert_esri_feature_to_geojson(esri_feature):
    """
    Convert ESRI Feature to GeoJSON format
    """
    try:
        geojson_feature = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": []
            },
            "properties": esri_feature.get('attributes', {})
        }
        
        if 'geometry' in esri_feature and 'rings' in esri_feature['geometry']:
            geojson_feature['geometry']['coordinates'] = esri_feature['geometry']['rings']
            
        return geojson_feature
    except Exception as e:
        st.error(f"Error converting ESRI feature to GeoJSON: {str(e)}")
        return None

def get_imagery_dates(bounds, zoom_level):
    """
    Query ESRI World Imagery service for image dates within the given bounds.
    """
    if zoom_level < 12:
        st.sidebar.info("Please zoom in to level 12 or higher to see imagery dates.")
        return {}
        
    base_url = "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/0/query"
    
    params = {
        'f': 'json',
        'spatialRel': 'esriSpatialRelIntersects',
        'geometry': json.dumps({
            'xmin': bounds[0],
            'ymin': bounds[1],
            'xmax': bounds[2],
            'ymax': bounds[3],
            'spatialReference': {'wkid': 102100}
        }),
        'geometryType': 'esriGeometryEnvelope',
        'inSR': 102100,
        'outSR': 3857,
        'outFields': '*',
        'returnGeometry': True
    }
    
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        data = response.json()
        
        if 'features' not in data:
            st.sidebar.error("No imagery data received from the server.")
            return {}
            
        dates_dict = {}
        for feature in data['features']:
            if 'attributes' in feature and 'SRC_DATE' in feature['attributes']:
                date_str = str(feature['attributes']['SRC_DATE'])
                formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                geojson_feature = convert_esri_feature_to_geojson(feature)
                if geojson_feature:
                    dates_dict[formatted_date] = geojson_feature
                
        return dates_dict
        
    except requests.exceptions.RequestException as e:
        st.sidebar.error(f"Error fetching imagery dates: {str(e)}")
        return {}

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
                
                # Display WKT in the sidebar
                st.sidebar.markdown("---")
                st.sidebar.subheader("WKT Format")
                st.sidebar.text_area("WKT Representation", wkt_representation, height=100)
                
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