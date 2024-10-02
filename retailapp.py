import psycopg2
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai

# Configure Google Generative AI
genai.configure(api_key='AIzaSyDUUsTEvKKRya7u46jEJw4OMwFZ3dRKIRs')

# Initialize Flask App
app = Flask(__name__)
CORS(app)

location_data = pd.read_csv('data/locations.csv')

# Database connection function
def get_db_connection():
    conn = psycopg2.connect(
        user="postgres.qzudlrfcsaagrxvugzot",
        password="m6vuWFRSoHj2EHZe",  # Replace with your actual password
        host="aws-0-ap-south-1.pooler.supabase.com",
        port=6543,
        dbname="postgres"
    )
    return conn

# Database Setup
def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Create inventory table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventory (
            product_id SERIAL PRIMARY KEY,
            product_name TEXT,
            current_stock INTEGER,
            adjusted_stock INTEGER
        )
    ''')

    # Create sales data table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sales_data (
            date TEXT,
            product_id INTEGER,
            sales INTEGER,
            price REAL,
            economic_conditions TEXT
        )
    ''')
    # Create slots data table
    cursor.execute('''CREATE TABLE IF NOT EXISTS slots (
                        id SERIAL PRIMARY KEY,
                        date DATE,
                        time VARCHAR(50),
                        available INTEGER)''')

    # Create customer table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            user_id SERIAL PRIMARY KEY,
            name TEXT,
            email TEXT,
            gender TEXT,
            age INTEGER,
            location TEXT,
            account_creation_date TEXT,
            last_login_date TEXT,
            total_spent REAL,
            transaction_frequency INTEGER,
            average_transaction_value REAL,
            last_transaction_date TEXT,
            number_of_transactions INTEGER,
            favorite_payment_method TEXT,
            purchase_channel TEXT,
            preferred_device TEXT,
            preferred_language TEXT,
            time_on_site INTEGER,
            page_views_per_session INTEGER,
            average_cart_value REAL,
            abandoned_cart_count INTEGER,
            product_browsing_history TEXT,
            loyalty_program_member BOOLEAN,
            loyalty_points_balance INTEGER,
            email_open_rate REAL,
            email_click_rate REAL,
            SMS_opt_in BOOLEAN,
            SMS_click_rate REAL,
            best_time_in_the_day TEXT,
            best_day_in_a_week TEXT,
            best_week_in_a_month TEXT,
            coupon_usage_frequency INTEGER,
            social_media_engagement INTEGER,
            number_of_reviews_written INTEGER,
            average_review_rating REAL,
            referral_count INTEGER,
            customer_service_interactions INTEGER,
            live_chat_use_frequency INTEGER,
            marketing_segment TEXT,
            campaign_engagement_score REAL,
            preferred_communication_channel TEXT,
            click_through_rate REAL,
            conversion_rate REAL,
            discount_usage_rate REAL,
            preferred_brand TEXT,
            brand_loyalty_index REAL,
            lifetime_value_estimate REAL,
            frequency_of_visits_per_week INTEGER,
            returning_customer BOOLEAN,
            shopping_basket_value REAL,
            cart_conversion_rate REAL,
            purchase_value_category TEXT,
            transaction_frequency_category TEXT,
            product_affinity TEXT,
            discount_affinity TEXT
        )
    ''')

    conn.commit()
    cursor.close()
    conn.close()

# Load Sample Data into Database
def load_data():
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Load customer data from CSV
        customer_df = pd.read_csv('data/users.csv')
        for _, row in customer_df.iterrows():
            cursor.execute('''
                INSERT INTO customers (name, email, gender, age, location, account_creation_date, last_login_date, 
                                       total_spent, transaction_frequency, average_transaction_value, last_transaction_date, 
                                       number_of_transactions, favorite_payment_method, purchase_channel, preferred_device, 
                                       preferred_language, time_on_site, page_views_per_session, average_cart_value, 
                                       abandoned_cart_count, product_browsing_history, loyalty_program_member, 
                                       loyalty_points_balance, email_open_rate, email_click_rate, SMS_opt_in, SMS_click_rate, 
                                       best_time_in_the_day, best_day_in_a_week, best_week_in_a_month, coupon_usage_frequency, 
                                       social_media_engagement, number_of_reviews_written, average_review_rating, 
                                       referral_count, customer_service_interactions, live_chat_use_frequency, 
                                       marketing_segment, campaign_engagement_score, preferred_communication_channel, 
                                       click_through_rate, conversion_rate, discount_usage_rate, preferred_brand, 
                                       brand_loyalty_index, lifetime_value_estimate, frequency_of_visits_per_week, 
                                       returning_customer, shopping_basket_value, cart_conversion_rate, 
                                       purchase_value_category, transaction_frequency_category, product_affinity, 
                                       discount_affinity)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', tuple(row))
        conn.commit()

        # Load sales data from CSV
        sales_df = pd.read_csv('data/sales_data.csv')
        for _, row in sales_df.iterrows():
            cursor.execute('''
                INSERT INTO sales_data (date, product_id, sales, price, economic_conditions)
                VALUES (%s, %s, %s, %s, %s)
            ''', tuple(row))
        conn.commit()

        # Load inventory data from CSV
        inventory_df = pd.read_csv('data/inventory_data.csv')
        for _, row in inventory_df.iterrows():
            cursor.execute('''
                INSERT INTO inventory (product_name, current_stock, adjusted_stock)
                VALUES (%s, %s, %s)
            ''', tuple(row))
        conn.commit()

        print("Data loaded successfully.")

    except Exception as e:
        print(f"Error loading data: {e}")

    cursor.close()
    conn.close()

