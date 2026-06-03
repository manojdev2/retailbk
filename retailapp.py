import os
import math
from flask import Flask, request, jsonify
import pandas as pd
import numpy as np
import requests
from flask_cors import CORS
from google import genai
import psycopg2
from sqlalchemy import create_engine
from sklearn.ensemble import RandomForestRegressor

app = Flask(__name__)
CORS(app)

genai_client = genai.Client(api_key='AQ.Ab8RN6IyFS062yHHQoEzLqFIpwZpet22tjhVVUy48D82pe2xfQ')
GMAPS_API_KEY = "AIzaSyDUyyoQCBngveLtfNNWb-brGXqmY-Qb0hs"

# Google Maps Routes API (computeRoutes) — the current replacement for the
# deprecated legacy Directions API used by the googlemaps client library.
ROUTES_API_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"

# Models tried in order: primary first, lighter fallbacks if it fails (e.g. quota/availability).
GEMINI_MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3.1-flash-lite"]

def generate_content_with_fallback(prompt):
    last_error = None
    for model in GEMINI_MODELS:
        try:
            response = genai_client.models.generate_content(
                model=model,
                contents=prompt,
            )
            return response.text
        except Exception as e:
            last_error = e
            continue
    raise last_error

DB_CONFIG = {
    "user": "postgres.awgupcysazlmzpsrgkxz",
    "password": "pykPKDDZhPYjDoZY",
    "host": "aws-1-ap-northeast-1.pooler.supabase.com",
    "port": 6543,
    "dbname": "postgres",
}

def get_db_connection():
    conn = psycopg2.connect(**DB_CONFIG)
    return conn

# SQLAlchemy engine for pandas reads (pandas no longer supports raw DBAPI connections).
db_engine = create_engine(
    "postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}".format(**DB_CONFIG)
)

def get_store_data():
    query = "SELECT store_id, location_x, location_y, inventory, demand, brand, store_name, price_per_unit FROM croma_inventory_data;"
    store_data = pd.read_sql(query, db_engine)
    return store_data

# Fetch Sales Data
def fetch_sales_data():
    query = '''
        SELECT * FROM sales_data
    '''
    sales_data = pd.read_sql(query, db_engine)
    return sales_data

@app.route('/api/inventory', methods=['GET'])
def get_inventory():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM inventory')
    inventory = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(inventory)

def get_reallocation_recommendation(store_id, excess_inventory, demand):
    prompt = (
        f"Given the store ID {store_id} with an excess inventory of {excess_inventory} "
        f"and a demand of {demand}, provide a stock reallocation recommendation."
    )
    try:
        return generate_content_with_fallback(prompt)
    except Exception as e:
        return f"Error in recommendation: {str(e)}"
    
