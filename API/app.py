from flask import Flask, request, jsonify
from matplotlib.patches import Arc
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from io import BytesIO
import base64
from datetime import datetime, time, timedelta
import psycopg2
from typing import Dict, Any, Tuple, List, Optional
from matplotlib import patheffects

# Initialize Flask app
app = Flask(__name__)

GPS_ACCURACY_THRESHOLD = 15

# Database configuration
DB_CONFIG = {
    "host": "solasdb.cv868wmkkyqh.eu-north-1.rds.amazonaws.com",
    "database": "Solasdb",
    "user": "wyvern42",
    "password": "FullMetal42"
}

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

def get_current_datetime() -> str:

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def format_time(total_seconds: int) -> str:
    """Convert total seconds into hrs:mins:secs format."""
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(hours)}:{int(minutes):02d}:{int(seconds):02d}"

def calculate_time_outside(user_id: str) -> int:
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        current_date = datetime.now().date()

        cur.execute(
            """
            SELECT "time" FROM final_table
            WHERE user_id = %s AND "outside?" = TRUE
            AND "time" > COALESCE(
                (SELECT "time" FROM final_table
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
                time_outside += int((current_time - last_outside_time).total_seconds())
        return time_outside
    except Exception as e:
        print(f"Error calculating time outside: {e}")
        return 0
    finally:
        if 'conn' in locals():
            conn.close()

def is_daytime(sunrise: str, sunset: str) -> bool:
    try:
        now = datetime.now().time()
        sunrise_time = datetime.strptime(sunrise, "%H:%M").time()
        sunset_time = datetime.strptime(sunset, "%H:%M").time()
        return sunrise_time <= now <= sunset_time
    except ValueError as e:
        print(f"Error parsing sunrise/sunset times: {e}")
        return False

def calculate_available_hours(sunrise: str, sunset: str) -> float:
    try:
        sunrise_time = datetime.strptime(sunrise, "%H:%M")
        sunset_time = datetime.strptime(sunset, "%H:%M")
        daylight_duration = sunset_time - sunrise_time
        return round(daylight_duration.total_seconds() / 3600, 2)
    except ValueError as e:
        print(f"Error calculating available hours: {e}")
        return 0.0

@app.route('/submit-feedback', methods=['POST'])
def submit_feedback() -> Tuple[Dict[str, Any], int]:
    data = request.get_json()
    if not data:
        return {"error": "Request must be JSON"}, 400

    required_fields = ['user_id', 'correct_result', 'gps_accuracy']
    if not all(field in data for field in required_fields):
        return {"error": f"Missing required fields: {required_fields}"}, 400

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO app_accuracy (user_id, time, correct_result, gps_accuracy)
            VALUES (%s, %s, %s, %s)
            """,
            (data['user_id'], get_current_datetime(), 
             data['correct_result'], round(data['gps_accuracy'], 2))
        )
        conn.commit()
        return {"message": "Feedback submitted successfully"}, 200
    except Exception as e:
        return {"error": f"Database error: {str(e)}"}, 500
    finally:
        if 'conn' in locals():
            conn.close()

