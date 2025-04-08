from flask import Flask, request, jsonify
from matplotlib.patches import Arc
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from io import BytesIO
import base64
from datetime import datetime, time, timedelta, timezone
import psycopg2
from typing import Dict, Any, Tuple, List, Optional
from matplotlib import patheffects

# Initialize Flask app
app = Flask(__name__)

GPS_ACCURACY_THRESHOLD = 18
MAX_TIME_BETWEEN_UPDATES = 600  # 10 minutes in seconds

# Database configuration
DB_CONFIG = {
    "host": "solasdb.cv868wmkkyqh.eu-north-1.rds.amazonaws.com",
    "database": "Solasdb",
    "user": "wyvern42",
    "password": "FullMetal42"
}

def get_db_connection():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.cursor().execute("SET TIME ZONE 'UTC';")
    return conn

def parse_device_time(device_time_str: str) -> datetime:
    """Parse device time with timezone information"""
    try:
        # First try parsing with timezone info
        dt = datetime.fromisoformat(device_time_str.replace(' ', 'T'))
        if dt.tzinfo is None:
            # If no timezone info, assume local timezone
            return dt.replace(tzinfo=timezone.utc).astimezone()
        return dt.astimezone(timezone.utc)  # Convert to UTC for storage
    except ValueError:
        try:
            # Fallback for older formats
            return datetime.strptime(device_time_str, "%Y-%m-%d %H:%M:%S%z").astimezone(timezone.utc)
        except ValueError:
            return datetime.strptime(device_time_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)

def is_daytime(sunrise: str, sunset: str, device_time: datetime) -> bool:
    """Check if current time is between sunrise and sunset using device time"""
    try:
        # Convert device_time to local time for comparison
        local_time = device_time.astimezone()
        current_time = local_time.time()
        
        # Parse sunrise/sunset times (assuming they're in local time)
        sunrise_time = datetime.strptime(sunrise, "%H:%M").time()
        sunset_time = datetime.strptime(sunset, "%H:%M").time()
        
        return sunrise_time <= current_time <= sunset_time
    except ValueError as e:
        print(f"Error parsing sunrise/sunset times: {e}")
        return False

def calculate_available_hours(sunrise: str, sunset: str, device_date: datetime) -> float:
    """Calculate daylight hours using device date"""
    try:
        # Convert device_date to local date
        local_date = device_date.astimezone().date()
        
        sunrise_time = datetime.strptime(sunrise, "%H:%M").time()
        sunset_time = datetime.strptime(sunset, "%H:%M").time()
        
        daylight_duration = (datetime.combine(local_date, sunset_time) - 
                          datetime.combine(local_date, sunrise_time))
        return round(daylight_duration.total_seconds() / 3600, 2)
    except ValueError as e:
        print(f"Error calculating available hours: {e}")
        return 0.0

