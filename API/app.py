from flask import Flask, request, jsonify
from matplotlib.patches import Arc
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from io import BytesIO
import base64
from datetime import datetime, time, timedelta, date
import psycopg2
from typing import Dict, Any, Tuple, List, Optional
from matplotlib import patheffects


app = Flask(__name__)

GPS_ACCURACY_THRESHOLD = 18

# Database configuration
DB_CONFIG = {
    "host": "solasdb.cv868wmkkyqh.eu-north-1.rds.amazonaws.com",
    "database": "Solasdb",
    "user": "wyvern42",
    "password": "FullMetal42"
}

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

def parse_device_time(device_time_str: str) -> datetime:
    """Parse device time string in DD-MM-YYYY HH:MM:SS format as Dublin time (no timezone)"""
    try:
        return datetime.strptime(device_time_str, "%d-%m-%Y %H:%M:%S")
    except ValueError as e:
        raise ValueError(f"Invalid device_time format: {str(e)}")

def format_time(total_seconds: int) -> str:
    """Convert total seconds into hrs:mins:secs format."""
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(hours)}:{int(minutes):02d}:{int(seconds):02d}"

def calculate_time_outside(user_id: str, current_date: date) -> int:
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        start_of_day = datetime.combine(current_date, time(0, 0))
        end_of_day = datetime.combine(current_date, time(23, 59, 59))
        
        cur.execute(
            """
            SELECT time FROM final_table
            WHERE user_id = %s AND "outside?" = TRUE
            AND time > COALESCE(
                (SELECT time FROM final_table
                 WHERE user_id = %s AND "outside?" = FALSE
                 AND time BETWEEN %s AND %s
                 ORDER BY time DESC
                 LIMIT 1),
                '1970-01-01'::timestamp
            )
            AND time BETWEEN %s AND %s
            ORDER BY time ASC
            """,
            (user_id, user_id, start_of_day, end_of_day, start_of_day, end_of_day)
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

def is_daytime(sunrise: str, sunset: str, current_time: datetime) -> bool:
    try:
        current_local_time = current_time.time()
        sunrise_time = datetime.strptime(sunrise, "%H:%M").time()
        sunset_time = datetime.strptime(sunset, "%H:%M").time()
        return sunrise_time <= current_local_time <= sunset_time
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

    required_fields = ['user_id', 'correct_result', 'gps_accuracy', 'device_time']
    if not all(field in data for field in required_fields):
        return {"error": f"Missing required fields: {required_fields}"}, 400

    try:
        device_time = parse_device_time(data['device_time'])
        
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO app_accuracy (user_id, time, correct_result, gps_accuracy)
            VALUES (%s, %s, %s, %s)
            """,
            (data['user_id'], device_time, 
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
        if not data or 'user_id' not in data or 'device_time' not in data:
            return jsonify({"error": "user_id and device_time are required"}), 400

        device_time = parse_device_time(data['device_time'])
        user_id = data['user_id']
        today = device_time.date()
        
        start_of_day = datetime.combine(today, time(0, 0))
        end_of_day = datetime.combine(today, time(23, 59, 59))
        
        conn = get_db_connection()
        cur = conn.cursor()

        if 'sunrise' not in data or 'sunset' not in data:
            return jsonify({"error": "sunrise and sunset times are required"}), 400

        sunrise_str = data['sunrise']
        sunset_str = data['sunset']

        cur.execute(
            """SELECT time, total_time_outside_for_given_day, "outside?" 
               FROM final_table
               WHERE user_id = %s AND time BETWEEN %s AND %s
               ORDER BY time ASC""",
            (user_id, start_of_day, end_of_day)
        )
        time_series = cur.fetchall()

        # Initialize with default values (no data)
        outdoor_periods = []
        total_time_seconds = 0
        has_data = bool(time_series)

        if has_data:
            outdoor_periods = []
            current_out_start = None
            prev_status = False
            total_time_seconds = time_series[-1][1] if time_series else 0

            for record in time_series:
                record_time = record[0]
                is_outside = record[2]
                
                if not prev_status and is_outside:
                    current_out_start = record_time
                elif prev_status and not is_outside and current_out_start:
                    outdoor_periods.append((current_out_start.time(), record_time.time()))
                    current_out_start = None
                prev_status = is_outside

            if current_out_start is not None:
                outdoor_periods.append((current_out_start.time(), device_time.time()))

        try:
            sunrise_time = datetime.strptime(sunrise_str, "%H:%M").time()
            sunset_time = datetime.strptime(sunset_str, "%H:%M").time()
        except ValueError:
            return jsonify({"error": "Invalid time format (expected HH:MM)"}), 400

        plt.style.use('dark_background')
        fig, ax = plt.subplots(figsize=(20, 16), facecolor='#1a1a1a')
        fig.patch.set_edgecolor('#FFA500')
        fig.patch.set_linewidth(5)

        radius = 25
        center = (0, 0)
        arc_width = 100

        daylight_duration = (datetime.combine(today, sunset_time) - 
                          datetime.combine(today, sunrise_time)).total_seconds()
        
        def time_to_daylight_angle(t: time) -> float:
            if t <= sunrise_time: return 0
            if t >= sunset_time: return 180
            seconds = (datetime.combine(today, t) - 
                     datetime.combine(today, sunrise_time)).total_seconds()
            return 180 * (seconds / daylight_duration)

        ax.set_xlim(radius+7, -radius-7)

        # Base daylight arc (gray)
        daylight_arc = Arc(center, 2*radius, 2*radius, angle=0,
                         theta1=0, theta2=180, color='#3a3a3a', lw=arc_width)
        ax.add_patch(daylight_arc)
        
        # Outdoor periods (orange) - will be empty if no data
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

        # Hour markers
        sunrise_dt = datetime.combine(today, sunrise_time)
        sunset_dt = datetime.combine(today, sunset_time)
        hour_markers = []
        current_marker = sunrise_dt.replace(minute=0, second=0, microsecond=0)
        
        if current_marker < sunrise_dt:
            current_marker += timedelta(hours=1)
        
        while current_marker <= sunset_dt:
            hour_markers.append(current_marker.time())
            current_marker += timedelta(hours=1)
        
        marker_length = 2.5
        for marker_time in hour_markers:
            angle = time_to_daylight_angle(marker_time)
            rad_angle = np.radians(angle)
            
            x_outer = radius * np.cos(rad_angle)
            y_outer = radius * np.sin(rad_angle)
            
            x_inner = (radius - marker_length) * np.cos(rad_angle)
            y_inner = (radius - marker_length) * np.sin(rad_angle)
            
            ax.plot([x_outer, x_inner], [y_outer, y_inner], 
                   color='white', linewidth=2, alpha=0.7)
            
            if marker_time.hour % 2 == 0:
                label_radius = radius - marker_length - 1.5
                x_label = label_radius * np.cos(rad_angle)
                y_label = label_radius * np.sin(rad_angle)
                
                ax.text(x_label, y_label, f"{marker_time.hour}:00",
                       color='white', ha='center', va='center',
                       fontsize=14, alpha=0.8)

        # Current time indicator
        current_time = device_time.time()
        current_angle = time_to_daylight_angle(current_time)
        rad_angle = np.radians(current_angle)
        
        x_dot = radius * np.cos(rad_angle)
        y_dot = radius * np.sin(rad_angle)
        
        ax.plot(x_dot, y_dot, 'o',
               color='white',
               markersize=17,
               alpha=0.6)

        # Sunrise/sunset labels
        ax.text(radius+2.8, -1.3, sunrise_str,
               color='white', ha='left', va='center',
               fontsize=28, fontweight='bold')

        ax.text(-radius-2.8, -1.3, sunset_str,
               color='white', ha='right', va='center',
               fontsize=28, fontweight='bold')

        # Time display
        formatted_time = format_time(total_time_seconds)
        
        ax.text(0, 8, "RECOMMENDED EXPOSURE\n45 MINUTES", 
               color='white', ha='center', va='center',
               fontsize=30, fontweight='bold', alpha=0.9,
               linespacing=1.5)

        ax.text(0, 0, formatted_time, 
               color='#FFA500', ha='center', va='center',
               fontsize=60, fontweight='bold',
               bbox=dict(facecolor='#1a1a1a88', edgecolor='#FFA500',
                        boxstyle='round,pad=0.8', linewidth=5))

        ax.set_ylim(-2, radius+3)
        ax.axis('off')
        ax.set_aspect('equal')
        
        plt.title('Daylight Exposure', color='#FFA500', pad=20, 
                 fontsize=44, fontweight='bold', y=1.05)
        
        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=250, bbox_inches='tight',
                   facecolor=fig.get_facecolor(), edgecolor=fig.get_edgecolor())
        plt.close(fig)
        buf.seek(0)
        
        return jsonify({
            "image": base64.b64encode(buf.read()).decode('utf-8'),
            "total_time_outside": formatted_time,
            "sunrise": sunrise_str,
            "sunset": sunset_str,
            "outdoor_periods": [
                {"start": str(start), "end": str(end)} 
                for start, end in outdoor_periods
            ],
            "hour_markers": [str(m) for m in hour_markers],
            "current_time": str(current_time),
            "data_available": has_data  # Indicates whether real data exists
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
        if not data or 'user_id' not in data or 'device_time' not in data:
            return jsonify({"error": "user_id and device_time are required"}), 400

        device_time = parse_device_time(data['device_time'])
        today = device_time.date()
        user_id = data['user_id']
        conn = get_db_connection()
        cur = conn.cursor()

        start_date = today - timedelta(days=6)
        
        start_datetime = datetime.combine(start_date, time(0, 0))
        end_datetime = datetime.combine(today, time(23, 59, 59))
        
        cur.execute(
            """
            WITH ranked_entries AS (
                SELECT 
                    time::date as date,
                    total_time_outside_for_given_day as time_seconds,
                    ROW_NUMBER() OVER (PARTITION BY time::date 
                                      ORDER BY time DESC) as row_num
                FROM final_table
                WHERE user_id = %s 
                AND time BETWEEN %s AND %s
            )
            SELECT date, time_seconds
            FROM ranked_entries
            WHERE row_num = 1
            ORDER BY date DESC  
            """,
            (user_id, start_datetime, end_datetime)
        )
        results = cur.fetchall()

        days = []
        minutes = []
        day_names = []
        
        existing_data = {record[0]: record[1] for record in results}
        
        for day_offset in range(6, -1, -1):
            current_date = today - timedelta(days=day_offset)
            day_name = current_date.strftime('%a %d-%m')
            day_names.append(day_name)
            time_seconds = existing_data.get(current_date, 0)
            minutes.append(time_seconds / 60)

        plt.style.use('dark_background')
        fig = plt.figure(figsize=(10, 6), facecolor='#1a1a1a')
        fig.patch.set_edgecolor('#FFA500')
        fig.patch.set_linewidth(2)
        
        ax = fig.add_subplot(111, facecolor='#2a2a2a')
        
        bars = ax.barh(
            day_names,
            minutes, 
            height=0.7, 
            color='#FFA500', 
            alpha=0.9,
            zorder=2
        )
        
        ax.set_title('Weekly Time Spent Outside (Minutes)', 
                    color='#FFA500', 
                    pad=15, 
                    fontsize=16, 
                    fontweight='bold')
        
        ax.set_xlabel('Minutes Outside', 
                     color='#FFA500', 
                     fontsize=12, 
                     labelpad=10)
        
        x_max = max(max(minutes) * 1.2, 60)
        ax.set_xlim(0, x_max)
        
        ax.tick_params(axis='y', colors='#FFA500', labelsize=12, pad=5)
        ax.tick_params(axis='x', colors='#FFA500', labelsize=11)
        
        ax.grid(color='#FFA50033', linestyle='--', linewidth=0.8, alpha=0.5, zorder=1, axis='x')
        ax.axvline(0, color='#FFA500', linestyle='-', linewidth=1.5, zorder=2)
        
        goal_minutes = 45
        ax.axvline(goal_minutes, color='#FFA500', linestyle=':', linewidth=2.5, alpha=0.7, zorder=3)
        ax.text(goal_minutes + 2, len(day_names) - 0.5, 
                'Daily Goal: 45 mins', 
                color='#FFA500', fontsize=11, va='center')
        
        for spine in ax.spines.values():
            spine.set_visible(False)
        
        for bar in bars:
            width = bar.get_width()
            label_x = width + (x_max * 0.02)
            ax.text(label_x, bar.get_y() + bar.get_height()/2,
                   f'{int(width)} min',
                   ha='left', va='center',
                   color='#FFA500', fontsize=11, weight='bold')
            
            if width >= goal_minutes:
                # Position checkmark at 95% of the bar width (inside the bar)
                check_x = width * 0.95
                ax.text(check_x, bar.get_y() + bar.get_height()/2,
                       '✓', 
                       ha='center', va='center',
                       color='#FFFFFF', fontsize=14, weight='bold')

        plt.tight_layout(pad=2)

        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=120, bbox_inches='tight', 
                   facecolor=fig.get_facecolor(), edgecolor=fig.get_edgecolor())
        plt.close(fig)
        buf.seek(0)
        
        return jsonify({
            "image": base64.b64encode(buf.read()).decode('utf-8'),
            "days": day_names,
            "minutes": minutes,
            "seconds": [m * 60 for m in minutes]
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
    MAX_TIME_BETWEEN_UPDATES = 600  # 10 minutes in seconds

    data = request.get_json()
    if not data:
        return {"error": "Request must be JSON"}, 400

    required_fields = ['user_id', 'gps_accuracy', 'device_time']
    if not all(field in data for field in required_fields):
        return {"error": f"Missing required fields: {required_fields}"}, 400

    try:
        device_time = parse_device_time(data['device_time'])
        current_datetime = device_time
        current_date = current_datetime.date()

        is_connected_to_wifi = data.get('is_connected_to_wifi', False)
        weather = data.get('weather', 'Unknown')
        temperature = data.get('temperature')
        uv = data.get('uv')
        sunrise = data.get('sunrise')
        sunset = data.get('sunset')
        gps_accuracy = round(float(data['gps_accuracy']), 2)

        if sunrise and sunset and not is_daytime(sunrise, sunset, current_datetime):
            return {"message": "Data collection paused during nighttime"}, 200

        is_outside = gps_accuracy <= GPS_ACCURACY_THRESHOLD and not is_connected_to_wifi

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT time, "outside?", 
                   time_outside, total_time_outside, total_time_outside_for_given_day 
            FROM final_table 
            WHERE user_id = %s 
            ORDER BY time DESC 
            LIMIT 1
            """,
            (data['user_id'],)
        )
        last_record = cur.fetchone()

        # Initialize all time variables
        time_outside = 0
        total_time_outside = last_record[3] if last_record else 0  # Use total_time_outside from last record
        total_time_outside_for_given_day = last_record[4] if last_record else 0  # Use total_time_outside_for_given_day from last record
        incremental_time = 0

        if last_record:
            last_record_time = last_record[0]
            last_record_date = last_record_time.date()
            time_since_last = (current_datetime - last_record_time).total_seconds()
            incremental_time = min(time_since_last, MAX_TIME_BETWEEN_UPDATES)
            
            # Reset daily total if it's a new day
            if current_date > last_record_date:
                total_time_outside_for_given_day = 0

            # Handle state transitions
            if last_record[1]:  # If was outside
                if is_outside:  # Still outside
                    time_outside = last_record[2] + incremental_time
                    total_time_outside += incremental_time
                    total_time_outside_for_given_day += incremental_time
                else:  # Transition from outside to inside
                    time_outside = 0  # Reset time_outside counter
                    # Only add the actual time spent outside before transition
                    transition_time = min(time_since_last, MAX_TIME_BETWEEN_UPDATES)
                    total_time_outside += transition_time
                    total_time_outside_for_given_day += transition_time
            else:  # If was inside
                if is_outside:  # Transition from inside to outside
                    time_outside = incremental_time  # Start counting time_outside
                    total_time_outside += incremental_time
                    total_time_outside_for_given_day += incremental_time
                else:  # Still inside
                    # No change to any counters
                    pass
        else:  # First record
            if is_outside:
                time_outside = incremental_time
                total_time_outside = incremental_time
                total_time_outside_for_given_day = incremental_time

        # Handle sunset transition if outside
        if sunset and is_outside:
            try:
                sunset_time = datetime.strptime(sunset, "%H:%M").time()
                if current_datetime.time() > sunset_time:
                    is_outside = False
                    if last_record and last_record[1]:  # Was outside before sunset
                        sunset_datetime = datetime.combine(current_date, sunset_time)
                        transition_time = min((sunset_datetime - last_record_time).total_seconds(),
                                            MAX_TIME_BETWEEN_UPDATES)
                        time_outside = 0  # Reset time_outside counter
                        total_time_outside += transition_time  # Add time until sunset
                        total_time_outside_for_given_day += transition_time
            except ValueError as e:
                print(f"Error parsing sunset time: {e}")

        total_available_hours = calculate_available_hours(sunrise, sunset) if sunrise and sunset else 0

        print(f"""
        Status Update:
        - Current Time: {current_datetime.strftime('%d-%m-%Y %H:%M:%S')}
        - Previous State: {'Outside' if last_record and last_record[1] else 'Inside' if last_record else 'First Record'}
        - New State: {'Outside' if is_outside else 'Inside'}
        - Time Outside: {time_outside} seconds (current session)
        - Total Time Outside: {total_time_outside} seconds (lifetime)
        - Total Today: {total_time_outside_for_given_day} seconds
        - GPS Accuracy: {gps_accuracy}
        - WiFi Connected: {is_connected_to_wifi}
        """)

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
        print(f"Error in check_location: {str(e)}")
        return {"error": str(e)}, 500
    finally:
        if 'conn' in locals():
            conn.close()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)