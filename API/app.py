from flask import Flask, request, jsonify
import psycopg2
from datetime import datetime, time, timedelta

app = Flask(__name__)

# Configuration
GPS_ACCURACY_THRESHOLD = 15

# Database connection details
DB_HOST = "solasdb.cv868wmkkyqh.eu-north-1.rds.amazonaws.com"
DB_NAME = "Solasdb"
DB_USER = "wyvern42"
DB_PASSWORD = "FullMetal42"

def get_db_connection():
    """Establish a connection to the PostgreSQL database."""
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )

def get_current_datetime():
    """Get the current date and time in the required format."""
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")  # Format as YYYY-MM-DD HH:MM:SS

def format_time(total_seconds, separator=":"):
    """
    Convert total seconds into hrs:mins:secs format.
    :param total_seconds: Total time in seconds
    :param separator: Separator between hrs, mins, secs (default is ":")
    :return: Formatted time string (e.g., "1:4:15")
    """
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(hours)}{separator}{int(minutes)}{separator}{int(seconds)}"

def calculate_time_outside(user_id):
    """Calculate the time spent outside since the last 'false' entry, only for the current day, in seconds."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Get the current date
        current_date = datetime.now().date()

        cur.execute(
            """
            SELECT "time" FROM updated_table
            WHERE user_id = %s AND "outside?" = TRUE
            AND "time" > COALESCE(
                (SELECT "time" FROM updated_table
                 WHERE user_id = %s AND "outside?" = FALSE
                 AND DATE("time") = %s
                 ORDER BY "time" DESC
                 LIMIT 1),
                '1970-01-01'::timestamp
            )
            AND DATE("time") = %s
            ORDER BY "time" ASC
            """,
            (user_id, user_id, current_date, current_date)
        )
        results = cur.fetchall()
        time_outside = 0
        if results:
            current_time = datetime.now()
            for result in results:
                last_outside_time = result[0]
                time_outside += (current_time - last_outside_time).total_seconds()  # Keep it in seconds
        cur.close()
        conn.close()
        return time_outside
    except Exception as e:
        print(f"Error calculating time outside: {e}")
        return 0

def is_daytime(sunrise, sunset):
    """Determine if the current time is daytime based on sunrise and sunset times (24-hour format)."""
    now = datetime.now().time()
    try:
        sunrise_time = datetime.strptime(sunrise, "%H:%M").time()  # Parse 24-hour format
        sunset_time = datetime.strptime(sunset, "%H:%M").time()    # Parse 24-hour format
        return sunrise_time <= now <= sunset_time
    except ValueError as e:
        print(f"Error parsing sunrise/sunset times: {e}")
        return False

def calculate_available_hours(sunrise, sunset):
    """Calculate the total available daylight hours based on sunrise and sunset times (24-hour format)."""
    try:
        sunrise_time = datetime.strptime(sunrise, "%H:%M")
        sunset_time = datetime.strptime(sunset, "%H:%M")
        daylight_duration = sunset_time - sunrise_time
        return round(daylight_duration.total_seconds() / 3600, 2)  # Convert to hours and round to 2 decimal places
    except ValueError as e:
        print(f"Error calculating available hours: {e}")
        return 0

@app.route('/submit-feedback', methods=['POST'])
def submit_feedback():
    data = request.json
    user_id = data.get('user_id')
    correct_result = data.get('correct_result')
    gps_accuracy = data.get('gps_accuracy')

    if user_id is None or correct_result is None or gps_accuracy is None:
        return jsonify({"error": "user_id, correct_result, and gps_accuracy are required"}), 400

    current_time = get_current_datetime()  # Use the same time format

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO app_accuracy (user_id, time, correct_result, gps_accuracy)
            VALUES (%s, %s, %s, %s)
            """,
            (user_id, current_time, correct_result, round(gps_accuracy, 2))  # Round GPS accuracy to 2 decimal places
        )
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"message": "Feedback submitted successfully"}), 200
    except Exception as e:
        return jsonify({"error": f"Database error: {str(e)}"}), 500


@app.route('/weekly-time-outside', methods=['GET'])
def get_weekly_time_outside():
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Get the start and end of the current week
        today = datetime.now().date()
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)

        # Query to calculate total time outside in seconds
        cur.execute(
            """
            SELECT 
                DATE("time") as date, 
                SUM(
                    CAST(SPLIT_PART(total_time_outside, ':', 1) AS INTEGER) * 3600 + -- Hours to seconds
                    CAST(SPLIT_PART(total_time_outside, ':', 2) AS INTEGER) * 60 +    -- Minutes to seconds
                    CAST(SPLIT_PART(total_time_outside, ':', 3) AS INTEGER)           -- Seconds
                ) as total_time_outside_seconds
            FROM updated_table
            WHERE user_id = %s AND DATE("time") BETWEEN %s AND %s
            GROUP BY DATE("time")
            ORDER BY DATE("time")
            """,
            (user_id, start_of_week, end_of_week)
        )
        results = cur.fetchall()

        cur.close()
        conn.close()

        # Format the results to include the day of the week
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        weekly_data = []
        for result in results:
            date = result[0]
            day_of_week = date.weekday()  # Get the day of the week as an integer (0 = Monday, 6 = Sunday)
            day_name = day_names[day_of_week]  # Convert to day name
            total_time_outside = result[1]  # Total time outside in seconds

            weekly_data.append({
                "day": day_name,
                "total_time_outside": total_time_outside
            })

        return jsonify(weekly_data), 200
    except Exception as e:
        print(f"Error in /weekly-time-outside: {str(e)}")
        return jsonify({"error": f"Database error: {str(e)}"}), 500