# Fetch Sales Data
def fetch_sales_data():
    conn = get_db_connection()
    query = '''
        SELECT * FROM sales_data
    '''
    sales_data = pd.read_sql(query, conn)
    conn.close()
    return sales_data

# Predictive Model
def train_demand_forecasting_model(sales_data):
    X = sales_data[['product_id', 'sales', 'price']]
    y = sales_data['sales']

    model = RandomForestRegressor()
    model.fit(X, y)
    return model

def predict_demand(model, new_data):
    return model.predict(new_data)

# Google Generative AI Insights
def generate_insight(customer_data):
    prompt = f"Analyze the following customer data and provide insights for inventory management: {customer_data}"
    response = genai.generate_text(prompt)
    return response.text

# Adjust Inventory Based on Predictions
def adjust_inventory():
    conn = get_db_connection()
    cursor = conn.cursor()
    sales_data = fetch_sales_data()
    
    for index, row in sales_data.iterrows():
        if row['sales'] > 100:
            new_stock = row['sales'] * 1.5  # Increase stock based on demand
            cursor.execute('UPDATE inventory SET adjusted_stock = %s WHERE product_id = %s', (new_stock, row['product_id']))
    
    conn.commit()
    cursor.close()
    conn.close()

def populate_slots():
    """Populates the delivery slots table with dummy data."""
    conn = get_db_connection()
    cursor = conn.cursor()
    slots = [
        ('2024-10-01', '10:00 - 12:00', 1),
        ('2024-10-01', '12:00 - 14:00', 1),
        ('2024-10-02', '14:00 - 16:00', 1),
    ]
    insert_query = '''INSERT INTO slots (date, time, available) VALUES (%s, %s, %s)'''
    cursor.executemany(insert_query, slots)
    conn.commit()
    cursor.close()
    conn.close()

def get_available_slots():
    """Fetches available delivery slots from PostgreSQL."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, date, time FROM slots WHERE available = 1")
    slots = cursor.fetchall()
    cursor.close()
    conn.close()
    return slots

def recommend_optimal_slots(user_location):
    """Recommends optimal delivery slots using Google Generative AI."""
    prompt = f"Based on the user's location at {user_location}, recommend the most optimal delivery slots."
    
    gem_model = genai.GenerativeModel("gemini-1.5-flash")
    
    try:
        response = gem_model.generate_content(prompt)
        if response and hasattr(response, 'text'):
            return response.text.strip()
        else:
            return "No recommendation could be generated."
    except Exception as e:
        print(f"Error generating content: {e}")
        return None

def score_locations(df):
    df['score'] = (
        df['population_density'] * 0.3 +
        df['income_level'] * 0.2 +
        df['competitors_nearby'] * -0.1 +
        df['traffic_score'] * 0.15 +
        df['public_transport_score'] * 0.1 +
        df['avg_rent'] * -0.1 +
        df['avg_shop_size'] * 0.05
    )
    return df.sort_values(by='score', ascending=False).head(5)

# Flask API Endpoints

@app.route('/api/inventory', methods=['GET'])
def get_inventory():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM inventory')
    inventory = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(inventory)

@app.route('/api/get_inventory', methods=['GET'])
def get_inventorydata():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM inventory')
    rows = cursor.fetchall()
    conn.close()
    return jsonify(rows)

@app.route('/api/get_sales_data', methods=['GET'])
def get_sales_data():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM sales_data')
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

@app.route('/api/generate-insights', methods=['POST'])
def generate_insights_route():
    customer_data = request.json['customer_data']
    insights = generate_insight(customer_data)
    return jsonify({'insights': insights})

@app.route('/api/optimal-locations', methods=['POST'])
def optimal_locations():
    request_data = request.json
    category = request_data.get('category')
    budget = request_data.get('budget')

    # Score locations based on the weighted criteria
    top_locations = score_locations(location_data)

    # Generate a business recommendation using Google Gemini
    prompt = f"Suggest the best location to open a new {category} store based on these top-scoring areas: {top_locations.to_dict(orient='records')}. The business has a budget of {budget}."

    # Specify the model when creating a ChatSession
    model = "gemini-1.5-pro"  # Replace with the desired model name
    #chat_session = gemini.ChatSession(model=model)  # Create a new chat session with the specified model

    # Generate the response directly with the prompt
    #gemini_response = chat_session.generate(prompt=prompt)

    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content(f"Suggest the best location to open a new {category} store based on these top-scoring areas: {top_locations.to_dict(orient='records')}. The business has a budget of {budget}.")

    return jsonify({
        'top_locations': top_locations[['latitude', 'longitude', 'score', 'avg_rent', 'traffic_score']].to_dict(orient='records'),
        'gemini_recommendation': response.text.strip()  # Ensure to access the correct attribute
    })

@app.route('/api/available-slots', methods=['GET'])
def available_slots():
    """API endpoint to fetch available delivery slots."""
    slots = get_available_slots()
    user_location = request.args.get('location')
    
    recommended_slots = recommend_optimal_slots(user_location)
    
    return jsonify({
        "available_slots": slots,
        "recommended_slots": recommended_slots
    })

@app.route('/api/reserve-slot', methods=['POST'])
def reserve_slot():
    """API endpoint to reserve a delivery slot."""
    slot_id = request.json.get('slot_id')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE slots SET available = 0 WHERE id = %s", (slot_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"status": "success", "message": "Slot reserved successfully!"})

if __name__ == '__main__':
    create_tables()
    populate_slots()
    app.run(debug=True)
