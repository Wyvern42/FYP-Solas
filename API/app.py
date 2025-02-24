from flask import Flask, request, jsonify
import requests
import psycopg2
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
import atexit

app = Flask(__name__)

# Configuration
GPS_ACCURACY_THRESHOLD = 15
WEATHER_API_KEY = '5949fe14755e489992a234453251702'
WEATHER_API_URL = 'http://api.weatherapi.com/v1/current.json'
LOCATION = 'Dublin'

# Database connection details
DB_HOST = "solasdb.cv868wmkkyqh.eu-north-1.rds.amazonaws.com"
DB_NAME = "Solasdb"
DB_USER = "wyvern42"
DB_PASSWORD = "FullMetal42"

# Global variable to store the latest weather data
latest_weather_data = {}

def get_db_connection():
    """Establish a connection to the PostgreSQL database."""
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )

def fetch_weather():
    """Fetch weather data using the WeatherAPI."""
    global latest_weather_data
    params = {
        'key': WEATHER_API_KEY,
        'q': LOCATION,
    }
    response = requests.get(WEATHER_API_URL, params=params)
    if response.status_code == 200:
        latest_weather_data = response.json()
    else:
        print(f"Failed to fetch weather data: {response.status_code}")

def get_current_datetime():
    """Get the current date and time in the required format."""
    now = datetime.now()
    return {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%Y-%m-%dT%H:%M:%S")
    }

def calculate_time_outside(user_id):
    """Calculate the time spent outside since the last 'false' entry."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT "time" FROM app_data
            WHERE user_id = %s AND "outside?" = TRUE
            AND "time" > COALESCE(
                (SELECT "time" FROM app_data
                 WHERE user_id = %s AND "outside?" = FALSE
                 ORDER BY "time" DESC
                 LIMIT 1),
                '1970-01-01'::timestamp
            )
            ORDER BY "time" ASC
            """,
            (user_id, user_id)
        )
        results = cur.fetchall()
        time_outside = 0
        if results:
            current_time = datetime.now()
            for result in results:
                last_outside_time = result[0]
                time_outside += (current_time - last_outside_time).total_seconds() / 3600  # Convert to hours
        cur.close()
        conn.close()
        return time_outside
    except Exception as e:
        print(f"Error calculating time outside: {e}")
        return 0

# Schedule the weather update every hour
scheduler = BackgroundScheduler()
scheduler.add_job(func=fetch_weather, trigger="interval", hours=1)
scheduler.start()

# Shut down the scheduler when exiting the app
atexit.register(lambda: scheduler.shutdown())

@app.route('/check-location', methods=['POST'])
def check_location():
    data = request.json
    user_id = data.get('user_id')
    gps_accuracy = data.get('gps_accuracy')

    if user_id is None or gps_accuracy is None:
        return jsonify({"error": "user_id and GPS accuracy are required"}), 400

    # Determine if the user is outside
    is_outside = gps_accuracy <= GPS_ACCURACY_THRESHOLD

    # Get current date and time
    current_datetime = get_current_datetime()

    # Fetch weather data
    weather = latest_weather_data.get('current', {}).get('condition', {}).get('text', 'Unknown')

    # Calculate time_outside if transitioning from outside to inside
    time_outside = 0
    if not is_outside:
        time_outside = calculate_time_outside(user_id)

    # Insert data into the database
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Check if the date has changed (reset total_hours_for_given_day if needed)
        cur.execute(
            """
            SELECT date, total_hours_for_given_day FROM app_data
            WHERE user_id = %s
            ORDER BY "time" DESC
            LIMIT 1
            """,
            (user_id,)
        )
        result = cur.fetchone()
        total_hours_for_given_day = 0
        if result:
            last_date = result[0]
            last_total_hours_for_given_day = result[1]
            current_date = datetime.strptime(current_datetime["date"], "%Y-%m-%d").date()
            if current_date != last_date:
                # Reset total_hours_for_given_day for the new day
                total_hours_for_given_day = 0
            else:
                total_hours_for_given_day = last_total_hours_for_given_day

        # Update total_hours_for_given_day and total_hours
        total_hours_for_given_day += time_outside
        total_hours = 0  # Initialize total_hours (you may fetch this from the database if needed)

        # Insert the new record
        cur.execute(
            """
            INSERT INTO app_data (
                user_id, total_hours, date, "time", total_available_hours,
                total_hours_for_given_day, "outside?", weather, time_outside
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user_id, total_hours, current_datetime["date"], current_datetime["time"],
                24, total_hours_for_given_day, is_outside, weather, time_outside
            )
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        return jsonify({"error": f"Database error: {str(e)}"}), 500

    # Include the latest weather data in the response
    response_data = {
        "is_outside": is_outside,
        "weather": weather,
        "time_outside": time_outside
    }

    return jsonify(response_data)

if __name__ == '__main__':
    # Fetch weather data immediately when the app starts
    fetch_weather()
    app.run(debug=True)

# python -m flask run --host=0.0.0.0