@app.route('/daily-visualisation', methods=['POST'])
def daily_visualisation():
    try:
        data = request.get_json()
        if not data or 'user_id' not in data:
            return jsonify({"error": "user_id is required in request body"}), 400

        user_id = data['user_id']
        conn = get_db_connection()
        cur = conn.cursor()
        today = datetime.now().date()

        # Validate sunrise/sunset
        if 'sunrise' not in data or 'sunset' not in data:
            return jsonify({"error": "sunrise and sunset times are required"}), 400

        sunrise_str = data['sunrise']
        sunset_str = data['sunset']

        # Get total time outside
        cur.execute(
            """SELECT total_time_outside_for_given_day FROM final_table
               WHERE user_id = %s AND DATE(time) = %s
               ORDER BY time DESC LIMIT 1""",
            (user_id, today)
        )
        total_time_seconds = cur.fetchone()[0] or 0
        formatted_time = format_time(total_time_seconds)

        # Get outdoor periods
        cur.execute(
            """SELECT time, "outside?" FROM final_table
               WHERE user_id = %s AND DATE(time) = %s
               ORDER BY time ASC""",
            (user_id, today)
        )
        results = cur.fetchall()

        outdoor_periods = []
        prev_time, prev_outside = None, False
        for record_time, outside in results:
            if prev_outside and not outside and prev_time:
                outdoor_periods.append((prev_time.time(), record_time.time()))
            prev_time, prev_outside = record_time, outside

        if prev_outside and prev_time:
            outdoor_periods.append((prev_time.time(), datetime.now().time()))

        # Convert sunrise/sunset
        try:
            sunrise_time = datetime.strptime(sunrise_str, "%H:%M").time()
            sunset_time = datetime.strptime(sunset_str, "%H:%M").time()
        except ValueError:
            return jsonify({"error": "Invalid time format (expected HH:MM)"}), 400

        # Create visualization
        plt.style.use('dark_background')
        fig, ax = plt.subplots(figsize=(14, 10), facecolor='#1a1a1a')
        fig.patch.set_edgecolor('#FFA500')
        fig.patch.set_linewidth(3)

        radius = 10
        center = (0, 0)
        arc_width = 50

        # Calculate daylight duration
        daylight_duration = (datetime.combine(today, sunset_time) - 
                          datetime.combine(today, sunrise_time)).total_seconds()
        
        def time_to_daylight_angle(t: time) -> float:
            if t <= sunrise_time: return 0
            if t >= sunset_time: return 180
            seconds = (datetime.combine(today, t) - 
                     datetime.combine(today, sunrise_time)).total_seconds()
            return 180 * (seconds / daylight_duration)

        ax.set_xlim(radius+3, -radius-3)  

        # Draw base arch
        daylight_arc = Arc(center, 2*radius, 2*radius, angle=0,
                         theta1=0, theta2=180, color='#3a3a3a', lw=arc_width)
        ax.add_patch(daylight_arc)
        
        # Draw outdoor periods
        for start, end in outdoor_periods:
            start_clipped = max(start, sunrise_time)
            end_clipped = min(end, sunset_time)
            if start_clipped >= end_clipped: continue  
                
            start_angle = time_to_daylight_angle(start_clipped)
            end_angle = time_to_daylight_angle(end_clipped)
            
            outdoor_arc = Arc(center, 2*radius, 2*radius, angle=0,
                            theta1=start_angle, theta2=end_angle,
                            color='#FFA500', lw=arc_width)
            ax.add_patch(outdoor_arc)

        # Time markers (adjusted for flipped coordinates)
        midday_time = (datetime.combine(today, sunrise_time) + 
                     timedelta(seconds=daylight_duration/2)).time()
        
        for time_marker, label in [
            (sunrise_time, sunrise_str),
            (midday_time, "Midday"), 
            (sunset_time, sunset_str)
        ]:
            angle = time_to_daylight_angle(time_marker)
            x, y = radius * np.cos(np.radians(angle)), radius * np.sin(np.radians(angle))
            
            ha = 'left' if angle < 90 else 'right' if angle > 90 else 'center'
            offset_x = 0.6 if angle < 90 else -0.6 if angle > 90 else 0
            offset_y = 0.6 if angle == 90 else 0
            
            ax.text(x + offset_x, y + offset_y, label,  
                   color='white', ha=ha, va='center', fontsize=14, fontweight='bold')

        # Center texts
        ax.text(0, 5, "Recommended daylight\nexposure per day:\n45Mins-2hrs", 
               color='white', ha='center', va='center',
               fontsize=20, fontweight='bold', alpha=0.8)

        ax.text(0, 0, formatted_time, 
               color='#FFA500', ha='center', va='center',
               fontsize=42, fontweight='bold',
               bbox=dict(facecolor='#1a1a1a88', edgecolor='#FFA500',
                        boxstyle='round,pad=0.8', linewidth=3))

        ax.set_ylim(0, radius+3)
        ax.axis('off')
        ax.set_aspect('equal')
        plt.title('Daylight Exposure', color='#FFA500', pad=30, fontsize=30, fontweight='bold')
        
        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=180, bbox_inches='tight',
                   facecolor=fig.get_facecolor(), edgecolor=fig.get_edgecolor())
        plt.close(fig)
        buf.seek(0)
        
        return jsonify({
            "image": base64.b64encode(buf.read()).decode('utf-8'),
            "total_time_outside": formatted_time,
            "sunrise": sunrise_str,
            "sunset": sunset_str
        }), 200

    except Exception as e:
        print(f"Visualization error: {str(e)}")
        return jsonify({"error": str(e)}), 500
    finally:
        if 'conn' in locals(): conn.close()
        plt.close('all')




