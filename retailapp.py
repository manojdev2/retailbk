from flask import Flask, request, jsonify
import pandas as pd
import numpy as np
from flask_cors import CORS
import google.generativeai as genai
import psycopg2
from sklearn.ensemble import RandomForestRegressor

app = Flask(__name__)
CORS(app)

genai.configure(api_key='AIzaSyDUUsTEvKKRya7u46jEJw4OMwFZ3dRKIRs')

def get_db_connection():
    conn = psycopg2.connect(
        user="postgres.qzudlrfcsaagrxvugzot",
        password="m6vuWFRSoHj2EHZe",  # Replace with your actual password
        host="aws-0-ap-south-1.pooler.supabase.com",
        port=6543,
        dbname="postgres"
    )
    return conn

def get_store_data():
    conn = get_db_connection()
    query = "SELECT store_id, location_x, location_y, inventory, demand, brand, store_name, price_per_unit FROM croma_inventory_data;"
    store_data = pd.read_sql(query, conn)
    conn.close()
    return store_data

# Fetch Sales Data
def fetch_sales_data():
    conn = get_db_connection()
    query = '''
        SELECT * FROM sales_data
    '''
    sales_data = pd.read_sql(query, conn)
    conn.close()
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
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error in recommendation: {str(e)}"

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
                    
                    reallocation_decisions.append({
                        'from_store': row['store_id'],
                        'to_store': nearby_row['store_id'],
                        'from_store_name':row['store_name'],
                        'to_store_name': nearby_row['store_name'],
                        'brand':row['brand'],
                        'amount': amount_to_reallocate,
                        'recommendation': recommendation,
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
    conn = get_db_connection()
    query = '''
        SELECT * FROM sales_data
    '''
    sales_data = pd.read_sql(query, conn)
    conn.close()
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