@app.route('/check-location', methods=['POST'])
def check_location():
    data = request.json
    user_id = data.get('user_id')
    gps_accuracy = data.get('gps_accuracy')
    is_connected_to_wifi = data.get('is_connected_to_wifi', False)  # Default to False if not provided
    weather = data.get('weather', 'Unknown')  # Get weather data from the app
    temperature = data.get('temperature', None)  # Get temperature
    uv = data.get('uv', None)  # Get UV index
    sunrise = data.get('sunrise')  # Get sunrise time (24-hour format)
    sunset = data.get('sunset')  # Get sunset time (24-hour format)

    if user_id is None or gps_accuracy is None:
        return jsonify({"error": "user_id and GPS accuracy are required"}), 400

    # Round GPS accuracy to 2 decimal places
    gps_accuracy = round(gps_accuracy, 2)

    # Determine if the user is outside
    is_outside = gps_accuracy <= GPS_ACCURACY_THRESHOLD

    # If the user is connected to Wi-Fi, assume they are inside
    if is_connected_to_wifi:
        is_outside = False

    # Get current date and time
    current_datetime = get_current_datetime()

    # Fetch the last recorded state of the user
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT "outside?", time FROM updated_table
        WHERE user_id = %s
        ORDER BY "time" DESC
        LIMIT 1
        """,
        (user_id,)
    )
    result = cur.fetchone()
    last_is_outside = result[0] if result else False
    last_time = result[1] if result else None

    # Calculate time_outside if transitioning from outside to inside
    time_outside = 0
    if (not is_outside and last_is_outside) or (sunset and last_is_outside):
        # If the user was outside and is now inside, or it's sunset and the user was last outside,
        # calculate the time spent outside since the last check
        if last_time:
            time_outside = (current_datetime - last_time).total_seconds()
        else:
            time_outside = 0

    # Format time_outside
    time_outside_formatted = format_time(time_outside, separator=":")  # Format as hrs:mins:secs

    # Check if it is daytime
    if sunrise and sunset:
        if not is_daytime(sunrise, sunset):
            return jsonify({
                "message": "It is not daytime. Data will not be saved to the database.",
                "is_outside": is_outside,
                "weather": weather,
                "time_outside": time_outside_formatted,
                "temperature": temperature,
                "uv": uv
            })

    # Calculate available daylight hours
    total_available_hours = calculate_available_hours(sunrise, sunset)

    # Insert data into the database (only if it is daytime)
    try:
        # Fetch the latest total_time_outside and total_time_outside_for_given_day for the user
        cur.execute(
            """
            SELECT time, total_time_outside, total_time_outside_for_given_day FROM updated_table
            WHERE user_id = %s
            ORDER BY "time" DESC
            LIMIT 1
            """,
            (user_id,)
        )
        result = cur.fetchone()
        total_time_outside_seconds = 0
        total_time_outside_for_given_day_seconds = 0
        if result:
            last_time = result[0]
            last_total_time_outside = result[1]
            last_total_time_outside_for_given_day = result[2]

            # Convert formatted time strings back to seconds
            def time_to_seconds(time_str):
                h, m, s = map(int, time_str.split(":"))
                return h * 3600 + m * 60 + s

            total_time_outside_seconds = time_to_seconds(last_total_time_outside)
            total_time_outside_for_given_day_seconds = time_to_seconds(last_total_time_outside_for_given_day)

            current_date = datetime.now().date()
            last_date = last_time.date()
            if current_date != last_date:
                # Reset total_time_outside_for_given_day for the new day
                total_time_outside_for_given_day_seconds = time_outside
            else:
                # Add to the existing total_time_outside_for_given_day
                total_time_outside_for_given_day_seconds += time_outside

        # Add to the cumulative total_time_outside
        total_time_outside_seconds += time_outside

        # Format total_time_outside and total_time_outside_for_given_day
        total_time_outside_formatted = format_time(total_time_outside_seconds, separator=":")
        total_time_outside_for_given_day_formatted = format_time(total_time_outside_for_given_day_seconds, separator=":")

        # Insert the new record
        cur.execute(
            """
            INSERT INTO updated_table (
                user_id, total_time_outside, time, total_available_hours,
                total_time_outside_for_given_day, "outside?", weather, time_outside, temperature, uv
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user_id, total_time_outside_formatted, current_datetime, total_available_hours,
                total_time_outside_for_given_day_formatted, is_outside, weather, time_outside_formatted, temperature, uv
            )
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        return jsonify({"error": f"Database error: {str(e)}"}), 500

    # Include the latest data in the response
    response_data = {
        "is_outside": is_outside,
        "weather": weather,
        "time_outside": time_outside_formatted,
        "total_time_outside": total_time_outside_formatted,
        "total_time_outside_for_given_day": total_time_outside_for_given_day_formatted,
        "temperature": temperature,
        "uv": uv,
        "total_available_hours": total_available_hours,
        "gps_accuracy": gps_accuracy  # Include the rounded GPS accuracy in the response
    }

    return jsonify(response_data)
if __name__ == '__main__':
    app.run(debug=True)

# python -m flask run --host=0.0.0.0

#curl -X POST http://192.168.68.103:5000/check-location -H "Content-Type: application/json" -d "{\"user_id\": \"user123\", \"gps_accuracy\": 20, \"is_connected_to_wifi\": false, \"weather\": \"Sunny\"}"