@app.route('/weekly-time-outside-graph', methods=['POST'])
def weekly_time_outside_graph():
    try:
        data = request.get_json()
        if not data or 'user_id' not in data:
            return jsonify({"error": "user_id is required in request body"}), 400

        user_id = data['user_id']
        conn = get_db_connection()
        cur = conn.cursor()

        # Get start and end of current week (Monday to Sunday)
        today = datetime.now().date()
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)

        # Fetch the latest record per day (keeping your existing query logic)
        cur.execute(
            """
            WITH ranked_entries AS (
                SELECT 
                    DATE("time") as date,
                    total_time_outside_for_given_day as time_seconds,
                    ROW_NUMBER() OVER (PARTITION BY DATE("time") ORDER BY "time" DESC) as row_num
                FROM final_table
                WHERE user_id = %s AND DATE("time") BETWEEN %s AND %s
            )
            SELECT date, time_seconds
            FROM ranked_entries
            WHERE row_num = 1
            ORDER BY date
            """,
            (user_id, start_of_week, end_of_week)
        )
        results = cur.fetchall()

        # Initialize all days of the week with 0 values
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        days = []
        seconds = []
        hours = []
        
        # Create a dictionary of existing data
        existing_data = {record[0]: record[1] for record in results}
        
        # Generate data for all 7 days of the week
        for day_offset in range(7):
            current_date = start_of_week + timedelta(days=day_offset)
            days.append(day_names[day_offset])
            
            # Use existing data if available, otherwise 0
            time_seconds = existing_data.get(current_date, 0)
            seconds.append(time_seconds)
            hours.append(time_seconds / 3600)

        # Create the plot 
        plt.style.use('dark_background')
        fig = plt.figure(figsize=(10, 6), facecolor='#1a1a1a')
        fig.patch.set_edgecolor('#FFA500')
        fig.patch.set_linewidth(2)
        
        ax = fig.add_subplot(111, facecolor='#2a2a2a')
        
        bars = ax.bar(
            range(len(days)), 
            hours, 
            width=0.7, 
            color='#FFA500', 
            alpha=0.9,
            edgecolor='#FFA500',
            linewidth=1.5,
            zorder=2,
            capstyle='round'  
        )
        

        ax.set_title('Weekly Time Spent Outside', 
                    color='#FFA500', 
                    pad=25, 
                    fontsize=16, 
                    fontweight='bold',
                    fontfamily='sans-serif',
                    loc='center')
        
        ax.set_ylabel('Hours Outside', 
                     color='#FFA500', 
                     fontsize=12, 
                     labelpad=15,
                     fontfamily='sans-serif')
        
        y_max = max(hours) * 1.3 if max(hours) > 0 else 5
        ax.set_ylim(0, y_max)
        
        ax.set_xticks(range(len(days)))
        ax.set_xticklabels(days)
        
        ax.tick_params(axis='x', colors='#FFA500', labelsize=12, pad=10)
        ax.tick_params(axis='y', colors='#FFA500', labelsize=11)
        
        ax.grid(color='#FFA50033', linestyle='--', linewidth=0.8, alpha=0.5, zorder=1)
        ax.axhline(0, color='#FFA500', linestyle='-', linewidth=1.5, zorder=2)
        
        for spine in ax.spines.values():
            spine.set_visible(False)
        
        fig.canvas.draw()
        plt.tight_layout(pad=3)

        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=120, bbox_inches='tight', facecolor=fig.get_facecolor(), edgecolor=fig.get_edgecolor())
        plt.close(fig)
        buf.seek(0)
        
        return jsonify({
            "image": base64.b64encode(buf.read()).decode('utf-8'),
            "days": days,
            "hours": hours,
            "seconds": seconds
        }), 200

    except Exception as e:
        print(f"Error in weekly graph generation: {str(e)}")
        return jsonify({"error": str(e)}), 500
    finally:
        if 'conn' in locals():
            conn.close()
        plt.close('all')