COST_PER_KM = 2.0            # Transport cost per km per unit
CARBON_PER_KM = 0.1          # kg CO2 per km per unit
ROAD_WINDING_FACTOR = 1.3    # Straight-line -> approx road distance
AVG_SPEED_KMPH = 40.0        # Assumed average driving speed for the estimate


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance between two lat/lon points, in kilometers."""
    r = 6371.0  # Earth radius in km
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


def _build_cost_payload(distance_km, travel_time_min, amount, polyline, estimated):
    return {
        'distance_km': distance_km,
        'travel_time_min': travel_time_min,
        'transport_cost': distance_km * COST_PER_KM * amount,
        'carbon_footprint': distance_km * CARBON_PER_KM * amount,
        'route_polyline': polyline,
        'estimated': estimated,
    }


def estimate_route_and_cost(start_location, end_location, amount_to_reallocate):
    """Fallback used when the Routes API is unavailable: straight-line distance
    (scaled to approximate roads) and a time estimate from an assumed speed."""
    straight = haversine_km(
        start_location['lat'], start_location['lon'],
        end_location['lat'], end_location['lon'],
    )
    distance_km = straight * ROAD_WINDING_FACTOR
    travel_time_min = (distance_km / AVG_SPEED_KMPH) * 60
    return _build_cost_payload(distance_km, travel_time_min, amount_to_reallocate, '', True)


def calculate_route_and_cost(start_location, end_location, amount_to_reallocate):
    """Driving distance/time via the Google Maps Routes API, with a haversine
    fallback so the numbers are always meaningful even if the API call fails."""
    try:
        body = {
            "origin": {"location": {"latLng": {
                "latitude": start_location['lat'], "longitude": start_location['lon']}}},
            "destination": {"location": {"latLng": {
                "latitude": end_location['lat'], "longitude": end_location['lon']}}},
            "travelMode": "DRIVE",
            "routingPreference": "TRAFFIC_UNAWARE",
            "units": "METRIC",
        }
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": GMAPS_API_KEY,
            "X-Goog-FieldMask": "routes.distanceMeters,routes.duration,routes.polyline.encodedPolyline",
        }
        resp = requests.post(ROUTES_API_URL, json=body, headers=headers, timeout=10)
        resp.raise_for_status()
        routes = resp.json().get("routes", [])

        if routes:
            route = routes[0]
            distance_km = route.get("distanceMeters", 0) / 1000
            # duration comes back as a string like "1234s".
            travel_time_min = int(str(route.get("duration", "0s")).rstrip("s") or 0) / 60
            polyline = route.get("polyline", {}).get("encodedPolyline", "")
            if distance_km > 0:
                return _build_cost_payload(
                    distance_km, travel_time_min, amount_to_reallocate, polyline, False)

        # No usable route returned -> fall back to an estimate.
        return estimate_route_and_cost(start_location, end_location, amount_to_reallocate)
    except Exception:
        # Any API/network error -> fall back to an estimate rather than zeros.
        return estimate_route_and_cost(start_location, end_location, amount_to_reallocate)


@app.route('/api/reallocate_stock', methods=['POST'])
def reallocate_stock():
    global store_data
    store_data = get_store_data()  # Fetch store data from the database
    store_data['excess_inventory'] = store_data['inventory'] - store_data['demand']
    
    reallocation_decisions = []
    
    for index, row in store_data.iterrows():
        if row['excess_inventory'] > 0:
            nearby_stores = store_data[
                (store_data['demand'] > store_data['inventory']) &
                (np.abs(row['location_x'] - store_data['location_x']) < 1) &
                (np.abs(row['location_y'] - store_data['location_y']) < 1)
            ]
            for _, nearby_row in nearby_stores.iterrows():
                if nearby_row['inventory'] > 0:
                    amount_to_reallocate = min(row['excess_inventory'], nearby_row['demand'])

                    if row['price_per_unit'] < nearby_row['price_per_unit']:
                        # Calculate profit if reallocation occurs
                        profit = (nearby_row['price_per_unit'] - row['price_per_unit']) * amount_to_reallocate
                    else:
                        profit = 0  # No profit if the source store's price is higher or equal

                    recommendation = get_reallocation_recommendation(row['store_id'], amount_to_reallocate, nearby_row['demand'])

                    start_location = {'lat': row['location_x'], 'lon': row['location_y']}
                    end_location = {'lat': nearby_row['location_x'], 'lon': nearby_row['location_y']}
                    route_info = calculate_route_and_cost(start_location, end_location, amount_to_reallocate);
                    
                    reallocation_decisions.append({
                        'from_store': row['store_id'],
                        'to_store': nearby_row['store_id'],
                        'from_store_name':row['store_name'],
                        'to_store_name': nearby_row['store_name'],
                        'brand':row['brand'],
                        'amount': amount_to_reallocate,
                        'recommendation': recommendation,
                        'transport_cost': route_info['transport_cost'],
                        'travel_time_min': route_info['travel_time_min'],
                        'distance_km': route_info['distance_km'],
                        'carbon_footprint': route_info['carbon_footprint'],
                        'route_polyline': route_info['route_polyline'],
                        'estimated': route_info.get('estimated', False),
                        'profit': profit
                    })
                   
                    # Update inventories
                    store_data.loc[index, 'inventory'] -= amount_to_reallocate
                    store_data.loc[store_data['store_id'] == nearby_row['store_id'], 'inventory'] += amount_to_reallocate
                    
                    # Break after one reallocation per store
                    break

    return jsonify(reallocation_decisions)

# def get_store_data_csv():
#     # Load data from a CSV file into a DataFrame
#     return pd.read_csv('data/croma_stores_inventory.csv')

# @app.route('/api/reallocate_stock', methods=['POST'])
# def reallocate_stock():
#     # global store_data
#     store_data = get_store_data_csv()  # Fetch store data from the database
#     store_data['excess_inventory'] = store_data['inventory'] - store_data['demand']
    
#     reallocation_decisions = []
    
#     for index, row in store_data.iterrows():
#         if row['excess_inventory'] > 0:
#             nearby_stores = store_data[
#                 (store_data['demand'] > store_data['inventory']) &
#                 (np.abs(row['location_x'] - store_data['location_x']) < 1) &
#                 (np.abs(row['location_y'] - store_data['location_y']) < 1)
#             ]
#             for _, nearby_row in nearby_stores.iterrows():
#                 if nearby_row['inventory'] > 0:
#                     amount_to_reallocate = min(row['excess_inventory'], nearby_row['demand'])
                    
#                     # Compare prices and calculate profit
#                     if row['price_per_unit'] < nearby_row['price_per_unit']:
#                         # Calculate profit if reallocation occurs
#                         profit = (nearby_row['price_per_unit'] - row['price_per_unit']) * amount_to_reallocate
#                     else:
#                         profit = 0  # No profit if the source store's price is higher or equal
                    
#                     recommendation = get_reallocation_recommendation(row['store_id'], amount_to_reallocate, nearby_row['demand'])
                    
#                     reallocation_decisions.append({
#                         'from_store': row['store_id'],
#                         'to_store': nearby_row['store_id'],
#                         'from_store_name': row['store_name'],
#                         'to_store_name': nearby_row['store_name'],
#                         'brand': row['brand'],
#                         'amount': amount_to_reallocate,
#                         'recommendation': recommendation,
#                         'profit': profit
#                     })

#                     # Update inventories
#                     store_data.loc[index, 'inventory'] -= amount_to_reallocate
#                     store_data.loc[store_data['store_id'] == nearby_row['store_id'], 'inventory'] += amount_to_reallocate
                    
#                     # Break after one reallocation per store
#                     break

#     return jsonify(reallocation_decisions)

@app.route('/api/stores', methods=['GET'])
def get_stores():
    global store_data
    store_data = get_store_data()  # Fetch store data from the database
    return jsonify(store_data.to_dict(orient='records'))

def fetch_sales_data():
    query = '''
        SELECT * FROM sales_data
    '''
    sales_data = pd.read_sql(query, db_engine)
    return sales_data

@app.route('/api/get_sales_data', methods=['GET'])
def get_sales_data():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM sales_data')
    rows = cursor.fetchall()
    conn.close()
    return jsonify(rows)

# Predictive Model
def train_demand_forecasting_model(sales_data):
    X = sales_data[['product_id', 'sales', 'price']]
    y = sales_data['sales']

    model = RandomForestRegressor()
    model.fit(X, y)
    return model

def predict_demand(model, new_data):
    return model.predict(new_data)

@app.route('/api/get_inventory', methods=['GET'])
def get_inventorydata():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM inventory')
    rows = cursor.fetchall()
    conn.close()
    return jsonify(rows)

@app.route('/api/predict-demand', methods=['POST'])
def predict_demand_route():
    data = request.json
    product_id = data['product_id']
    sales = data['sales']
    price = data['price']
    new_data = pd.DataFrame({'product_id': [product_id], 'sales': [sales], 'price': [price]})
    
    sales_data = fetch_sales_data()
    model = train_demand_forecasting_model(sales_data)
    prediction = predict_demand(model, new_data)
    return jsonify({'predicted_demand': prediction.tolist()})

if __name__ == '__main__':
    app.run(debug=True)