def format_time(total_seconds: int) -> str:
    """Convert total seconds into hrs:mins:secs format."""
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(hours)}:{int(minutes):02d}:{int(seconds):02d}"

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
             data['correct_result'], round(data['gps_accuracy'], 2)))
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
        # Validate and parse request data
        data = request.get_json()
        if not data or 'user_id' not in data or 'device_time' not in data:
            return jsonify({"error": "user_id and device_time are required"}), 400
        
        try:
            device_time = datetime.fromisoformat(data['device_time'].replace('Z', '+00:00'))
            device_tz = device_time.astimezone().tzinfo
            today = device_time.date()
        except ValueError as e:
            return jsonify({"error": f"Invalid device_time format: {str(e)}"}), 400

        if 'sunrise' not in data or 'sunset' not in data:
            return jsonify({"error": "sunrise and sunset times are required"}), 400

        # Database operations
        conn = get_db_connection()
        cur = conn.cursor()
        
        try:
            # Get all records for today (treating database timestamps as UTC)
            cur.execute(
                """SELECT time, total_time_outside_for_given_day, "outside?" 
                   FROM final_table
                   WHERE user_id = %s AND DATE(time) = %s
                   ORDER BY time ASC""",
                (data['user_id'], today)
            )
            time_series = cur.fetchall()
        except Exception as e:
            return jsonify({"error": f"Database error: {str(e)}"}), 500

        # Process time series data
        outdoor_periods = []
        current_out_start = None
        prev_status = False
        total_time_seconds = 0
        has_data = bool(time_series)

        if has_data:
            for record_time, total_outside, is_outside in time_series:
                # Convert DB timestamp (UTC) to device's local timezone
                utc_time = record_time.replace(tzinfo=timezone.utc)
                local_time = utc_time.astimezone(device_tz)
                
                # Track outdoor periods
                if not prev_status and is_outside:
                    current_out_start = local_time
                elif prev_status and not is_outside and current_out_start:
                    outdoor_periods.append((current_out_start.time(), local_time.time()))
                    current_out_start = None
                prev_status = is_outside

            # Handle final segment if still outside
            if current_out_start:
                outdoor_periods.append((current_out_start.time(), device_time.time()))
            
            total_time_seconds = time_series[-1][1]

        # Parse sunrise/sunset times
        try:
            sunrise_time = datetime.strptime(data['sunrise'], "%H:%M").time()
            sunset_time = datetime.strptime(data['sunset'], "%H:%M").time()
        except ValueError:
            return jsonify({"error": "Invalid time format for sunrise/sunset (expected HH:MM)"}), 400

        # Visualization setup
        plt.style.use('dark_background')
        fig, ax = plt.subplots(figsize=(20, 16), facecolor='#1a1a1a')
        fig.patch.set_edgecolor('#FFA500')
        fig.patch.set_linewidth(5)

        radius = 25
        center = (0, 0)
        arc_width = 100

        # Calculate daylight duration and angle conversion
        daylight_start = datetime.combine(today, sunrise_time)
        daylight_end = datetime.combine(today, sunset_time)
        daylight_duration = (daylight_end - daylight_start).total_seconds()

        def time_to_angle(t: time) -> float:
            """Convert time to angle (0-180 degrees) within daylight period"""
            t_dt = datetime.combine(today, t)
            if t_dt <= daylight_start: return 0
            if t_dt >= daylight_end: return 180
            seconds = (t_dt - daylight_start).total_seconds()
            return 180 * (seconds / daylight_duration)

        # Draw daylight arc (background)
        ax.set_xlim(radius+7, -radius-7)
        daylight_arc = Arc(center, 2*radius, 2*radius, angle=0,
                         theta1=0, theta2=180, color='#3a3a3a', lw=arc_width)
        ax.add_patch(daylight_arc)

        # Draw outdoor periods (only during daylight)
        for start, end in outdoor_periods:
            start_clipped = max(start, sunrise_time)
            end_clipped = min(end, sunset_time)
            if start_clipped >= end_clipped: continue
                
            start_angle = time_to_angle(start_clipped)
            end_angle = time_to_angle(end_clipped)
            
            outdoor_arc = Arc(center, 2*radius, 2*radius, angle=0,
                            theta1=start_angle, theta2=end_angle,
                            color='#FFA500', lw=arc_width)
            ax.add_patch(outdoor_arc)

        # Add hour markers
        current_marker = daylight_start.replace(minute=0, second=0, microsecond=0)
        if current_marker < daylight_start:
            current_marker += timedelta(hours=1)
        
        marker_length = 2.5
        while current_marker <= daylight_end:
            marker_time = current_marker.time()
            angle = time_to_angle(marker_time)
            rad_angle = np.radians(angle)
            
            # Marker line
            x_outer = radius * np.cos(rad_angle)
            y_outer = radius * np.sin(rad_angle)
            x_inner = (radius - marker_length) * np.cos(rad_angle)
            y_inner = (radius - marker_length) * np.sin(rad_angle)
            ax.plot([x_outer, x_inner], [y_outer, y_inner], 
                   color='white', linewidth=2, alpha=0.7)
            
            # Label every 2 hours
            if marker_time.hour % 2 == 0:
                label_radius = radius - marker_length - 1.5
                ax.text(label_radius * np.cos(rad_angle),
                       label_radius * np.sin(rad_angle),
                       f"{marker_time.hour}:00",
                       color='white', ha='center', va='center',
                       fontsize=14, alpha=0.8)
            
            current_marker += timedelta(hours=1)

        # Add current time indicator
        current_angle = time_to_angle(device_time.time())
        current_rad = np.radians(current_angle)
        ax.plot(radius * np.cos(current_rad), radius * np.sin(current_rad),
               'o', color='white', markersize=8, alpha=0.7)

        # Add labels and text
        ax.text(radius+2.8, -1, data['sunrise'],
               color='white', ha='left', va='center', 
               fontsize=28, fontweight='bold')
        ax.text(-radius-2.8, -1, data['sunset'],
               color='white', ha='right', va='center',
               fontsize=28, fontweight='bold')

        ax.text(0, 8, "RECOMMENDED EXPOSURE\n45 MINUTES", 
               color='white', ha='center', va='center',
               fontsize=30, fontweight='bold', alpha=0.9,
               linespacing=1.5)

        ax.text(0, 0, format_time(total_time_seconds), 
               color='#FFA500', ha='center', va='center',
               fontsize=60, fontweight='bold',
               bbox=dict(facecolor='#1a1a1a88', edgecolor='#FFA500',
                        boxstyle='round,pad=0.8', linewidth=5))

        ax.set_ylim(-2, radius+3)
        ax.axis('off')
        ax.set_aspect('equal')
        plt.title('Daylight Exposure', color='#FFA500', pad=20, 
                 fontsize=44, fontweight='bold', y=1.05)

        # Save and return image
        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=250, bbox_inches='tight',
                   facecolor=fig.get_facecolor(), edgecolor=fig.get_edgecolor())
        plt.close(fig)
        buf.seek(0)
        
        return jsonify({
            "image": base64.b64encode(buf.read()).decode('utf-8'),
            "total_time_outside": format_time(total_time_seconds),
            "sunrise": data['sunrise'],
            "sunset": data['sunset'],
            "outdoor_periods": [{"start": str(s), "end": str(e)} for s,e in outdoor_periods],
            "timezone": str(device_tz),
            "current_time": device_time.astimezone(device_tz).isoformat(),
            "data_available": has_data,
            "message": "Visualization generated" if has_data else "No data yet today"
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
        local_device_time = device_time.astimezone()
        today = local_device_time.date()
        user_id = data['user_id']
        conn = get_db_connection()
        cur = conn.cursor()

        # Get the past 7 days including today
        start_date = today - timedelta(days=6)
        
        cur.execute(
            """
            WITH ranked_entries AS (
                SELECT 
                    DATE(time AT TIME ZONE 'UTC') as date,
                    total_time_outside_for_given_day as time_seconds,
                    ROW_NUMBER() OVER (PARTITION BY DATE(time AT TIME ZONE 'UTC') ORDER BY time DESC) as row_num
                FROM final_table
                WHERE user_id = %s AND DATE(time AT TIME ZONE 'UTC') BETWEEN %s AND %s
            )
            SELECT date, time_seconds
            FROM ranked_entries
            WHERE row_num = 1
            ORDER BY date ASC
            """,
            (user_id, start_date, today)
        )
        results = cur.fetchall()

        # Create day labels in "Day MM/DD" format
        days = []
        minutes = []
        day_names = []
        
        existing_data = {record[0]: record[1] for record in results}
        
        for day_offset in range(6, -1, -1):
            current_date = today - timedelta(days=day_offset)
            day_name = current_date.strftime('%a %m/%d')
            day_names.append(day_name)
            time_seconds = existing_data.get(current_date, 0)
            minutes.append(time_seconds / 60)

        # Create the horizontal bar plot
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
            edgecolor='#FFA500',
            linewidth=1.5,
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
        
        # Set x-axis limit with some padding
        x_max = max(max(minutes) * 1.2, 60)  # Ensure at least 60 mins is shown
        ax.set_xlim(0, x_max)
        
        ax.tick_params(axis='y', colors='#FFA500', labelsize=12, pad=5)
        ax.tick_params(axis='x', colors='#FFA500', labelsize=11)
        
        ax.grid(color='#FFA50033', linestyle='--', linewidth=0.8, alpha=0.5, zorder=1, axis='x')
        ax.axvline(0, color='#FFA500', linestyle='-', linewidth=1.5, zorder=2)
        
        # Add goal line at 45 minutes (using theme color)
        goal_minutes = 45
        ax.axvline(goal_minutes, color='#FFA500', linestyle=':', linewidth=2.5, alpha=0.7, zorder=3)
        ax.text(goal_minutes + 2, len(day_names) - 0.5, 
                'Daily Goal: 45 mins', 
                color='#FFA500', fontsize=11, va='center')
        
        for spine in ax.spines.values():
            spine.set_visible(False)
        
        # Add labels just outside the bars at the end
        for bar in bars:
            width = bar.get_width()
            # Position label just past the end of the bar
            label_x = width + (x_max * 0.02)  # Small offset from bar end
            ax.text(label_x, bar.get_y() + bar.get_height()/2,
                   f'{int(width)} min',
                   ha='left', va='center',
                   color='#FFA500', fontsize=11, weight='bold')
            
            # Add check mark if goal is reached (inside the bar)
            if width >= goal_minutes:
                check_x = min(width, goal_minutes - 5)  # Position check mark before goal line
                ax.text(check_x, bar.get_y() + bar.get_height()/2,
                       '✓', 
                       ha='center', va='center',
                       color='#FFFFFF', fontsize=14, weight='bold')

        plt.tight_layout(pad=2)

        # Save to buffer
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
    data = request.get_json()
    if not data:
        return {"error": "Request must be JSON"}, 400

    required_fields = ['user_id', 'gps_accuracy', 'device_time']
    if not all(field in data for field in required_fields):
        return {"error": f"Missing required fields: {required_fields}"}, 400

    try:
        device_time = parse_device_time(data['device_time'])
        local_device_time = device_time.astimezone()
        current_date = local_device_time.date()

        is_connected_to_wifi = data.get('is_connected_to_wifi', False)
        weather = data.get('weather', 'Unknown')
        temperature = data.get('temperature')
        uv = data.get('uv')
        sunrise = data.get('sunrise')
        sunset = data.get('sunset')
        gps_accuracy = round(float(data['gps_accuracy']), 2)

        # Daytime check using device time
        if sunrise and sunset and not is_daytime(sunrise, sunset, device_time):
            return {"message": "Data collection paused during nighttime"}, 200

        is_outside = gps_accuracy <= GPS_ACCURACY_THRESHOLD and not is_connected_to_wifi

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

        time_outside = 0
        total_time_outside = last_record[3] if last_record else 0
        total_time_outside_for_given_day = last_record[4] if last_record else 0
        incremental_time = 0

        if last_record:
            last_record_time = last_record[0].astimezone()
            time_since_last = (local_device_time - last_record_time).total_seconds()
            incremental_time = min(time_since_last, MAX_TIME_BETWEEN_UPDATES)
            
            last_date = last_record_time.date()
            if current_date > last_date:
                total_time_outside_for_given_day = 0

            if last_record[1]:
                if is_outside:
                    time_outside = last_record[2] + incremental_time
                    total_time_outside += incremental_time
                    total_time_outside_for_given_day += incremental_time
                else:
                    transition_time = min(time_since_last, MAX_TIME_BETWEEN_UPDATES)
                    time_outside = 0
                    total_time_outside += transition_time
                    total_time_outside_for_given_day += transition_time
            else:
                if is_outside:
                    time_outside = incremental_time
                    total_time_outside += incremental_time
                    total_time_outside_for_given_day += incremental_time
        else:
            if is_outside:
                time_outside = incremental_time
                total_time_outside = incremental_time
                total_time_outside_for_given_day = incremental_time

        # Sunset transition handling
        if sunset and is_outside:
            try:
                sunset_time = datetime.strptime(sunset, "%H:%M").time()
                sunset_datetime = datetime.combine(current_date, sunset_time).astimezone()
                if local_device_time > sunset_datetime:
                    is_outside = False
                    if last_record and last_record[1]:
                        transition_time = min((sunset_datetime - last_record_time).total_seconds(),
                                            MAX_TIME_BETWEEN_UPDATES)
                        time_outside = 0
                        total_time_outside += transition_time
                        total_time_outside_for_given_day += transition_time
            except ValueError as e:
                print(f"Error parsing sunset time: {e}")

        total_available_hours = calculate_available_hours(sunrise, sunset, device_time) if sunrise and sunset else 0

        cur.execute(
            """
            INSERT INTO final_table (
                user_id, time, "outside?", 
                time_outside, total_time_outside, total_time_outside_for_given_day,
                total_available_hours, weather, temperature, uv, gps_accuracy
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                data['user_id'], device_time, is_outside,
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