@app.route('/check-location', methods=['POST'])
def check_location() -> Tuple[Dict[str, Any], int]:
    MAX_TIME_BETWEEN_UPDATES = 600  

    # Input validation
    data = request.get_json()
    if not data:
        return {"error": "Request must be JSON"}, 400

    required_fields = ['user_id', 'gps_accuracy']
    if not all(field in data for field in required_fields):
        return {"error": f"Missing required fields: {required_fields}"}, 400

    # Set defaults
    is_connected_to_wifi = data.get('is_connected_to_wifi', False)
    weather = data.get('weather', 'Unknown')
    temperature = data.get('temperature')
    uv = data.get('uv')
    sunrise = data.get('sunrise')
    sunset = data.get('sunset')
    gps_accuracy = round(float(data['gps_accuracy']), 2)

    try:
        # Daytime check
        if sunrise and sunset and not is_daytime(sunrise, sunset):
            return {"message": "Data collection paused during nighttime"}, 200

        # Determine outdoor status
        current_datetime = datetime.now()
        current_date = current_datetime.date()
        is_outside = gps_accuracy <= GPS_ACCURACY_THRESHOLD and not is_connected_to_wifi

        # Get previous record
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT time, "outside?", time_outside, total_time_outside, total_time_outside_for_given_day 
            FROM final_table 
            WHERE user_id = %s 
            ORDER BY time DESC 
            LIMIT 1
            """,
            (data['user_id'],)
        )
        last_record = cur.fetchone()

        # Initialize time variables
        time_outside = 0
        total_time_outside = last_record[3] if last_record else 0
        
        # Check if it's a new day
        if last_record:
            last_date = last_record[0].date()
            if current_date > last_date:
                # New day 
                total_time_outside_for_given_day = 0
            else:
                # Same day 
                total_time_outside_for_given_day = last_record[4] if last_record else 0
        else:
            # No previous records 
            total_time_outside_for_given_day = 0

        # Time calculation logic
        if is_outside and last_record and last_record[1]:  # Still outside
            time_since_last = (current_datetime - last_record[0]).total_seconds()
            incremental_time = min(time_since_last, MAX_TIME_BETWEEN_UPDATES)
            time_outside = last_record[2] + incremental_time
            total_time_outside = last_record[3] + incremental_time
            total_time_outside_for_given_day += incremental_time

        elif not is_outside and last_record and last_record[1]:  # Transition to inside
            time_outside = min((current_datetime - last_record[0]).total_seconds(), MAX_TIME_BETWEEN_UPDATES)
            total_time_outside = last_record[3] + time_outside
            total_time_outside_for_given_day += time_outside

        # Sunset transition handling
        if sunset and is_outside:
            sunset_time = datetime.strptime(sunset, "%H:%M").time()
            if current_datetime.time() > sunset_time:
                is_outside = False
                time_outside = min((datetime.combine(current_datetime.date(), sunset_time) - last_record[0]).total_seconds(),
                                 MAX_TIME_BETWEEN_UPDATES)

        # Calculate available daylight hours
        total_available_hours = calculate_available_hours(sunrise, sunset) if sunrise and sunset else 0

        cur.execute(
            """
            INSERT INTO final_table (
                user_id, time, "outside?", 
                time_outside, total_time_outside, total_time_outside_for_given_day,
                total_available_hours, weather, temperature, uv, gps_accuracy
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                data['user_id'], current_datetime, is_outside,
                time_outside, total_time_outside, total_time_outside_for_given_day,
                total_available_hours, weather, temperature, uv, gps_accuracy
            )
        )
        conn.commit()

        return {
            "is_outside": is_outside,
            "gps_accuracy": gps_accuracy,
            "time_outside": time_outside,
            "total_time_outside": total_time_outside,
            "total_time_outside_for_given_day": total_time_outside_for_given_day,
            "weather": weather,
            "temperature": temperature,
            "uv": uv
        }, 200

    except Exception as e:
        return {"error": str(e)}, 500
    finally:
        if 'conn' in locals():
            conn.close()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)


# python -m flask run --host=0.0.0.0

# curl -X POST http://192.168.68.103:5000/check-location -H "Content-Type: application/json" -d "{\"user_id\": \"user123\", \"gps_accuracy\": 20, \"is_connected_to_wifi\": false, \"weather\": \"Sunny\"}"
