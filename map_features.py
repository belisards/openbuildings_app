
import requests
import json
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