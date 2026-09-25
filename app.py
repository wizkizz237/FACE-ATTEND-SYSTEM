from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    jsonify,
    send_from_directory,
    send_file,
    has_request_context
)

from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
from dotenv import load_dotenv

import mysql.connector
import os
import base64
import cv2
import numpy as np
import secrets
import hashlib
from datetime import datetime, timedelta
import smtplib
import io
import csv

from apscheduler.schedulers.background import BackgroundScheduler

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


# =========================================================
# PDF REPORT EXPORT
# =========================================================

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.units import mm


# =========================================================
# ENVIRONMENT
# =========================================================

load_dotenv()


# =========================================================
# FLASK APP
# =========================================================

app = Flask(__name__)

SECRET_KEY = os.getenv("SECRET_KEY")

if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY is missing from the .env file."
    )

app.secret_key = SECRET_KEY


# =========================================================
# PROJECT PATH
# =========================================================

PROJECT_ROOT = os.path.dirname(
    os.path.abspath(__file__)
)


# =========================================================
# FACE RECOGNITION CONFIGURATION
# =========================================================

FACE_CASCADE_PATH = os.path.join(
    PROJECT_ROOT,
    "static",
    "models",
    "haarcascade_frontalface_default.xml"
)

if not os.path.isfile(FACE_CASCADE_PATH):
    raise RuntimeError(
        "Face detector file not found:\n"
        f"{FACE_CASCADE_PATH}"
    )


face_detector = cv2.CascadeClassifier(
    FACE_CASCADE_PATH
)

if face_detector.empty():
    raise RuntimeError(
        "Unable to load OpenCV face detector."
    )


FACE_DATASET_DIR = os.path.join(
    PROJECT_ROOT,
    "face_dataset"
)


FACE_MODEL_PATH = os.path.join(
    FACE_DATASET_DIR,
    "lbph_model.yml"
)


FACE_SIZE = (200, 200)


# Lower distance = better LBPH match.
LBPH_THRESHOLD = 70.0


# Minimum enrolled images required.
MIN_FACE_IMAGES = 10


# =========================================================
# OTP CONFIGURATION
# =========================================================

OTP_EXPIRY_MINUTES = 5
OTP_MAX_ATTEMPTS = 5


# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_db_connection():

    try:

        return mysql.connector.connect(
            host=os.getenv(
                "DB_HOST",
                "localhost"
            ),
            user=os.getenv(
                "DB_USER",
                "root"
            ),
            password=os.getenv(
                "DB_PASSWORD",
                ""
            ),
            database=os.getenv(
                "DB_NAME",
                "employee_attendance"
            ),
            use_pure=True
        )

    except mysql.connector.Error as error:

        print(
            "Database connection error:",
            error
        )

        return None


# =========================================================
# ADMIN NAME HELPER
# =========================================================

# =========================================================
# AUDIT LOG HELPER
# =========================================================
def create_audit_log(action, description=None):

    connection = get_db_connection()

    if connection is None:
        print("Audit log creation failed: database connection unavailable.")
        return False

    cursor = connection.cursor()

    try:
        # Audit logs can be created both during normal HTTP requests
        # and during background/system tasks such as automatic report backfill.
        if has_request_context():
            admin_id = session.get("admin_id")
            ip_address = request.headers.get(
                "X-Forwarded-For",
                request.remote_addr
            )

            if ip_address and "," in ip_address:
                ip_address = ip_address.split(",", 1)[0].strip()
        else:
            admin_id = None
            ip_address = None

        cursor.execute("""
            INSERT INTO audit_logs
            (admin_id, action, description, ip_address)
            VALUES (%s, %s, %s, %s)
        """, (
            admin_id,
            action,
            description,
            ip_address
        ))

        connection.commit()
        return True

    except mysql.connector.Error as error:
        connection.rollback()
        print("Audit log creation error:", error)
        return False

    finally:
        cursor.close()
        connection.close()


def get_admin_name():

    return session.get(
        "admin_full_name",
        session.get(
            "admin_username",
            "Administrator"
        )
    )

# =========================================================
# CREATE NOTIFICATION
# =========================================================

def create_notification(
    title,
    message,
    notification_type="info"
):

    connection = get_db_connection()

    if connection is None:

        print(
            "Notification creation failed: "
            "database connection unavailable."
        )

        return False

    cursor = connection.cursor()

    try:

        allowed_types = {
            "info",
            "success",
            "warning",
            "error"
        }

        if notification_type not in allowed_types:
            notification_type = "info"

        cursor.execute("""
            INSERT INTO notifications
            (
                title,
                message,
                notification_type
            )
            VALUES
            (
                %s,
                %s,
                %s
            )
        """, (
            title,
            message,
            notification_type
        ))

        connection.commit()

        print(
            "Notification created:",
            title
        )

        return True

    except mysql.connector.Error as error:

        connection.rollback()

        print(
            "Notification creation error:",
            error
        )

        return False

    finally:

        cursor.close()
        connection.close()
        
# =========================================================
# AUTOMATIC DAILY ATTENDANCE REPORT GENERATOR
# =========================================================

def generate_daily_attendance_report(report_date):

    connection = get_db_connection()

    if connection is None:

        print(
            "Daily report generation failed: "
            "database connection unavailable."
        )

        return False

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        # -------------------------------------------------
        # TOTAL EMPLOYEES
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                COUNT(*) AS total
            FROM employees
        """)

        total_employees = (
            cursor.fetchone()["total"]
            or 0
        )

        # -------------------------------------------------
        # PRESENT EMPLOYEES
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                COUNT(*) AS total
            FROM attendance
            WHERE attendance_date = %s
              AND status = 'Present'
        """, (
            report_date,
        ))

        present_count = (
            cursor.fetchone()["total"]
            or 0
        )

        # -------------------------------------------------
        # LATE EMPLOYEES
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                COUNT(*) AS total
            FROM attendance
            WHERE attendance_date = %s
              AND status = 'Late'
        """, (
            report_date,
        ))

        late_count = (
            cursor.fetchone()["total"]
            or 0
        )

        # -------------------------------------------------
        # ABSENT EMPLOYEES
        # -------------------------------------------------

        absent_count = max(
            total_employees
            - present_count
            - late_count,
            0
        )

        # -------------------------------------------------
        # SAVE / UPDATE DAILY REPORT
        # -------------------------------------------------

        cursor.execute("""
            INSERT INTO daily_attendance_reports
            (
                report_date,
                total_employees,
                present_count,
                late_count,
                absent_count,
                generated_at,
                status
            )
            VALUES
            (
                %s,
                %s,
                %s,
                %s,
                %s,
                NOW(),
                'Generated'
            )

            ON DUPLICATE KEY UPDATE

                total_employees =
                    VALUES(total_employees),

                present_count =
                    VALUES(present_count),

                late_count =
                    VALUES(late_count),

                absent_count =
                    VALUES(absent_count),

                generated_at =
                    NOW(),

                status =
                    'Generated'
        """, (
            report_date,
            total_employees,
            present_count,
            late_count,
            absent_count
        ))

        connection.commit()

        create_audit_log(
            "Daily Report Generated",
            f"Daily attendance report for {report_date} was generated."
        )

        print("=" * 60)
        print("DAILY ATTENDANCE REPORT GENERATED")
        print(f"Report date: {report_date}")
        print(f"Total employees: {total_employees}")
        print(f"Present: {present_count}")
        print(f"Late: {late_count}")
        print(f"Absent: {absent_count}")
        print("=" * 60)

        create_notification(
            "Daily Report Generated",
            f"The attendance report for {report_date} was generated successfully.",
            "success"
        )

        return True

    except mysql.connector.Error as error:

        connection.rollback()

        print(
            "Daily report generation error:",
            error
        )

        return False

    finally:

        cursor.close()
        connection.close()


# =========================================================
# LOGIN REQUIRED
# =========================================================

def login_required(function):

    @wraps(function)
    def decorated_function(*args, **kwargs):

        if "admin_id" not in session:

            return redirect(
                url_for("login")
            )

        return function(
            *args,
            **kwargs
        )

    return decorated_function


# =========================================================
# FACE IMAGE PATH HELPER
# =========================================================

def get_face_image_full_path(image_path):

    if not image_path:
        return None

    normalized_path = image_path.replace(
        "\\",
        "/"
    ).lstrip("/")

    return os.path.join(
        PROJECT_ROOT,
        *normalized_path.split("/")
    )


# =========================================================
# OTP HELPERS
# =========================================================

def generate_otp():

    return f"{secrets.randbelow(1000000):06d}"


def hash_otp(otp):

    return hashlib.sha256(
        otp.encode("utf-8")
    ).hexdigest()


def mask_email(email):

    if not email or "@" not in email:
        return email

    local_part, domain = email.split(
        "@",
        1
    )

    if len(local_part) <= 2:

        masked_local = (
            "*" * len(local_part)
        )

    else:

        masked_local = (
            local_part[0]
            + ("*" * (len(local_part) - 2))
            + local_part[-1]
        )

    return (
        f"{masked_local}@{domain}"
    )


def send_otp_email(
    recipient_email,
    employee_name,
    otp
):

    smtp_host = os.getenv(
        "SMTP_HOST",
        "smtp.gmail.com"
    )

    try:

        smtp_port = int(
            os.getenv(
                "SMTP_PORT",
                "587"
            )
        )

    except ValueError:

        smtp_port = 587

    smtp_username = os.getenv(
        "SMTP_USERNAME",
        ""
    )

    smtp_password = os.getenv(
        "SMTP_PASSWORD",
        ""
    )

    smtp_from = os.getenv(
        "SMTP_FROM",
        smtp_username
    )

    if not smtp_username:

        print(
            "SMTP_USERNAME is not configured."
        )

        return False

    if not smtp_password:

        print(
            "SMTP_PASSWORD is not configured."
        )

        return False

    if not recipient_email:

        print(
            "Recipient email is missing."
        )

        return False

    subject = (
        "FaceAttend Attendance Verification Code"
    )

    message_body = f"""
Hello {employee_name},

Your FaceAttend attendance verification code is:

{otp}

This code expires in {OTP_EXPIRY_MINUTES} minutes.

If you did not request attendance verification,
please ignore this email.

Face Recognition Attendance System for Employees
"""

    message = MIMEMultipart()

    message["From"] = smtp_from
    message["To"] = recipient_email
    message["Subject"] = subject

    message.attach(
        MIMEText(
            message_body,
            "plain"
        )
    )

    try:

        with smtplib.SMTP(
            smtp_host,
            smtp_port,
            timeout=20
        ) as server:

            server.ehlo()

            server.starttls()

            server.ehlo()

            server.login(
                smtp_username,
                smtp_password
            )

            server.sendmail(
                smtp_from,
                recipient_email,
                message.as_string()
            )

        print(
            "OTP email sent successfully to:",
            mask_email(recipient_email)
        )

        return True

    except Exception as error:

        print(
            "OTP email error:",
            error
        )

        return False


# =========================================================
# ATTENDANCE TIME HELPER
# =========================================================

def get_late_threshold_datetime(
    current_datetime,
    work_start_time,
    late_threshold_minutes
):

    if isinstance(
        work_start_time,
        timedelta
    ):

        total_seconds = int(
            work_start_time.total_seconds()
        )

        total_seconds = (
            total_seconds
            % (24 * 60 * 60)
        )

        hours = (
            total_seconds
            // 3600
        )

        minutes = (
            (total_seconds % 3600)
            // 60
        )

        seconds = (
            total_seconds
            % 60
        )

        start_time_value = (
            f"{hours:02d}:"
            f"{minutes:02d}:"
            f"{seconds:02d}"
        )

        work_start_datetime = datetime.strptime(
            (
                f"{current_datetime.date()} "
                f"{start_time_value}"
            ),
            "%Y-%m-%d %H:%M:%S"
        )

    elif hasattr(
        work_start_time,
        "hour"
    ):

        work_start_datetime = datetime.combine(
            current_datetime.date(),
            work_start_time
        )

    elif isinstance(
        work_start_time,
        str
    ):

        time_string = work_start_time.strip()

        if len(time_string) == 5:

            time_string += ":00"

        work_start_datetime = datetime.strptime(
            (
                f"{current_datetime.date()} "
                f"{time_string}"
            ),
            "%Y-%m-%d %H:%M:%S"
        )

    else:

        raise ValueError(
            "Invalid work_start_time value."
        )

    return (
        work_start_datetime
        + timedelta(
            minutes=int(
                late_threshold_minutes
            )
        )
    )


# =========================================================
# AUTOMATIC LBPH MODEL BUILDER
# =========================================================

def rebuild_face_model():

    if not hasattr(cv2, "face"):

        print(
            "OpenCV face module is unavailable."
        )

        print(
            "Install opencv-contrib-python."
        )

        return (
            False,
            "OpenCV face module is unavailable."
        )

    connection = get_db_connection()

    if connection is None:

        return (
            False,
            "Database connection failed."
        )

    cursor = connection.cursor(
        dictionary=True
    )

    image_records = []

    try:

        cursor.execute("""
            SELECT
                fi.employee_id,
                fi.image_path,
                fi.image_number
            FROM face_images fi
            INNER JOIN employees e
                ON fi.employee_id = e.id
            WHERE e.face_trained = 1
            ORDER BY
                fi.employee_id ASC,
                fi.image_number ASC
        """)

        image_records = cursor.fetchall()

    except mysql.connector.Error as error:

        print(
            "Model source query error:",
            error
        )

        return (
            False,
            "Unable to load face enrollment records."
        )

    finally:

        cursor.close()
        connection.close()

    if not image_records:

        if os.path.isfile(
            FACE_MODEL_PATH
        ):

            try:

                os.remove(
                    FACE_MODEL_PATH
                )

            except OSError as error:

                print(
                    "Unable to remove old model:",
                    error
                )

        print(
            "No completed face enrollments."
        )

        return (
            False,
            "No completed face enrollments."
        )

    training_faces = []
    training_labels = []

    enrolled_employee_ids = set()

    for record in image_records:

        employee_id = int(
            record["employee_id"]
        )

        image_path = record[
            "image_path"
        ]

        full_path = (
            get_face_image_full_path(
                image_path
            )
        )

        if not full_path:
            continue

        if not os.path.isfile(
            full_path
        ):

            print(
                "Missing face image:",
                full_path
            )

            continue

        image = cv2.imread(
            full_path,
            cv2.IMREAD_GRAYSCALE
        )

        if image is None:

            print(
                "Unable to read face image:",
                full_path
            )

            continue

        image = cv2.equalizeHist(
            image
        )

        faces = (
            face_detector.detectMultiScale(
                image,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(80, 80)
            )
        )

        if len(faces) == 0:

            print(
                "No face detected in:",
                full_path
            )

            continue

        largest_face = max(
            faces,
            key=lambda box:
                box[2] * box[3]
        )

        x, y, w, h = largest_face

        face_crop = image[
            y:y + h,
            x:x + w
        ]

        if face_crop.size == 0:
            continue

        face_crop = cv2.resize(
            face_crop,
            FACE_SIZE
        )

        face_crop = cv2.equalizeHist(
            face_crop
        )

        training_faces.append(
            face_crop
        )

        training_labels.append(
            employee_id
        )

        enrolled_employee_ids.add(
            employee_id
        )

    if not training_faces:

        if os.path.isfile(
            FACE_MODEL_PATH
        ):

            try:

                os.remove(
                    FACE_MODEL_PATH
                )

            except OSError:
                pass

        return (
            False,
            "No usable enrolled face images found."
        )

    try:

        os.makedirs(
            FACE_DATASET_DIR,
            exist_ok=True
        )

        recognizer = (
            cv2.face.LBPHFaceRecognizer_create(
                radius=1,
                neighbors=8,
                grid_x=8,
                grid_y=8
            )
        )

        recognizer.train(
            training_faces,
            np.array(
                training_labels,
                dtype=np.int32
            )
        )

        recognizer.save(
            FACE_MODEL_PATH
        )

        print("=" * 60)
        print("LBPH MODEL UPDATED")
        print(
            f"Training images: {len(training_faces)}"
        )
        print(
            f"Employees: {len(enrolled_employee_ids)}"
        )
        print(
            f"Model: {FACE_MODEL_PATH}"
        )
        print("=" * 60)

        return (
            True,
            "Face recognition model updated successfully."
        )

    except Exception as error:

        print(
            "LBPH model build error:",
            error
        )

        return (
            False,
            "Unable to build recognition model."
        )


# =========================================================
# LOGIN
# =========================================================

@app.route(
    "/",
    methods=["GET", "POST"]
)
@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if "admin_id" in session:

        return redirect(
            url_for("dashboard")
        )

    error = None

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        if not username or not password:

            return render_template(
                "login.html",
                error=(
                    "Please enter your username "
                    "and password."
                )
            )

        connection = (
            get_db_connection()
        )

        if connection is None:

            return render_template(
                "login.html",
                error=(
                    "Unable to connect to the database."
                )
            )

        cursor = connection.cursor(
            dictionary=True
        )

        try:

            cursor.execute("""
                SELECT
                    id,
                    username,
                    password_hash,
                    full_name
                FROM admins
                WHERE username = %s
                LIMIT 1
            """, (
                username,
            ))

            admin = cursor.fetchone()

            if (
                admin
                and check_password_hash(
                    admin["password_hash"],
                    password
                )
            ):

                session["admin_id"] = (
                    admin["id"]
                )

                session["admin_username"] = (
                    admin["username"]
                )

                session["admin_full_name"] = (
                    admin["full_name"]
                    or admin["username"]
                )

                create_audit_log(
                    "Login",
                    f"Administrator '{admin['username']}' logged in successfully."
                )

                return redirect(
                    url_for("dashboard")
                )

            error = (
                "Invalid username or password."
            )

        except mysql.connector.Error as db_error:

            print(
                "Login database error:",
                db_error
            )

            error = (
                "Unable to process your login request."
            )

        finally:

            cursor.close()
            connection.close()

    return render_template(
        "login.html",
        error=error
    )



# =========================================================
# ADMIN PROFILE
# =========================================================

@app.route("/admin-profile", methods=["GET", "POST"])
@login_required
def admin_profile():

    connection = get_db_connection()
    admin_id = session.get("admin_id")

    profile = {
        "id": admin_id,
        "username": session.get("admin_username", ""),
        "full_name": get_admin_name(),
        "created_at": None
    }

    if connection is None:
        return render_template(
            "admin_profile.html",
            profile=profile,
            admin_name=get_admin_name(),
            error="Unable to connect to the database.",
            success=None
        ), 500

    cursor = connection.cursor(dictionary=True)
    error = None
    success = None

    try:
        cursor.execute("""
            SELECT
                id,
                username,
                full_name,
                created_at,
                password_hash
            FROM admins
            WHERE id = %s
            LIMIT 1
        """, (admin_id,))

        admin = cursor.fetchone()

        if admin is None:
            session.clear()
            return redirect(url_for("login"))

        profile.update({
            "id": admin["id"],
            "username": admin["username"],
            "full_name": admin["full_name"] or admin["username"],
            "created_at": admin["created_at"]
        })

        if request.method == "POST":
            action = request.form.get("action", "profile").strip().lower()

            if action == "profile":
                full_name = request.form.get("full_name", "").strip()

                if not full_name:
                    error = "Please enter your full name."
                elif len(full_name) > 150:
                    error = "Full name must not exceed 150 characters."
                else:
                    cursor.execute("""
                        UPDATE admins
                        SET full_name = %s
                        WHERE id = %s
                    """, (full_name, admin_id))
                    connection.commit()

                    session["admin_full_name"] = full_name
                    profile["full_name"] = full_name
                    create_audit_log(
                        "Admin Profile Updated",
                        "Administrator profile name was updated."
                    )
                    success = "Your profile has been updated successfully."

                    create_notification(
                        "Admin Profile Updated",
                        f"Administrator profile for {full_name} was updated successfully.",
                        "info"
                    )

            elif action == "password":
                current_password = request.form.get("current_password", "")
                new_password = request.form.get("new_password", "")
                confirm_password = request.form.get("confirm_password", "")

                if not current_password or not new_password or not confirm_password:
                    error = "Please complete all password fields."
                elif not check_password_hash(
                    admin["password_hash"],
                    current_password
                ):
                    error = "Your current password is incorrect."
                elif len(new_password) < 8:
                    error = "Your new password must contain at least 8 characters."
                elif new_password != confirm_password:
                    error = "New password and confirmation do not match."
                elif new_password == current_password:
                    error = "Your new password must be different from the current password."
                else:
                    password_hash = generate_password_hash(new_password)

                    cursor.execute("""
                        UPDATE admins
                        SET password_hash = %s
                        WHERE id = %s
                    """, (password_hash, admin_id))
                    connection.commit()

                    success = "Your password has been changed successfully."

                    create_audit_log(
                        "Admin Password Changed",
                        "Administrator password was changed successfully."
                    )

                    create_notification(
                        "Admin Password Changed",
                        f"Administrator account {admin['username']} password was changed successfully.",
                        "info"
                    )

            else:
                error = "Invalid profile action."

    except mysql.connector.Error as db_error:
        connection.rollback()
        print("Admin profile database error:", db_error)
        error = "Unable to update your administrator profile."

    except Exception as exception:
        connection.rollback()
        print("Admin profile error:", exception)
        error = "An unexpected error occurred while updating your profile."

    finally:
        cursor.close()
        connection.close()

    return render_template(
        "admin_profile.html",
        profile=profile,
        admin_name=get_admin_name(),
        error=error,
        success=success
    )


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
@login_required
def dashboard():

    connection = get_db_connection()

    admin_name = get_admin_name()

    if connection is None:

        return render_template(
            "dashboard.html",
            error="Unable to connect to the database.",
            total_employees=0,
            total_departments=0,
            present_today=0,
            late_today=0,
            recent_attendance=[],
            attendance_session=None,
            admin_name=admin_name
        )

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM employees
        """)

        total_employees = (
            cursor.fetchone()["total"]
            or 0
        )

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM departments
        """)

        total_departments = (
            cursor.fetchone()["total"]
            or 0
        )

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM attendance
            WHERE attendance_date = CURDATE()
              AND status = 'Present'
        """)

        present_today = (
            cursor.fetchone()["total"]
            or 0
        )

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM attendance
            WHERE attendance_date = CURDATE()
              AND status = 'Late'
        """)

        late_today = (
            cursor.fetchone()["total"]
            or 0
        )

        cursor.execute("""
            SELECT
                a.id,
                a.attendance_date,
                a.check_in,
                a.check_out,
                a.status,
                e.employee_number,
                e.first_name,
                e.last_name,
                d.name AS department_name
            FROM attendance a
            INNER JOIN employees e
                ON a.employee_id = e.id
            LEFT JOIN departments d
                ON e.department_id = d.id
            ORDER BY
                a.attendance_date DESC,
                a.check_in DESC
            LIMIT 8
        """)

        recent_attendance = (
            cursor.fetchall()
        )

        cursor.execute("""
            SELECT
                id,
                attendance_date,
                started_at,
                ended_at,
                status,
                started_by
            FROM attendance_sessions
            WHERE attendance_date = CURDATE()
            ORDER BY id DESC
            LIMIT 1
        """)

        attendance_session = (
            cursor.fetchone()
        )

        return render_template(
            "dashboard.html",
            total_employees=total_employees,
            total_departments=total_departments,
            present_today=present_today,
            late_today=late_today,
            recent_attendance=recent_attendance,
            attendance_session=attendance_session,
            admin_name=admin_name
        )

    except mysql.connector.Error as error:

        print(
            "Dashboard database error:",
            error
        )

        return render_template(
            "dashboard.html",
            error="Unable to load dashboard data.",
            total_employees=0,
            total_departments=0,
            present_today=0,
            late_today=0,
            recent_attendance=[],
            attendance_session=None,
            admin_name=admin_name
        )

    finally:

        cursor.close()
        connection.close()

# =========================================================
# NOTIFICATIONS
# =========================================================

@app.route("/api/notifications")
@login_required
def get_notifications():

    connection = get_db_connection()

    if connection is None:

        return jsonify({
            "success": False,
            "message": "Unable to connect to the database."
        }), 500

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        cursor.execute("""
            SELECT
                id,
                title,
                message,
                notification_type,
                is_read,
                created_at
            FROM notifications
            ORDER BY created_at DESC, id DESC
            LIMIT 20
        """)

        notifications = cursor.fetchall()

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM notifications
            WHERE is_read = 0
        """)

        unread_count = (
            cursor.fetchone()["total"]
            or 0
        )

        for notification in notifications:

            if notification["created_at"]:

                notification["created_at"] = (
                    notification["created_at"].strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                )

        return jsonify({
            "success": True,
            "notifications": notifications,
            "unread_count": unread_count
        })

    except mysql.connector.Error as error:

        print(
            "Notifications database error:",
            error
        )

        return jsonify({
            "success": False,
            "message": "Unable to load notifications."
        }), 500

    finally:

        cursor.close()
        connection.close()


# =========================================================
# MARK NOTIFICATION AS READ
# =========================================================

@app.route(
    "/api/notifications/<int:notification_id>/read",
    methods=["POST"]
)
@login_required
def mark_notification_read(notification_id):

    connection = get_db_connection()

    if connection is None:

        return jsonify({
            "success": False,
            "message": "Unable to connect to the database."
        }), 500

    cursor = connection.cursor()

    try:

        cursor.execute("""
            UPDATE notifications
            SET is_read = 1
            WHERE id = %s
        """, (
            notification_id,
        ))

        connection.commit()

        return jsonify({
            "success": True
        })

    except mysql.connector.Error as error:

        connection.rollback()

        print(
            "Mark notification read error:",
            error
        )

        return jsonify({
            "success": False,
            "message": "Unable to update notification."
        }), 500

    finally:

        cursor.close()
        connection.close()


# =========================================================
# MARK ALL NOTIFICATIONS AS READ
# =========================================================

@app.route(
    "/api/notifications/read-all",
    methods=["POST"]
)
@login_required
def mark_all_notifications_read():

    connection = get_db_connection()

    if connection is None:

        return jsonify({
            "success": False,
            "message": "Unable to connect to the database."
        }), 500

    cursor = connection.cursor()

    try:

        cursor.execute("""
            UPDATE notifications
            SET is_read = 1
            WHERE is_read = 0
        """)

        connection.commit()

        return jsonify({
            "success": True
        })

    except mysql.connector.Error as error:

        connection.rollback()

        print(
            "Mark all notifications read error:",
            error
        )

        return jsonify({
            "success": False,
            "message": "Unable to update notifications."
        }), 500

    finally:

        cursor.close()
        connection.close()
        

# =========================================================
# SETTINGS TIME INPUT FORMATTER
# =========================================================

def format_time_for_input(value):

    if value is None:
        return ""

    if isinstance(value, timedelta):
        total_seconds = int(
            value.total_seconds()
        ) % 86400

        hours = total_seconds // 3600
        minutes = (
            total_seconds % 3600
        ) // 60

        return f"{hours:02d}:{minutes:02d}"

    if hasattr(value, "strftime"):
        return value.strftime("%H:%M")

    value_text = str(value).strip()

    if len(value_text) >= 5:
        return value_text[:5]

    return value_text


# =========================================================
# SETTINGS
# =========================================================

@app.route(
    "/settings",
    methods=["GET", "POST"]
)
@login_required
def settings():

    connection = get_db_connection()

    admin_name = get_admin_name()

    if connection is None:

        return render_template(
            "settings.html",
            settings=None,
            error="Unable to connect to the database.",
            admin_name=admin_name,
            saved=False
        ), 500

    cursor = connection.cursor(
        dictionary=True
    )

    settings_data = None

    try:

        # -------------------------------------------------
        # LOAD CURRENT SETTINGS
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                id,
                work_start_time,
                work_end_time,
                late_threshold_minutes,
                minimum_work_hours,
                created_at,
                updated_at
            FROM attendance_settings
            ORDER BY id ASC
            LIMIT 1
        """)

        settings_data = (
            cursor.fetchone()
        )

        if settings_data is not None:
            settings_data["work_start_time"] = format_time_for_input(
                settings_data["work_start_time"]
            )
            settings_data["work_end_time"] = format_time_for_input(
                settings_data["work_end_time"]
            )


        # -------------------------------------------------
        # CREATE DEFAULT SETTINGS
        # -------------------------------------------------

        if settings_data is None:

            cursor.execute("""
                INSERT INTO attendance_settings
                (
                    work_start_time,
                    work_end_time,
                    late_threshold_minutes,
                    minimum_work_hours
                )
                VALUES
                (
                    '08:00:00',
                    '17:00:00',
                    15,
                    8.00
                )
            """)

            connection.commit()

            cursor.execute("""
                SELECT
                    id,
                    work_start_time,
                    work_end_time,
                    late_threshold_minutes,
                    minimum_work_hours,
                    created_at,
                    updated_at
                FROM attendance_settings
                ORDER BY id ASC
                LIMIT 1
            """)

            settings_data = (
                cursor.fetchone()
            )

            if settings_data is not None:
                settings_data["work_start_time"] = format_time_for_input(
                    settings_data["work_start_time"]
                )
                settings_data["work_end_time"] = format_time_for_input(
                    settings_data["work_end_time"]
                )


        # -------------------------------------------------
        # SAVE SETTINGS
        # -------------------------------------------------

        if request.method == "POST":

            work_start_time = request.form.get(
                "work_start_time",
                ""
            ).strip()

            work_end_time = request.form.get(
                "work_end_time",
                ""
            ).strip()

            late_threshold_minutes = request.form.get(
                "late_threshold_minutes",
                ""
            ).strip()

            minimum_work_hours = request.form.get(
                "minimum_work_hours",
                ""
            ).strip()


            # ---------------------------------------------
            # REQUIRED VALUES
            # ---------------------------------------------

            if (
                not work_start_time
                or not work_end_time
                or not late_threshold_minutes
                or not minimum_work_hours
            ):

                return render_template(
                    "settings.html",
                    settings=settings_data,
                    error=(
                        "All attendance settings "
                        "are required."
                    ),
                    admin_name=admin_name,
                    saved=False
                )


            # ---------------------------------------------
            # CONVERT NUMERIC VALUES
            # ---------------------------------------------

            try:

                late_threshold_value = int(
                    late_threshold_minutes
                )

                minimum_work_hours_value = float(
                    minimum_work_hours
                )

            except ValueError:

                return render_template(
                    "settings.html",
                    settings=settings_data,
                    error=(
                        "Late threshold and minimum "
                        "work hours must contain valid numbers."
                    ),
                    admin_name=admin_name,
                    saved=False
                )


            # ---------------------------------------------
            # VALIDATE NUMBERS
            # ---------------------------------------------

            if late_threshold_value < 0:

                return render_template(
                    "settings.html",
                    settings=settings_data,
                    error=(
                        "Late threshold cannot be negative."
                    ),
                    admin_name=admin_name,
                    saved=False
                )


            if late_threshold_value > 720:

                return render_template(
                    "settings.html",
                    settings=settings_data,
                    error=(
                        "Late threshold cannot exceed 720 minutes."
                    ),
                    admin_name=admin_name,
                    saved=False
                )


            if minimum_work_hours_value <= 0:

                return render_template(
                    "settings.html",
                    settings=settings_data,
                    error=(
                        "Minimum work hours must be "
                        "greater than zero."
                    ),
                    admin_name=admin_name,
                    saved=False
                )


            if minimum_work_hours_value > 24:

                return render_template(
                    "settings.html",
                    settings=settings_data,
                    error=(
                        "Minimum work hours cannot exceed 24."
                    ),
                    admin_name=admin_name,
                    saved=False
                )


            # ---------------------------------------------
            # VALIDATE TIME VALUES
            # ---------------------------------------------

            try:

                datetime.strptime(
                    work_start_time,
                    "%H:%M"
                )

                datetime.strptime(
                    work_end_time,
                    "%H:%M"
                )

            except ValueError:

                return render_template(
                    "settings.html",
                    settings=settings_data,
                    error=(
                        "Please enter valid work start "
                        "and end times."
                    ),
                    admin_name=admin_name,
                    saved=False
                )


            # ---------------------------------------------
            # UPDATE DATABASE
            # ---------------------------------------------

            cursor.execute("""
                UPDATE attendance_settings
                SET
                    work_start_time = %s,
                    work_end_time = %s,
                    late_threshold_minutes = %s,
                    minimum_work_hours = %s
                WHERE id = %s
            """, (
                work_start_time,
                work_end_time,
                late_threshold_value,
                minimum_work_hours_value,
                settings_data["id"]
            ))

            connection.commit()

            create_notification(
                "Attendance Settings Updated",
                "The attendance rules and working hours were updated.",
                "info"
            )

            create_audit_log(
                "Attendance Settings Updated",
                "Attendance working hours and late-arrival rules were updated."
            )

            # Reload updated settings
            cursor.execute("""
                SELECT
                    id,
                    work_start_time,
                    work_end_time,
                    late_threshold_minutes,
                    minimum_work_hours,
                    created_at,
                    updated_at
                FROM attendance_settings
                WHERE id = %s
                LIMIT 1
            """, (
                settings_data["id"],
            ))

            settings_data = cursor.fetchone()

            print("=" * 70)
            print("ATTENDANCE SETTINGS UPDATED")
            print(
                f"Work start time: {work_start_time}"
            )
            print(
                f"Work end time: {work_end_time}"
            )
            print(
                f"Late threshold: "
                f"{late_threshold_value} minutes"
            )
            print(
                f"Minimum work hours: "
                f"{minimum_work_hours_value}"
            )
            print("=" * 70)

            return redirect(
                url_for(
                    "settings",
                    saved=1
                )
            )


        # -------------------------------------------------
        # SUCCESS FLAG
        # -------------------------------------------------

        saved = (
            request.args.get(
                "saved"
            ) == "1"
        )


        # -------------------------------------------------
        # DISPLAY SETTINGS
        # -------------------------------------------------

        return render_template(
            "settings.html",
            settings=settings_data,
            admin_name=admin_name,
            saved=saved,
            error=None
        )


    except mysql.connector.Error as error:

        connection.rollback()

        print(
            "Settings database error:",
            error
        )

        return render_template(
            "settings.html",
            settings=settings_data,
            error=(
                "Unable to load or save "
                "attendance settings."
            ),
            admin_name=admin_name,
            saved=False
        ), 500


    except Exception as error:

        connection.rollback()

        print(
            "Settings error:",
            error
        )

        return render_template(
            "settings.html",
            settings=settings_data,
            error=(
                "An unexpected error occurred "
                "while processing settings."
            ),
            admin_name=admin_name,
            saved=False
        ), 500


    finally:

        cursor.close()
        connection.close()


# =========================================================
# EMPLOYEES
# =========================================================

@app.route("/employees")
@login_required
def employees():

    connection = get_db_connection()

    admin_name = get_admin_name()

    if connection is None:

        return render_template(
            "employees.html",
            error="Unable to connect to the database.",
            employees=[],
            admin_name=admin_name
        )

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        cursor.execute("""
            SELECT
                e.id,
                e.employee_number,
                e.first_name,
                e.last_name,
                e.gender,
                e.email,
                e.phone,
                e.position,
                e.face_trained,
                d.name AS department_name
            FROM employees e
            LEFT JOIN departments d
                ON e.department_id = d.id
            ORDER BY
                e.first_name ASC,
                e.last_name ASC
        """)

        employees_list = (
            cursor.fetchall()
        )

        return render_template(
            "employees.html",
            employees=employees_list,
            admin_name=admin_name
        )

    except mysql.connector.Error as error:

        print(
            "Employees database error:",
            error
        )

        return render_template(
            "employees.html",
            error="Unable to load employee records.",
            employees=[],
            admin_name=admin_name
        )

    finally:

        cursor.close()
        connection.close()


# =========================================================
# ADD EMPLOYEE
# =========================================================

@app.route(
    "/employees/add",
    methods=["GET", "POST"]
)
@login_required
def add_employee():

    connection = get_db_connection()

    admin_name = get_admin_name()

    if connection is None:

        return render_template(
            "add_employee.html",
            error="Unable to connect to the database.",
            departments=[],
            admin_name=admin_name
        )

    cursor = connection.cursor(
        dictionary=True
    )

    departments = []

    try:

        cursor.execute("""
            SELECT
                id,
                name
            FROM departments
            ORDER BY name ASC
        """)

        departments = cursor.fetchall()

        if request.method == "POST":

            employee_number = request.form.get(
                "employee_number",
                ""
            ).strip()

            first_name = request.form.get(
                "first_name",
                ""
            ).strip()

            last_name = request.form.get(
                "last_name",
                ""
            ).strip()

            gender = request.form.get(
                "gender",
                ""
            ).strip()

            email = request.form.get(
                "email",
                ""
            ).strip()

            phone = request.form.get(
                "phone",
                ""
            ).strip()

            position = request.form.get(
                "position",
                ""
            ).strip()

            department_id = request.form.get(
                "department_id",
                ""
            ).strip()

            if (
                not employee_number
                or not first_name
                or not last_name
            ):

                return render_template(
                    "add_employee.html",
                    error=(
                        "Employee number, first name "
                        "and last name are required."
                    ),
                    departments=departments,
                    admin_name=admin_name
                )

            if department_id == "":

                department_id = None

            else:

                department_id = int(
                    department_id
                )

            cursor.execute("""
                SELECT id
                FROM employees
                WHERE employee_number = %s
                LIMIT 1
            """, (
                employee_number,
            ))

            if cursor.fetchone():

                return render_template(
                    "add_employee.html",
                    error=(
                        "Employee number already exists."
                    ),
                    departments=departments,
                    admin_name=admin_name
                )

            if email:

                cursor.execute("""
                    SELECT id
                    FROM employees
                    WHERE email = %s
                    LIMIT 1
                """, (
                    email,
                ))

                if cursor.fetchone():

                    return render_template(
                        "add_employee.html",
                        error=(
                            "Email address is already registered."
                        ),
                        departments=departments,
                        admin_name=admin_name
                    )

            cursor.execute("""
                INSERT INTO employees
                (
                    employee_number,
                    first_name,
                    last_name,
                    gender,
                    email,
                    phone,
                    position,
                    department_id,
                    face_trained
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    0
                )
            """, (
                employee_number,
                first_name,
                last_name,
                gender or None,
                email or None,
                phone or None,
                position or None,
                department_id
            ))

            connection.commit()

            create_notification(
                "Employee Added",
                f"Employee {first_name} {last_name} was added successfully.",
                "success"
            )

            create_audit_log(
                "Employee Added",
                f"Employee {first_name} {last_name} ({employee_number}) was added."
            )

            return redirect(
                url_for("employees")
            )

        return render_template(
            "add_employee.html",
            departments=departments,
            admin_name=admin_name
        )

    except ValueError:

        connection.rollback()

        return render_template(
            "add_employee.html",
            error="Invalid department selected.",
            departments=departments,
            admin_name=admin_name
        )

    except mysql.connector.Error as error:

        connection.rollback()

        print(
            "Add employee database error:",
            error
        )

        return render_template(
            "add_employee.html",
            error="Unable to add employee. Please try again.",
            departments=departments,
            admin_name=admin_name
        )

    finally:

        cursor.close()
        connection.close()


# =========================================================
# VIEW EMPLOYEE
# =========================================================

@app.route(
    "/employees/view/<int:employee_id>"
)
@login_required
def view_employee(employee_id):

    connection = get_db_connection()

    admin_name = get_admin_name()

    if connection is None:

        return render_template(
            "view_employee.html",
            error="Unable to connect to the database.",
            employee=None,
            face_images=[],
            admin_name=admin_name
        )

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        cursor.execute("""
            SELECT
                e.id,
                e.employee_number,
                e.first_name,
                e.last_name,
                e.gender,
                e.email,
                e.phone,
                e.position,
                e.department_id,
                e.face_trained,
                d.name AS department_name
            FROM employees e
            LEFT JOIN departments d
                ON e.department_id = d.id
            WHERE e.id = %s
            LIMIT 1
        """, (
            employee_id,
        ))

        employee = cursor.fetchone()

        if employee is None:

            return redirect(
                url_for("employees")
            )

        cursor.execute("""
            SELECT
                id,
                image_path,
                image_number,
                captured_at
            FROM face_images
            WHERE employee_id = %s
            ORDER BY image_number ASC
        """, (
            employee_id,
        ))

        face_images = cursor.fetchall()

        return render_template(
            "view_employee.html",
            employee=employee,
            face_images=face_images,
            admin_name=admin_name
        )

    except mysql.connector.Error as error:

        print(
            "View employee database error:",
            error
        )

        return render_template(
            "view_employee.html",
            error="Unable to load employee information.",
            employee=None,
            face_images=[],
            admin_name=admin_name
        )

    finally:

        cursor.close()
        connection.close()


# =========================================================
# EDIT EMPLOYEE
# =========================================================

@app.route(
    "/employees/edit/<int:employee_id>",
    methods=["GET", "POST"]
)
@login_required
def edit_employee(employee_id):

    connection = get_db_connection()

    admin_name = get_admin_name()

    if connection is None:

        return render_template(
            "edit_employee.html",
            error="Unable to connect to the database.",
            employee=None,
            departments=[],
            admin_name=admin_name
        )

    cursor = connection.cursor(
        dictionary=True
    )

    departments = []
    employee = None

    try:

        cursor.execute("""
            SELECT
                id,
                name
            FROM departments
            ORDER BY name ASC
        """)

        departments = cursor.fetchall()

        cursor.execute("""
            SELECT
                id,
                employee_number,
                first_name,
                last_name,
                gender,
                email,
                phone,
                position,
                department_id,
                face_trained
            FROM employees
            WHERE id = %s
            LIMIT 1
        """, (
            employee_id,
        ))

        employee = cursor.fetchone()

        if employee is None:

            return redirect(
                url_for("employees")
            )

        if request.method == "POST":

            employee_number = request.form.get(
                "employee_number",
                ""
            ).strip()

            first_name = request.form.get(
                "first_name",
                ""
            ).strip()

            last_name = request.form.get(
                "last_name",
                ""
            ).strip()

            gender = request.form.get(
                "gender",
                ""
            ).strip()

            email = request.form.get(
                "email",
                ""
            ).strip()

            phone = request.form.get(
                "phone",
                ""
            ).strip()

            position = request.form.get(
                "position",
                ""
            ).strip()

            department_id = request.form.get(
                "department_id",
                ""
            ).strip()

            if (
                not employee_number
                or not first_name
                or not last_name
            ):

                return render_template(
                    "edit_employee.html",
                    error=(
                        "Employee number, first name "
                        "and last name are required."
                    ),
                    employee=employee,
                    departments=departments,
                    admin_name=admin_name
                )

            if department_id == "":

                department_id = None

            else:

                department_id = int(
                    department_id
                )

            cursor.execute("""
                SELECT id
                FROM employees
                WHERE employee_number = %s
                  AND id != %s
                LIMIT 1
            """, (
                employee_number,
                employee_id
            ))

            if cursor.fetchone():

                return render_template(
                    "edit_employee.html",
                    error=(
                        "Employee number already exists."
                    ),
                    employee=employee,
                    departments=departments,
                    admin_name=admin_name
                )

            if email:

                cursor.execute("""
                    SELECT id
                    FROM employees
                    WHERE email = %s
                      AND id != %s
                    LIMIT 1
                """, (
                    email,
                    employee_id
                ))

                if cursor.fetchone():

                    return render_template(
                        "edit_employee.html",
                        error=(
                            "Email address is already registered."
                        ),
                        employee=employee,
                        departments=departments,
                        admin_name=admin_name
                    )

            cursor.execute("""
                UPDATE employees
                SET
                    employee_number = %s,
                    first_name = %s,
                    last_name = %s,
                    gender = %s,
                    email = %s,
                    phone = %s,
                    position = %s,
                    department_id = %s
                WHERE id = %s
            """, (
                employee_number,
                first_name,
                last_name,
                gender or None,
                email or None,
                phone or None,
                position or None,
                department_id,
                employee_id
            ))

            connection.commit()

            create_audit_log(
                "Employee Updated",
                f"Employee {first_name} {last_name} ({employee_number}) was updated."
            )

            return redirect(
                url_for(
                    "view_employee",
                    employee_id=employee_id
                )
            )

        return render_template(
            "edit_employee.html",
            employee=employee,
            departments=departments,
            admin_name=admin_name
        )

    except ValueError:

        connection.rollback()

        return render_template(
            "edit_employee.html",
            error="Invalid department selected.",
            employee=employee,
            departments=departments,
            admin_name=admin_name
        )

    except mysql.connector.Error as error:

        connection.rollback()

        print(
            "Edit employee database error:",
            error
        )

        return render_template(
            "edit_employee.html",
            error="Unable to update employee.",
            employee=employee,
            departments=departments,
            admin_name=admin_name
        )

    finally:

        cursor.close()
        connection.close()


# =========================================================
# FACE ENROLLMENT LIST
# =========================================================

@app.route("/face-enrollment")
@login_required
def face_enrollment_list():

    connection = get_db_connection()

    admin_name = get_admin_name()

    if connection is None:

        return render_template(
            "face_enrollment_list.html",
            error="Unable to connect to the database.",
            employees=[],
            admin_name=admin_name
        )

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        cursor.execute("""
            SELECT
                e.id,
                e.employee_number,
                e.first_name,
                e.last_name,
                e.gender,
                e.email,
                e.phone,
                e.position,
                e.face_trained,
                d.name AS department_name,

                (
                    SELECT COUNT(*)
                    FROM face_images fi
                    WHERE fi.employee_id = e.id
                ) AS image_count

            FROM employees e

            LEFT JOIN departments d
                ON e.department_id = d.id

            ORDER BY
                e.first_name ASC,
                e.last_name ASC
        """)

        employees_list = cursor.fetchall()

        return render_template(
            "face_enrollment_list.html",
            employees=employees_list,
            admin_name=admin_name
        )

    except mysql.connector.Error as error:

        print(
            "Face enrollment list database error:",
            error
        )

        return render_template(
            "face_enrollment_list.html",
            error=(
                "Unable to load face enrollment records."
            ),
            employees=[],
            admin_name=admin_name
        )

    finally:

        cursor.close()
        connection.close()


# =========================================================
# FACE ENROLLMENT
# =========================================================

@app.route(
    "/face-enrollment/<int:employee_id>"
)
@login_required
def face_enrollment(employee_id):

    connection = get_db_connection()

    admin_name = get_admin_name()

    if connection is None:

        return render_template(
            "face_enrollment.html",
            error="Unable to connect to the database.",
            employee=None,
            image_count=0,
            face_images=[],
            admin_name=admin_name
        )

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        cursor.execute("""
            SELECT
                e.id,
                e.employee_number,
                e.first_name,
                e.last_name,
                e.gender,
                e.email,
                e.phone,
                e.position,
                e.face_trained,
                d.name AS department_name
            FROM employees e
            LEFT JOIN departments d
                ON e.department_id = d.id
            WHERE e.id = %s
            LIMIT 1
        """, (
            employee_id,
        ))

        employee = cursor.fetchone()

        if employee is None:

            return redirect(
                url_for("face_enrollment_list")
            )

        cursor.execute("""
            SELECT
                id,
                employee_id,
                image_path,
                image_number,
                captured_at
            FROM face_images
            WHERE employee_id = %s
            ORDER BY image_number ASC
        """, (
            employee_id,
        ))

        face_images = cursor.fetchall()

        return render_template(
            "face_enrollment.html",
            employee=employee,
            image_count=len(face_images),
            face_images=face_images,
            admin_name=admin_name
        )

    except mysql.connector.Error as error:

        print(
            "Face enrollment database error:",
            error
        )

        return render_template(
            "face_enrollment.html",
            error="Unable to load face enrollment.",
            employee=None,
            image_count=0,
            face_images=[],
            admin_name=admin_name
        )

    finally:

        cursor.close()
        connection.close()


# =========================================================
# SERVE FACE DATASET IMAGES
# =========================================================

@app.route(
    "/face-dataset/<path:filename>"
)
@login_required
def face_dataset_file(filename):

    return send_from_directory(
        FACE_DATASET_DIR,
        filename
    )


# =========================================================
# CAPTURE FACE IMAGE
# =========================================================

@app.route(
    "/face-enrollment/<int:employee_id>/capture",
    methods=["POST"]
)
@login_required
def capture_face(employee_id):

    connection = get_db_connection()

    if connection is None:

        return jsonify({
            "success": False,
            "message": (
                "Unable to connect to the database."
            )
        }), 500

    cursor = connection.cursor(
        dictionary=True
    )

    full_path = None

    try:

        cursor.execute("""
            SELECT id
            FROM employees
            WHERE id = %s
            LIMIT 1
        """, (
            employee_id,
        ))

        employee = cursor.fetchone()

        if employee is None:

            return jsonify({
                "success": False,
                "message": "Employee not found."
            }), 404

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM face_images
            WHERE employee_id = %s
        """, (
            employee_id,
        ))

        current_count = (
            cursor.fetchone()["total"]
            or 0
        )

        if current_count >= MIN_FACE_IMAGES:

            return jsonify({
                "success": False,
                "message": (
                    "This employee already has "
                    f"{MIN_FACE_IMAGES} face images."
                )
            }), 400

        data = request.get_json(
            silent=True
        )

        if not data:

            return jsonify({
                "success": False,
                "message": (
                    "No image data was received."
                )
            }), 400

        image_data = data.get(
            "image",
            ""
        ).strip()

        if not image_data.startswith(
            "data:image/jpeg;base64,"
        ):

            return jsonify({
                "success": False,
                "message": (
                    "Invalid image format."
                )
            }), 400

        try:

            encoded_data = image_data.split(
                ",",
                1
            )[1]

            image_bytes = base64.b64decode(
                encoded_data,
                validate=True
            )

        except Exception:

            return jsonify({
                "success": False,
                "message": (
                    "Unable to decode captured image."
                )
            }), 400

        if not image_bytes:

            return jsonify({
                "success": False,
                "message": (
                    "The captured image is empty."
                )
            }), 400

        image_array = np.frombuffer(
            image_bytes,
            dtype=np.uint8
        )

        captured_frame = cv2.imdecode(
            image_array,
            cv2.IMREAD_COLOR
        )

        if captured_frame is None:

            return jsonify({
                "success": False,
                "message": (
                    "The captured image could not be read."
                )
            }), 400

        gray = cv2.cvtColor(
            captured_frame,
            cv2.COLOR_BGR2GRAY
        )

        gray = cv2.equalizeHist(
            gray
        )

        detected_faces = (
            face_detector.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(80, 80)
            )
        )

        if len(detected_faces) == 0:

            return jsonify({
                "success": False,
                "message": (
                    "No face detected. "
                    "Position the employee clearly "
                    "in front of the camera."
                )
            }), 400

        if len(detected_faces) > 1:

            return jsonify({
                "success": False,
                "message": (
                    "Multiple faces detected. "
                    "Only one employee should be visible."
                )
            }), 400

        employee_folder = os.path.join(
            FACE_DATASET_DIR,
            str(employee_id)
        )

        os.makedirs(
            employee_folder,
            exist_ok=True
        )

        image_number = (
            current_count + 1
        )

        filename = (
            f"face_{image_number:02d}.jpg"
        )

        full_path = os.path.join(
            employee_folder,
            filename
        )

        with open(
            full_path,
            "wb"
        ) as image_file:

            image_file.write(
                image_bytes
            )

        image_path = os.path.join(
            "face_dataset",
            str(employee_id),
            filename
        ).replace(
            "\\",
            "/"
        )

        cursor.execute("""
            INSERT INTO face_images
            (
                employee_id,
                image_path,
                image_number
            )
            VALUES
            (
                %s,
                %s,
                %s
            )
        """, (
            employee_id,
            image_path,
            image_number
        ))

        new_count = image_number

        cursor.execute("""
            UPDATE employees
            SET face_trained = %s
            WHERE id = %s
        """, (
            1 if new_count >= MIN_FACE_IMAGES else 0,
            employee_id
        ))

        connection.commit()

        create_audit_log(
            "Face Image Captured",
            f"Face enrollment image {new_count} was captured for employee ID {employee_id}."
        )

        if new_count == MIN_FACE_IMAGES:

            cursor.execute("""
                SELECT first_name, last_name, employee_number
                FROM employees
                WHERE id = %s
            """, (
                employee_id,
            ))

            employee_info = cursor.fetchone()

            employee_display = (
                f"{employee_info['first_name']} {employee_info['last_name']} "
                f"({employee_info['employee_number']})"
                if employee_info
                else f"Employee ID {employee_id}"
            )

            create_notification(
                "Face Enrollment Completed",
                f"Face enrollment completed for {employee_display} with {new_count} images.",
                "success"
            )

        model_updated, model_message = (
            rebuild_face_model()
        )

        print(
            "Automatic model update:",
            model_message
        )

        return jsonify({
            "success": True,
            "message": (
                f"Face image {image_number} "
                "captured successfully."
            ),
            "image_count": new_count,
            "face_trained": (
                new_count >= MIN_FACE_IMAGES
            ),
            "model_updated": model_updated
        })

    except mysql.connector.Error as error:

        connection.rollback()

        print(
            "Face capture database error:",
            error
        )

        try:

            if (
                full_path
                and os.path.isfile(full_path)
            ):

                os.remove(
                    full_path
                )

        except OSError:
            pass

        return jsonify({
            "success": False,
            "message": (
                "Unable to save the face image."
            )
        }), 500

    except OSError as error:

        connection.rollback()

        print(
            "Face capture file error:",
            error
        )

        return jsonify({
            "success": False,
            "message": (
                "Unable to save the captured image."
            )
        }), 500

    finally:

        cursor.close()
        connection.close()


# =========================================================
# DELETE CAPTURED FACE IMAGE
# =========================================================

@app.route(
    "/face-enrollment/image/<int:image_id>/delete",
    methods=["POST"]
)
@login_required
def delete_face_image(image_id):

    connection = get_db_connection()

    if connection is None:

        return redirect(
            url_for("face_enrollment_list")
        )

    cursor = connection.cursor(
        dictionary=True
    )

    employee_id = None

    try:

        cursor.execute("""
            SELECT
                id,
                employee_id,
                image_path
            FROM face_images
            WHERE id = %s
            LIMIT 1
        """, (
            image_id,
        ))

        image = cursor.fetchone()

        if image is None:

            return redirect(
                url_for("face_enrollment_list")
            )

        employee_id = image[
            "employee_id"
        ]

        old_file = (
            get_face_image_full_path(
                image["image_path"]
            )
        )

        if (
            old_file
            and os.path.isfile(old_file)
        ):

            os.remove(
                old_file
            )

        cursor.execute("""
            DELETE FROM face_images
            WHERE id = %s
        """, (
            image_id,
        ))

        cursor.execute("""
            SELECT
                id,
                image_path,
                image_number
            FROM face_images
            WHERE employee_id = %s
            ORDER BY
                image_number ASC,
                id ASC
        """, (
            employee_id,
        ))

        remaining_images = (
            cursor.fetchall()
        )

        temp_files = []

        for remaining_image in remaining_images:

            old_path = (
                get_face_image_full_path(
                    remaining_image["image_path"]
                )
            )

            if (
                old_path
                and os.path.isfile(old_path)
            ):

                temporary_path = os.path.join(
                    os.path.dirname(old_path),
                    (
                        f".tmp_face_"
                        f"{remaining_image['id']}.jpg"
                    )
                )

                os.rename(
                    old_path,
                    temporary_path
                )

                temp_files.append({
                    "id": remaining_image["id"],
                    "path": temporary_path
                })

        employee_folder = os.path.join(
            FACE_DATASET_DIR,
            str(employee_id)
        )

        os.makedirs(
            employee_folder,
            exist_ok=True
        )

        for index, temp_file in enumerate(
            temp_files,
            start=1
        ):

            new_filename = (
                f"face_{index:02d}.jpg"
            )

            new_path = os.path.join(
                employee_folder,
                new_filename
            )

            os.rename(
                temp_file["path"],
                new_path
            )

            new_database_path = os.path.join(
                "face_dataset",
                str(employee_id),
                new_filename
            ).replace(
                "\\",
                "/"
            )

            cursor.execute("""
                UPDATE face_images
                SET
                    image_number = %s,
                    image_path = %s
                WHERE id = %s
            """, (
                index,
                new_database_path,
                temp_file["id"]
            ))

        new_count = len(
            remaining_images
        )

        cursor.execute("""
            UPDATE employees
            SET face_trained = %s
            WHERE id = %s
        """, (
            1 if new_count >= MIN_FACE_IMAGES else 0,
            employee_id
        ))

        connection.commit()

        create_notification(
            "Face Enrollment Updated",
            f"A face enrollment image was removed for employee ID {employee_id}.",
            "info"
        )

        create_audit_log(
            "Face Image Deleted",
            f"A face enrollment image was deleted for employee ID {employee_id}."
        )

        model_updated, model_message = (
            rebuild_face_model()
        )

        print(
            "Automatic model update:",
            model_message
        )

        return redirect(
            url_for(
                "face_enrollment",
                employee_id=employee_id
            )
        )

    except mysql.connector.Error as error:

        connection.rollback()

        print(
            "Delete face image database error:",
            error
        )

        if employee_id is not None:

            return redirect(
                url_for(
                    "face_enrollment",
                    employee_id=employee_id
                )
            )

        return redirect(
            url_for("face_enrollment_list")
        )

    except OSError as error:

        connection.rollback()

        print(
            "Delete face image file error:",
            error
        )

        if employee_id is not None:

            return redirect(
                url_for(
                    "face_enrollment",
                    employee_id=employee_id
                )
            )

        return redirect(
            url_for("face_enrollment_list")
        )

    finally:

        cursor.close()
        connection.close()


# =========================================================
# DELETE EMPLOYEE
# =========================================================

@app.route(
    "/employees/delete/<int:employee_id>",
    methods=["POST"]
)
@login_required
def delete_employee(employee_id):

    connection = get_db_connection()

    if connection is None:

        return redirect(
            url_for("employees")
        )

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        cursor.execute("""
            SELECT first_name, last_name, employee_number
            FROM employees
            WHERE id = %s
        """, (
            employee_id,
        ))

        employee_info = cursor.fetchone()

        cursor.execute("""
            SELECT image_path
            FROM face_images
            WHERE employee_id = %s
        """, (
            employee_id,
        ))

        employee_images = (
            cursor.fetchall()
        )

        cursor.execute("""
            DELETE FROM employees
            WHERE id = %s
        """, (
            employee_id,
        ))

        connection.commit()

        employee_display = (
            f"{employee_info['first_name']} {employee_info['last_name']} "
            f"({employee_info['employee_number']})"
            if employee_info
            else f"Employee ID {employee_id}"
        )

        create_notification(
            "Employee Deleted",
            f"{employee_display} was deleted successfully.",
            "warning"
        )

        create_audit_log(
            "Employee Deleted",
            f"{employee_display} was deleted."
        )

        for image in employee_images:

            full_path = (
                get_face_image_full_path(
                    image["image_path"]
                )
            )

            if (
                full_path
                and os.path.isfile(full_path)
            ):

                try:

                    os.remove(
                        full_path
                    )

                except OSError as error:

                    print(
                        "Unable to remove face image:",
                        error
                    )

        employee_folder = os.path.join(
            FACE_DATASET_DIR,
            str(employee_id)
        )

        if os.path.isdir(
            employee_folder
        ):

            try:

                os.rmdir(
                    employee_folder
                )

            except OSError:
                pass

        model_updated, model_message = (
            rebuild_face_model()
        )

        print(
            "Automatic model update:",
            model_message
        )

        return redirect(
            url_for("employees")
        )

    except mysql.connector.Error as error:

        connection.rollback()

        print(
            "Delete employee database error:",
            error
        )

        return redirect(
            url_for("employees")
        )

    finally:

        cursor.close()
        connection.close()


# =========================================================
# DEPARTMENTS
# =========================================================

@app.route("/departments")
@login_required
def departments():

    connection = get_db_connection()

    admin_name = get_admin_name()

    if connection is None:

        return render_template(
            "departments.html",
            departments=[],
            admin_name=admin_name,
            error=(
                "Unable to connect to the database."
            )
        )

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        cursor.execute("""
            SELECT
                d.id,
                d.name,
                d.description,
                COUNT(e.id) AS employee_count
            FROM departments d
            LEFT JOIN employees e
                ON e.department_id = d.id
            GROUP BY
                d.id,
                d.name,
                d.description
            ORDER BY d.name ASC
        """)

        departments_list = (
            cursor.fetchall()
        )

        return render_template(
            "departments.html",
            departments=departments_list,
            admin_name=admin_name
        )

    except mysql.connector.Error as error:

        print(
            "Departments database error:",
            error
        )

        return render_template(
            "departments.html",
            departments=[],
            admin_name=admin_name,
            error=(
                "Unable to load departments."
            )
        )

    finally:

        cursor.close()
        connection.close()


# =========================================================
# ADD DEPARTMENT
# =========================================================

@app.route(
    "/departments/add",
    methods=["GET", "POST"]
)
@login_required
def add_department():

    connection = get_db_connection()

    admin_name = get_admin_name()

    if connection is None:

        return render_template(
            "add_department.html",
            admin_name=admin_name,
            error=(
                "Unable to connect to the database."
            )
        )

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        if request.method == "POST":

            name = request.form.get(
                "name",
                ""
            ).strip()

            description = request.form.get(
                "description",
                ""
            ).strip()

            if not name:

                return render_template(
                    "add_department.html",
                    admin_name=admin_name,
                    error=(
                        "Department name is required."
                    )
                )

            cursor.execute("""
                SELECT id
                FROM departments
                WHERE name = %s
                LIMIT 1
            """, (
                name,
            ))

            if cursor.fetchone():

                return render_template(
                    "add_department.html",
                    admin_name=admin_name,
                    error=(
                        "Department already exists."
                    )
                )

            cursor.execute("""
                INSERT INTO departments
                (
                    name,
                    description
                )
                VALUES
                (
                    %s,
                    %s
                )
            """, (
                name,
                description or None
            ))

            connection.commit()

            create_notification(
                "Department Added",
                f"Department '{name}' was added successfully.",
                "success"
            )

            create_audit_log(
                "Department Added",
                f"Department '{name}' was added."
            )

            return redirect(
                url_for("departments")
            )

        return render_template(
            "add_department.html",
            admin_name=admin_name
        )

    except mysql.connector.Error as error:

        connection.rollback()

        print(
            "Add department database error:",
            error
        )

        return render_template(
            "add_department.html",
            admin_name=admin_name,
            error="Unable to add department."
        )

    finally:

        cursor.close()
        connection.close()


# =========================================================
# EDIT DEPARTMENT
# =========================================================

@app.route(
    "/departments/edit/<int:department_id>",
    methods=["GET", "POST"]
)
@login_required
def edit_department(department_id):

    connection = get_db_connection()

    admin_name = get_admin_name()

    if connection is None:

        return redirect(
            url_for("departments")
        )

    cursor = connection.cursor(
        dictionary=True
    )

    department = None

    try:

        cursor.execute("""
            SELECT
                id,
                name,
                description
            FROM departments
            WHERE id = %s
            LIMIT 1
        """, (
            department_id,
        ))

        department = cursor.fetchone()

        if department is None:

            return redirect(
                url_for("departments")
            )

        if request.method == "POST":

            name = request.form.get(
                "name",
                ""
            ).strip()

            description = request.form.get(
                "description",
                ""
            ).strip()

            if not name:

                return render_template(
                    "edit_department.html",
                    department=department,
                    admin_name=admin_name,
                    error=(
                        "Department name is required."
                    )
                )

            cursor.execute("""
                SELECT id
                FROM departments
                WHERE name = %s
                  AND id != %s
                LIMIT 1
            """, (
                name,
                department_id
            ))

            if cursor.fetchone():

                return render_template(
                    "edit_department.html",
                    department=department,
                    admin_name=admin_name,
                    error=(
                        "Department already exists."
                    )
                )

            cursor.execute("""
                UPDATE departments
                SET
                    name = %s,
                    description = %s
                WHERE id = %s
            """, (
                name,
                description or None,
                department_id
            ))

            connection.commit()

            create_notification(
                "Department Updated",
                f"Department '{name}' was updated successfully.",
                "info"
            )

            create_audit_log(
                "Department Updated",
                f"Department '{name}' (ID {department_id}) was updated."
            )

            return redirect(
                url_for("departments")
            )

        return render_template(
            "edit_department.html",
            department=department,
            admin_name=admin_name
        )

    except mysql.connector.Error as error:

        connection.rollback()

        print(
            "Edit department database error:",
            error
        )

        return render_template(
            "edit_department.html",
            department=department,
            admin_name=admin_name,
            error=(
                "Unable to update department."
            )
        )

    finally:

        cursor.close()
        connection.close()


# =========================================================
# DELETE DEPARTMENT
# =========================================================

@app.route(
    "/departments/delete/<int:department_id>",
    methods=["POST"]
)
@login_required
def delete_department(department_id):

    connection = get_db_connection()

    if connection is None:

        return redirect(
            url_for("departments")
        )

    cursor = connection.cursor()

    try:

        cursor.execute("""
            SELECT COUNT(*)
            FROM employees
            WHERE department_id = %s
        """, (
            department_id,
        ))

        result = cursor.fetchone()

        employee_count = (
            result[0]
            or 0
        )

        if employee_count > 0:

            return redirect(
                url_for("departments")
            )

        cursor.execute("""
            DELETE FROM departments
            WHERE id = %s
        """, (
            department_id,
        ))

        connection.commit()

        create_notification(
            "Department Deleted",
            f"Department ID {department_id} was deleted successfully.",
            "warning"
        )

        create_audit_log(
            "Department Deleted",
            f"Department ID {department_id} was deleted."
        )

        return redirect(
            url_for("departments")
        )

    except mysql.connector.Error as error:

        connection.rollback()

        print(
            "Delete department database error:",
            error
        )

        return redirect(
            url_for("departments")
        )

    finally:

        cursor.close()
        connection.close()


# =========================================================
# START / REOPEN TODAY'S ATTENDANCE
# =========================================================

@app.route(
    "/attendance/start",
    methods=["POST"]
)
@login_required
def start_attendance():

    connection = get_db_connection()

    if connection is None:

        return redirect(
            url_for("dashboard")
        )

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        cursor.execute("""
            SELECT
                id,
                attendance_date,
                started_at,
                ended_at,
                status,
                started_by
            FROM attendance_sessions
            WHERE attendance_date = CURDATE()
            ORDER BY id DESC
            LIMIT 1
        """)

        existing_session = (
            cursor.fetchone()
        )

        if existing_session:

            if existing_session["status"] == "Active":

                print(
                    "Today's attendance session "
                    "is already active."
                )

                return redirect(
                    url_for("attendance")
                )

            if existing_session["status"] == "Closed":

                cursor.execute("""
                    UPDATE attendance_sessions
                    SET
                        status = 'Active',
                        ended_at = NULL
                    WHERE id = %s
                """, (
                    existing_session["id"],
                ))

                connection.commit()

                create_audit_log(
                    "Attendance Session Reopened",
                    f"Today's attendance session (ID {existing_session['id']}) was reopened."
                )

                create_notification(
                    "Attendance Session Reopened",
                    "Today's employee attendance session has been reopened.",
                    "info"
                )

                print("=" * 70)
                print("ATTENDANCE SESSION REOPENED")
                print(
                    f"Session ID: "
                    f"{existing_session['id']}"
                )
                print(
                    f"Attendance date: "
                    f"{existing_session['attendance_date']}"
                )
                print("=" * 70)

                return redirect(
                    url_for("attendance")
                )

        cursor.execute("""
            INSERT INTO attendance_sessions
            (
                attendance_date,
                started_at,
                status,
                started_by
            )
            VALUES
            (
                CURDATE(),
                NOW(),
                'Active',
                %s
            )
        """, (
            session["admin_id"],
        ))

        connection.commit()

        create_audit_log(
            "Attendance Session Started",
            "Today's employee attendance session was started."
        )

        create_notification(
            "Attendance Session Started",
            "Today's employee attendance session has been started.",
            "success"
        )

        print("=" * 70)
        print("NEW ATTENDANCE SESSION STARTED")
        print("=" * 70)

        return redirect(
            url_for("attendance")
        )

    except mysql.connector.Error as error:

        connection.rollback()

        print(
            "Start attendance database error:",
            error
        )

        return redirect(
            url_for("dashboard")
        )

    finally:

        cursor.close()
        connection.close()


# =========================================================
# CLOSE TODAY'S ATTENDANCE
# =========================================================

@app.route(
    "/attendance/close",
    methods=["POST"]
)
@login_required
def close_attendance_session():

    connection = get_db_connection()

    if connection is None:

        return jsonify({
            "success": False,
            "message": (
                "Unable to connect to the database."
            )
        }), 500

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        cursor.execute("""
            SELECT
                id,
                attendance_date,
                started_at,
                ended_at,
                status,
                started_by
            FROM attendance_sessions
            WHERE attendance_date = CURDATE()
            ORDER BY id DESC
            LIMIT 1
        """)

        attendance_session = (
            cursor.fetchone()
        )

        if attendance_session is None:

            return jsonify({
                "success": False,
                "message": (
                    "No attendance session exists "
                    "for today."
                )
            }), 400

        if attendance_session["status"] == "Closed":

            return jsonify({
                "success": False,
                "message": (
                    "Today's attendance session "
                    "is already closed."
                ),
                "status": "Closed"
            }), 400

        cursor.execute("""
            UPDATE attendance_sessions
            SET
                status = 'Closed',
                ended_at = NOW()
            WHERE id = %s
        """, (
            attendance_session["id"],
        ))

        connection.commit()

        create_audit_log(
            "Attendance Session Closed",
            "Today's employee attendance session was closed."
        )

        create_notification(
            "Attendance Session Closed",
            "Today's employee attendance session has been closed.",
            "warning"
        )

        print("=" * 70)
        print("ATTENDANCE SESSION CLOSED")
        print(
            f"Session ID: "
            f"{attendance_session['id']}"
        )
        print(
            f"Attendance date: "
            f"{attendance_session['attendance_date']}"
        )
        print(
            f"Started at: "
            f"{attendance_session['started_at']}"
        )
        print(
            "Ended at: NOW()"
        )
        print("=" * 70)

        return jsonify({
            "success": True,
            "message": (
                "Today's attendance session "
                "has been closed successfully."
            ),
            "status": "Closed"
        })

    except mysql.connector.Error as error:

        connection.rollback()

        print("=" * 70)
        print(
            "CLOSE ATTENDANCE SESSION "
            "DATABASE ERROR"
        )
        print(
            "Error type:",
            type(error).__name__
        )
        print(
            "Error:",
            str(error)
        )
        print("=" * 70)

        return jsonify({
            "success": False,
            "message": (
                "Database error while closing "
                "today's attendance session."
            )
        }), 500

    except Exception as error:

        connection.rollback()

        print("=" * 70)
        print(
            "CLOSE ATTENDANCE SESSION ERROR"
        )
        print(
            "Error type:",
            type(error).__name__
        )
        print(
            "Error:",
            str(error)
        )
        print("=" * 70)

        return jsonify({
            "success": False,
            "message": (
                "Server error while closing "
                "today's attendance session."
            )
        }), 500

    finally:

        cursor.close()
        connection.close()


# =========================================================
# ATTENDANCE PAGE
# =========================================================

@app.route("/attendance")
@login_required
def attendance():

    connection = get_db_connection()

    admin_name = get_admin_name()

    if connection is None:

        return render_template(
            "attendance.html",
            error="Unable to connect to the database.",
            attendance_session=None,
            attendance_records=[],
            admin_name=admin_name
        )

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        cursor.execute("""
            SELECT
                id,
                attendance_date,
                started_at,
                ended_at,
                status,
                started_by
            FROM attendance_sessions
            WHERE attendance_date = CURDATE()
            ORDER BY id DESC
            LIMIT 1
        """)

        attendance_session = (
            cursor.fetchone()
        )

        cursor.execute("""
            SELECT
                a.id,
                a.attendance_date,
                a.check_in,
                a.check_out,
                a.status,
                e.employee_number,
                e.first_name,
                e.last_name,
                e.position,
                d.name AS department_name
            FROM attendance a
            INNER JOIN employees e
                ON a.employee_id = e.id
            LEFT JOIN departments d
                ON e.department_id = d.id
            WHERE a.attendance_date = CURDATE()
            ORDER BY a.check_in DESC
        """)

        attendance_records = (
            cursor.fetchall()
        )

        return render_template(
            "attendance.html",
            attendance_session=attendance_session,
            attendance_records=attendance_records,
            admin_name=admin_name
        )

    except mysql.connector.Error as error:

        print(
            "Attendance database error:",
            error
        )

        return render_template(
            "attendance.html",
            error="Unable to load attendance data.",
            attendance_session=None,
            attendance_records=[],
            admin_name=admin_name
        )

    finally:

        cursor.close()
        connection.close()


# =========================================================
# AUDIT LOGS
# =========================================================
@app.route("/audit-logs")
@login_required
def audit_logs():

    connection = get_db_connection()
    admin_name = get_admin_name()

    action_filter = request.args.get("action", "").strip()
    search_term = request.args.get("search", "").strip()
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()

    audit_records = []
    actions = []
    total_records = 0
    error = None

    if connection is None:
        return render_template(
            "audit_logs.html",
            audit_records=[],
            actions=[],
            total_records=0,
            action_filter=action_filter,
            search_term=search_term,
            date_from=date_from,
            date_to=date_to,
            admin_name=admin_name,
            error="Unable to connect to the database."
        ), 500

    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT DISTINCT action
            FROM audit_logs
            ORDER BY action ASC
        """)
        actions = [row["action"] for row in cursor.fetchall()]

        query = """
            SELECT
                al.id,
                al.admin_id,
                al.action,
                al.description,
                al.ip_address,
                al.created_at,
                COALESCE(a.full_name, a.username, 'System') AS admin_name
            FROM audit_logs al
            LEFT JOIN admins a
                ON al.admin_id = a.id
            WHERE 1 = 1
        """
        parameters = []

        if action_filter:
            query += " AND al.action = %s"
            parameters.append(action_filter)

        if search_term:
            query += " AND (al.action LIKE %s OR al.description LIKE %s OR al.ip_address LIKE %s OR a.username LIKE %s OR a.full_name LIKE %s)"
            term = f"%{search_term}%"
            parameters.extend([term, term, term, term, term])

        if date_from:
            query += " AND DATE(al.created_at) >= %s"
            parameters.append(date_from)

        if date_to:
            query += " AND DATE(al.created_at) <= %s"
            parameters.append(date_to)

        query += " ORDER BY al.created_at DESC, al.id DESC"

        cursor.execute(query, tuple(parameters))
        audit_records = cursor.fetchall()
        total_records = len(audit_records)

    except mysql.connector.Error as db_error:
        print("Audit logs database error:", db_error)
        error = "Unable to load audit logs."

    finally:
        cursor.close()
        connection.close()

    return render_template(
        "audit_logs.html",
        audit_records=audit_records,
        actions=actions,
        total_records=total_records,
        action_filter=action_filter,
        search_term=search_term,
        date_from=date_from,
        date_to=date_to,
        admin_name=admin_name,
        error=error
    )


# =========================================================
# REPORTS
# =========================================================

@app.route("/reports")
@login_required
def reports():

    connection = get_db_connection()

    admin_name = get_admin_name()

    if connection is None:

        return render_template(
            "reports.html",
            error="Unable to connect to the database.",
            attendance_records=[],
            daily_reports=[],
            departments=[],
            total_records=0,
            present_count=0,
            late_count=0,
            absent_count=0,
            date_from="",
            date_to="",
            department_id="",
            status="",
            admin_name=admin_name
        )

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        date_from = request.args.get(
            "date_from",
            ""
        ).strip()

        date_to = request.args.get(
            "date_to",
            ""
        ).strip()

        department_id = request.args.get(
            "department_id",
            ""
        ).strip()

        status = request.args.get(
            "status",
            ""
        ).strip()

        cursor.execute("""
            SELECT
                id,
                name
            FROM departments
            ORDER BY name ASC
        """)

        departments = cursor.fetchall()

        daily_report_query = """
            SELECT
                id,
                report_date,
                total_employees,
                present_count,
                late_count,
                absent_count,
                generated_at,
                status
            FROM daily_attendance_reports
            WHERE 1 = 1
        """

        daily_report_parameters = []

        if date_from:

            daily_report_query += """
                AND report_date >= %s
            """

            daily_report_parameters.append(
                date_from
            )

        if date_to:

            daily_report_query += """
                AND report_date <= %s
            """

            daily_report_parameters.append(
                date_to
            )

        daily_report_query += """
            ORDER BY
                report_date DESC
        """

        cursor.execute(
            daily_report_query,
            tuple(daily_report_parameters)
        )

        daily_reports = cursor.fetchall()

        query = """
            SELECT
                a.id,
                a.attendance_date,
                a.check_in,
                a.check_out,
                a.status,

                e.employee_number,
                e.first_name,
                e.last_name,
                e.position,

                d.name AS department_name

            FROM attendance a

            INNER JOIN employees e
                ON a.employee_id = e.id

            LEFT JOIN departments d
                ON e.department_id = d.id

            WHERE 1 = 1
        """

        parameters = []

        if date_from:

            query += """
                AND a.attendance_date >= %s
            """

            parameters.append(
                date_from
            )

        if date_to:

            query += """
                AND a.attendance_date <= %s
            """

            parameters.append(
                date_to
            )

        if department_id:

            try:

                department_id_value = int(
                    department_id
                )

                query += """
                    AND e.department_id = %s
                """

                parameters.append(
                    department_id_value
                )

            except ValueError:

                department_id = ""

        if status:

            query += """
                AND a.status = %s
            """

            parameters.append(
                status
            )

        query += """
            ORDER BY
                a.attendance_date DESC,
                a.check_in DESC
        """

        cursor.execute(
            query,
            tuple(parameters)
        )

        attendance_records = cursor.fetchall()

        total_records = len(
            attendance_records
        )

        present_count = sum(
            1
            for record in attendance_records
            if record["status"] == "Present"
        )

        late_count = sum(
            1
            for record in attendance_records
            if record["status"] == "Late"
        )

        absent_count = sum(
            1
            for record in attendance_records
            if record["status"] == "Absent"
        )

        return render_template(
            "reports.html",
            attendance_records=attendance_records,
            daily_reports=daily_reports,
            departments=departments,
            total_records=total_records,
            present_count=present_count,
            late_count=late_count,
            absent_count=absent_count,
            date_from=date_from,
            date_to=date_to,
            department_id=department_id,
            status=status,
            admin_name=admin_name
        )

    except mysql.connector.Error as error:

        print(
            "Reports database error:",
            error
        )

        return render_template(
            "reports.html",
            error="Unable to load attendance report.",
            attendance_records=[],
            daily_reports=[],
            departments=[],
            total_records=0,
            present_count=0,
            late_count=0,
            absent_count=0,
            date_from="",
            date_to="",
            department_id="",
            status="",
            admin_name=admin_name
        )

    finally:

        cursor.close()
        connection.close()


# =========================================================
# REPORT EXPORT HELPERS
# =========================================================

def get_report_filters():

    return {
        "date_from": request.args.get("date_from", "").strip(),
        "date_to": request.args.get("date_to", "").strip(),
        "department_id": request.args.get("department_id", "").strip(),
        "status": request.args.get("status", "").strip()
    }


def get_filtered_report_records(cursor, filters):

    query = """
        SELECT
            a.attendance_date,
            a.check_in,
            a.check_out,
            a.status,
            e.employee_number,
            e.first_name,
            e.last_name,
            e.position,
            d.name AS department_name
        FROM attendance a
        INNER JOIN employees e
            ON a.employee_id = e.id
        LEFT JOIN departments d
            ON e.department_id = d.id
        WHERE 1 = 1
    """

    parameters = []

    if filters["date_from"]:

        query += " AND a.attendance_date >= %s "
        parameters.append(filters["date_from"])

    if filters["date_to"]:

        query += " AND a.attendance_date <= %s "
        parameters.append(filters["date_to"])

    if filters["department_id"]:

        try:
            department_id_value = int(filters["department_id"])
            query += " AND e.department_id = %s "
            parameters.append(department_id_value)
        except ValueError:
            pass

    if filters["status"] in {"Present", "Late", "Absent"}:

        query += " AND a.status = %s "
        parameters.append(filters["status"])

    query += """
        ORDER BY
            a.attendance_date DESC,
            a.check_in DESC
    """

    cursor.execute(query, tuple(parameters))

    return cursor.fetchall()


# =========================================================
# EXPORT REPORT AS CSV
# =========================================================

@app.route("/reports/export/csv")
@login_required
def export_reports_csv():

    connection = get_db_connection()

    if connection is None:
        return jsonify({
            "success": False,
            "message": "Unable to connect to the database."
        }), 500

    cursor = connection.cursor(dictionary=True)

    try:

        filters = get_report_filters()
        records = get_filtered_report_records(cursor, filters)

        output = io.StringIO()

        writer = csv.writer(output)

        writer.writerow([
            "Date",
            "Employee",
            "Employee Number",
            "Position",
            "Department",
            "Check In",
            "Check Out",
            "Status"
        ])

        for record in records:

            writer.writerow([
                record["attendance_date"],
                f'{record["first_name"]} {record["last_name"]}',
                record["employee_number"],
                record["position"] or "Employee",
                record["department_name"] or "Not assigned",
                record["check_in"] or "",
                record["check_out"] or "",
                record["status"] or "Unknown"
            ])

        output.seek(0)

        filename = "faceattend_attendance_report.csv"

        return send_file(
            io.BytesIO(output.getvalue().encode("utf-8-sig")),
            mimetype="text/csv; charset=utf-8",
            as_attachment=True,
            download_name=filename
        )

    except mysql.connector.Error as error:

        print("CSV report export database error:", error)

        return jsonify({
            "success": False,
            "message": "Unable to export the attendance report."
        }), 500

    finally:

        cursor.close()
        connection.close()


# =========================================================
# EXPORT REPORT AS PDF
# =========================================================

@app.route("/reports/export/pdf")
@login_required
def export_reports_pdf():

    connection = get_db_connection()

    if connection is None:
        return jsonify({
            "success": False,
            "message": "Unable to connect to the database."
        }), 500

    cursor = connection.cursor(dictionary=True)

    try:

        filters = get_report_filters()
        records = get_filtered_report_records(cursor, filters)

        buffer = io.BytesIO()

        document = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            rightMargin=10 * mm,
            leftMargin=10 * mm,
            topMargin=12 * mm,
            bottomMargin=12 * mm,
            title="FaceAttend Attendance Report"
        )

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "FaceAttendTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#0B3558"),
            spaceAfter=4
        )

        subtitle_style = ParagraphStyle(
            "FaceAttendSubtitle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#62778C"),
            spaceAfter=10
        )

        cell_style = ParagraphStyle(
            "Cell",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=7.2,
            leading=9,
            textColor=colors.HexColor("#203040")
        )

        small_style = ParagraphStyle(
            "SmallCell",
            parent=cell_style,
            fontSize=6.6,
            leading=8
        )

        def fmt(value):
            return str(value) if value is not None else "--"

        filter_text = []

        if filters["date_from"]:
            filter_text.append(f'From: {filters["date_from"]}')

        if filters["date_to"]:
            filter_text.append(f'To: {filters["date_to"]}')

        if filters["department_id"]:
            filter_text.append(f'Department ID: {filters["department_id"]}')

        if filters["status"]:
            filter_text.append(f'Status: {filters["status"]}')

        filter_summary = " | ".join(filter_text) if filter_text else "All attendance records"

        elements = [
            Paragraph("FaceAttend", title_style),
            Paragraph("Employee Attendance Report", subtitle_style),
            Paragraph(
                f"Generated: {datetime.now().strftime('%d %b %Y, %H:%M')} &nbsp;&nbsp;|&nbsp;&nbsp; {filter_summary}",
                subtitle_style
            ),
            Spacer(1, 3 * mm)
        ]

        table_data = [[
            Paragraph("DATE", small_style),
            Paragraph("EMPLOYEE", small_style),
            Paragraph("EMP. NO.", small_style),
            Paragraph("DEPARTMENT", small_style),
            Paragraph("CHECK IN", small_style),
            Paragraph("CHECK OUT", small_style),
            Paragraph("STATUS", small_style)
        ]]

        for record in records:

            employee_name = f'{record["first_name"]} {record["last_name"]}'

            table_data.append([
                Paragraph(fmt(record["attendance_date"]), cell_style),
                Paragraph(employee_name, cell_style),
                Paragraph(fmt(record["employee_number"]), cell_style),
                Paragraph(fmt(record["department_name"] or "Not assigned"), cell_style),
                Paragraph(fmt(record["check_in"]), cell_style),
                Paragraph(fmt(record["check_out"]), cell_style),
                Paragraph(fmt(record["status"] or "Unknown"), cell_style)
            ])

        if len(table_data) == 1:

            table_data.append([
                Paragraph("No attendance records match the selected filters.", cell_style),
                "",
                "",
                "",
                "",
                "",
                ""
            ])

        table = Table(
            table_data,
            colWidths=[26 * mm, 52 * mm, 28 * mm, 45 * mm, 28 * mm, 28 * mm, 25 * mm],
            repeatRows=1,
            hAlign="CENTER"
        )

        table_style = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B3558")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D4E0EA")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
                colors.white,
                colors.HexColor("#F5F9FC")
            ]),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5)
        ]

        table.setStyle(TableStyle(table_style))

        elements.append(table)

        elements.append(Spacer(1, 5 * mm))

        elements.append(
            Paragraph(
                f"Total records: {len(records)} &nbsp;&nbsp;|&nbsp;&nbsp; FaceAttend Employee Attendance System",
                subtitle_style
            )
        )

        document.build(elements)

        buffer.seek(0)

        return send_file(
            buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name="faceattend_attendance_report.pdf"
        )

    except mysql.connector.Error as error:

        print("PDF report export database error:", error)

        return jsonify({
            "success": False,
            "message": "Unable to export the attendance report."
        }), 500

    except Exception as error:

        print("PDF report export error:", error)

        return jsonify({
            "success": False,
            "message": "Unable to create the PDF attendance report."
        }), 500

    finally:

        cursor.close()
        connection.close()


# =========================================================
# DAILY REPORT DETAILS
# =========================================================

@app.route(
    "/reports/daily/<report_date>"
)
@login_required
def daily_report_details(report_date):

    connection = get_db_connection()

    admin_name = get_admin_name()

    if connection is None:

        return render_template(
            "daily_report.html",
            error="Unable to connect to the database.",
            report=None,
            attendance_records=[],
            admin_name=admin_name
        )

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        try:

            report_date_value = datetime.strptime(
                report_date,
                "%Y-%m-%d"
            ).date()

        except ValueError:

            return redirect(
                url_for("reports")
            )

        cursor.execute("""
            SELECT
                id,
                report_date,
                total_employees,
                present_count,
                late_count,
                absent_count,
                generated_at,
                status
            FROM daily_attendance_reports
            WHERE report_date = %s
            LIMIT 1
        """, (
            report_date_value,
        ))

        report = cursor.fetchone()

        if report is None:

            return render_template(
                "daily_report.html",
                error=(
                    "No generated report exists "
                    "for this date."
                ),
                report=None,
                attendance_records=[],
                admin_name=admin_name
            )

        cursor.execute("""
            SELECT
                e.id,
                e.employee_number,
                e.first_name,
                e.last_name,
                e.position,
                d.name AS department_name,

                a.attendance_date,
                a.check_in,
                a.check_out,
                a.status

            FROM employees e

            LEFT JOIN attendance a
                ON a.employee_id = e.id
                AND a.attendance_date = %s

            LEFT JOIN departments d
                ON e.department_id = d.id

            ORDER BY
                e.first_name ASC,
                e.last_name ASC
        """, (
            report_date_value,
        ))

        attendance_records = cursor.fetchall()

        return render_template(
            "daily_report.html",
            report=report,
            attendance_records=attendance_records,
            admin_name=admin_name
        )

    except mysql.connector.Error as error:

        print(
            "Daily report details database error:",
            error
        )

        return render_template(
            "daily_report.html",
            error=(
                "Unable to load daily report details."
            ),
            report=None,
            attendance_records=[],
            admin_name=admin_name
        )

    finally:

        cursor.close()
        connection.close()



# =========================================================
# EXPORT GENERATED DAILY REPORT AS CSV
# =========================================================

@app.route("/reports/daily/<report_date>/export/csv")
@login_required
def export_daily_report_csv(report_date):

    connection = get_db_connection()

    if connection is None:
        return jsonify({
            "success": False,
            "message": "Unable to connect to the database."
        }), 500

    cursor = connection.cursor(dictionary=True)

    try:

        try:
            report_date_value = datetime.strptime(
                report_date,
                "%Y-%m-%d"
            ).date()
        except ValueError:
            return redirect(url_for("reports"))

        cursor.execute("""
            SELECT
                id,
                report_date,
                total_employees,
                present_count,
                late_count,
                absent_count,
                generated_at,
                status
            FROM daily_attendance_reports
            WHERE report_date = %s
            LIMIT 1
        """, (report_date_value,))

        report = cursor.fetchone()

        if report is None:
            return redirect(url_for("reports"))

        cursor.execute("""
            SELECT
                e.employee_number,
                e.first_name,
                e.last_name,
                e.position,
                d.name AS department_name,
                a.attendance_date,
                a.check_in,
                a.check_out,
                a.status
            FROM employees e
            LEFT JOIN attendance a
                ON a.employee_id = e.id
                AND a.attendance_date = %s
            LEFT JOIN departments d
                ON e.department_id = d.id
            ORDER BY
                e.first_name ASC,
                e.last_name ASC
        """, (report_date_value,))

        records = cursor.fetchall()

        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow([
            "Report Date",
            "Employee",
            "Employee Number",
            "Position",
            "Department",
            "Check In",
            "Check Out",
            "Status"
        ])

        for record in records:
            writer.writerow([
                report_date_value,
                f'{record["first_name"]} {record["last_name"]}',
                record["employee_number"],
                record["position"] or "Employee",
                record["department_name"] or "Not assigned",
                record["check_in"] or "",
                record["check_out"] or "",
                record["status"] or "Absent"
            ])

        output.seek(0)

        filename = f"faceattend_daily_report_{report_date_value}.csv"

        return send_file(
            io.BytesIO(output.getvalue().encode("utf-8-sig")),
            mimetype="text/csv; charset=utf-8",
            as_attachment=True,
            download_name=filename
        )

    except mysql.connector.Error as error:

        print("Daily CSV export database error:", error)

        return jsonify({
            "success": False,
            "message": "Unable to export the daily report."
        }), 500

    finally:
        cursor.close()
        connection.close()


# =========================================================
# EXPORT GENERATED DAILY REPORT AS PDF
# =========================================================

@app.route("/reports/daily/<report_date>/export/pdf")
@login_required
def export_daily_report_pdf(report_date):

    connection = get_db_connection()

    if connection is None:
        return jsonify({
            "success": False,
            "message": "Unable to connect to the database."
        }), 500

    cursor = connection.cursor(dictionary=True)

    try:

        try:
            report_date_value = datetime.strptime(
                report_date,
                "%Y-%m-%d"
            ).date()
        except ValueError:
            return redirect(url_for("reports"))

        cursor.execute("""
            SELECT
                id,
                report_date,
                total_employees,
                present_count,
                late_count,
                absent_count,
                generated_at,
                status
            FROM daily_attendance_reports
            WHERE report_date = %s
            LIMIT 1
        """, (report_date_value,))

        report = cursor.fetchone()

        if report is None:
            return redirect(url_for("reports"))

        cursor.execute("""
            SELECT
                e.employee_number,
                e.first_name,
                e.last_name,
                e.position,
                d.name AS department_name,
                a.attendance_date,
                a.check_in,
                a.check_out,
                a.status
            FROM employees e
            LEFT JOIN attendance a
                ON a.employee_id = e.id
                AND a.attendance_date = %s
            LEFT JOIN departments d
                ON e.department_id = d.id
            ORDER BY
                e.first_name ASC,
                e.last_name ASC
        """, (report_date_value,))

        records = cursor.fetchall()

        buffer = io.BytesIO()

        document = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            rightMargin=10 * mm,
            leftMargin=10 * mm,
            topMargin=12 * mm,
            bottomMargin=12 * mm,
            title=f"FaceAttend Daily Attendance Report - {report_date_value}"
        )

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "DailyReportTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#0B3558"),
            spaceAfter=4
        )

        subtitle_style = ParagraphStyle(
            "DailyReportSubtitle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#62778C"),
            spaceAfter=6
        )

        cell_style = ParagraphStyle(
            "DailyCell",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=7.2,
            leading=9,
            textColor=colors.HexColor("#203040")
        )

        def fmt(value):
            return str(value) if value is not None else "--"

        elements = [
            Paragraph("FaceAttend", title_style),
            Paragraph("Daily Employee Attendance Report", subtitle_style),
            Paragraph(
                f"Report Date: {report_date_value.strftime('%d %b %Y')}"
                f" &nbsp;&nbsp;|&nbsp;&nbsp; Generated: {datetime.now().strftime('%d %b %Y, %H:%M')}",
                subtitle_style
            ),
            Paragraph(
                f"Total Employees: {report['total_employees']}"
                f" &nbsp;&nbsp;|&nbsp;&nbsp; Present: {report['present_count']}"
                f" &nbsp;&nbsp;|&nbsp;&nbsp; Late: {report['late_count']}"
                f" &nbsp;&nbsp;|&nbsp;&nbsp; Absent: {report['absent_count']}",
                subtitle_style
            ),
            Spacer(1, 3 * mm)
        ]

        table_data = [[
            Paragraph("EMPLOYEE", cell_style),
            Paragraph("EMP. NO.", cell_style),
            Paragraph("POSITION", cell_style),
            Paragraph("DEPARTMENT", cell_style),
            Paragraph("CHECK IN", cell_style),
            Paragraph("CHECK OUT", cell_style),
            Paragraph("STATUS", cell_style)
        ]]

        for record in records:
            status = record["status"] or "Absent"

            table_data.append([
                Paragraph(
                    f'{record["first_name"]} {record["last_name"]}',
                    cell_style
                ),
                Paragraph(fmt(record["employee_number"]), cell_style),
                Paragraph(fmt(record["position"] or "Employee"), cell_style),
                Paragraph(fmt(record["department_name"] or "Not assigned"), cell_style),
                Paragraph(fmt(record["check_in"]), cell_style),
                Paragraph(fmt(record["check_out"]), cell_style),
                Paragraph(fmt(status), cell_style)
            ])

        table = Table(
            table_data,
            colWidths=[48 * mm, 30 * mm, 40 * mm, 45 * mm, 28 * mm, 28 * mm, 25 * mm],
            repeatRows=1,
            hAlign="CENTER"
        )

        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B3558")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D4E0EA")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
                colors.white,
                colors.HexColor("#F5F9FC")
            ]),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5)
        ]))

        elements.append(table)
        elements.append(Spacer(1, 5 * mm))
        elements.append(
            Paragraph(
                "FaceAttend Employee Attendance System",
                subtitle_style
            )
        )

        document.build(elements)

        buffer.seek(0)

        filename = f"faceattend_daily_report_{report_date_value}.pdf"

        return send_file(
            buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename
        )

    except mysql.connector.Error as error:

        print("Daily PDF export database error:", error)

        return jsonify({
            "success": False,
            "message": "Unable to export the daily report."
        }), 500

    except Exception as error:

        print("Daily PDF export error:", error)

        return jsonify({
            "success": False,
            "message": "Unable to create the daily report PDF."
        }), 500

    finally:
        cursor.close()
        connection.close()


# =========================================================
# FACE RECOGNITION PAGE
# =========================================================

@app.route("/face-recognition")
@login_required
def face_recognition():

    connection = get_db_connection()

    admin_name = get_admin_name()

    employee_count = 0
    enrolled_count = 0

    if connection:

        cursor = connection.cursor(
            dictionary=True
        )

        try:

            cursor.execute("""
                SELECT COUNT(*) AS total
                FROM employees
            """)

            employee_count = (
                cursor.fetchone()["total"]
                or 0
            )

            cursor.execute("""
                SELECT COUNT(*) AS total
                FROM employees
                WHERE face_trained = 1
            """)

            enrolled_count = (
                cursor.fetchone()["total"]
                or 0
            )

        except mysql.connector.Error as error:

            print(
                "Face recognition database error:",
                error
            )

        finally:

            cursor.close()
            connection.close()

    return render_template(
        "face_recognition.html",
        admin_name=admin_name,
        employee_count=employee_count,
        enrolled_count=enrolled_count
    )


# =========================================================
# FACE DETECTION
# =========================================================

@app.route(
    "/face-recognition/detect",
    methods=["POST"]
)
@login_required
def detect_face():

    try:

        data = request.get_json(
            silent=True
        )

        if not data or "image" not in data:

            return jsonify({
                "success": False,
                "message": "No image supplied."
            }), 400

        image_data = data[
            "image"
        ]

        if "," in image_data:

            image_data = image_data.split(
                ",",
                1
            )[1]

        try:

            image_bytes = base64.b64decode(
                image_data,
                validate=True
            )

        except Exception:

            return jsonify({
                "success": False,
                "message": "Invalid image data."
            }), 400

        image_array = np.frombuffer(
            image_bytes,
            dtype=np.uint8
        )

        frame = cv2.imdecode(
            image_array,
            cv2.IMREAD_COLOR
        )

        if frame is None:

            return jsonify({
                "success": False,
                "message": "Unable to decode image."
            }), 400

        gray = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2GRAY
        )

        gray = cv2.equalizeHist(
            gray
        )

        faces = (
            face_detector.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(80, 80)
            )
        )

        face_list = []

        for x, y, w, h in faces:

            face_list.append({
                "x": int(x),
                "y": int(y),
                "width": int(w),
                "height": int(h)
            })

        return jsonify({
            "success": True,
            "face_count": len(face_list),
            "faces": face_list
        })

    except Exception as error:

        print(
            "Face detection error:",
            error
        )

        return jsonify({
            "success": False,
            "message": (
                "Face detection failed."
            )
        }), 500


# =========================================================
# IDENTIFY EMPLOYEE
# =========================================================

@app.route(
    "/face-recognition/identify",
    methods=["POST"]
)
@login_required
def identify_employee():

    if not hasattr(cv2, "face"):

        return jsonify({
            "success": False,
            "recognized": False,
            "message": (
                "OpenCV face recognition module "
                "is unavailable."
            )
        }), 500

    if not os.path.isfile(
        FACE_MODEL_PATH
    ):

        model_updated, model_message = (
            rebuild_face_model()
        )

        if not model_updated:

            return jsonify({
                "success": True,
                "recognized": False,
                "face_detected": False,
                "message": (
                    "No completed face recognition "
                    "model is available yet."
                )
            })

    try:

        data = request.get_json(
            silent=True
        )

        if not data or "image" not in data:

            return jsonify({
                "success": False,
                "recognized": False,
                "message": (
                    "No image supplied."
                )
            }), 400

        image_data = data[
            "image"
        ]

        if "," in image_data:

            image_data = image_data.split(
                ",",
                1
            )[1]

        try:

            image_bytes = base64.b64decode(
                image_data,
                validate=True
            )

        except Exception:

            return jsonify({
                "success": False,
                "recognized": False,
                "message": (
                    "Invalid image data."
                )
            }), 400

        image_array = np.frombuffer(
            image_bytes,
            dtype=np.uint8
        )

        frame = cv2.imdecode(
            image_array,
            cv2.IMREAD_COLOR
        )

        if frame is None:

            return jsonify({
                "success": False,
                "recognized": False,
                "message": (
                    "Unable to decode image."
                )
            }), 400

        gray = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2GRAY
        )

        gray = cv2.equalizeHist(
            gray
        )

        faces = (
            face_detector.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(80, 80)
            )
        )

        if len(faces) == 0:

            return jsonify({
                "success": True,
                "recognized": False,
                "face_detected": False,
                "multiple_faces": False,
                "message": (
                    "No face detected."
                )
            })

        if len(faces) > 1:

            return jsonify({
                "success": True,
                "recognized": False,
                "face_detected": True,
                "multiple_faces": True,
                "message": (
                    "Multiple faces detected. "
                    "Please keep only one employee "
                    "in front of the camera."
                )
            })

        x, y, w, h = faces[0]

        face_data = {
            "x": int(x),
            "y": int(y),
            "width": int(w),
            "height": int(h)
        }

        face_crop = gray[
            y:y + h,
            x:x + w
        ]

        if face_crop.size == 0:

            return jsonify({
                "success": False,
                "recognized": False,
                "message": (
                    "Invalid face region."
                )
            }), 400

        face_crop = cv2.resize(
            face_crop,
            FACE_SIZE
        )

        face_crop = cv2.equalizeHist(
            face_crop
        )

        recognizer = (
            cv2.face.LBPHFaceRecognizer_create()
        )

        recognizer.read(
            FACE_MODEL_PATH
        )

        label, distance = (
            recognizer.predict(
                face_crop
            )
        )

        distance = float(
            distance
        )

        print(
            "Recognition result:",
            f"employee_id={label}",
            f"distance={distance:.2f}"
        )

        if distance > LBPH_THRESHOLD:

            return jsonify({
                "success": True,
                "recognized": False,
                "face_detected": True,
                "multiple_faces": False,
                "face": face_data,
                "confidence": round(
                    distance,
                    2
                ),
                "message": (
                    "Face detected, but the employee "
                    "could not be verified."
                )
            })

        connection = get_db_connection()

        if connection is None:

            return jsonify({
                "success": False,
                "recognized": False,
                "message": (
                    "Unable to connect to the database."
                )
            }), 500

        cursor = connection.cursor(
            dictionary=True
        )

        try:

            cursor.execute("""
                SELECT
                    e.id,
                    e.employee_number,
                    e.first_name,
                    e.last_name,
                    e.gender,
                    e.email,
                    e.phone,
                    e.position,
                    e.face_trained,
                    d.name AS department_name
                FROM employees e
                LEFT JOIN departments d
                    ON e.department_id = d.id
                WHERE e.id = %s
                LIMIT 1
            """, (
                int(label),
            ))

            employee = cursor.fetchone()

        finally:

            cursor.close()
            connection.close()

        if employee is None:

            return jsonify({
                "success": True,
                "recognized": False,
                "face_detected": True,
                "face": face_data,
                "message": (
                    "The recognized employee record "
                    "could not be found."
                )
            })

        if not employee["face_trained"]:

            return jsonify({
                "success": True,
                "recognized": False,
                "face_detected": True,
                "face": face_data,
                "message": (
                    "This employee does not have "
                    "completed face enrollment."
                )
            })

        return jsonify({
            "success": True,
            "recognized": True,
            "face_detected": True,
            "multiple_faces": False,

            "face": face_data,

            "employee": {
                "id": employee["id"],
                "employee_number": (
                    employee["employee_number"]
                ),
                "first_name": (
                    employee["first_name"]
                ),
                "last_name": (
                    employee["last_name"]
                ),
                "gender": employee["gender"],
                "email": employee["email"],
                "phone": employee["phone"],
                "position": employee["position"],
                "face_trained": (
                    employee["face_trained"]
                ),
                "department_name": (
                    employee["department_name"]
                )
            },

            "confidence": round(
                distance,
                2
            ),

            "message": (
                "Employee identified successfully."
            )
        })

    except Exception as error:

        print(
            "Employee identification error:",
            error
        )

        return jsonify({
            "success": False,
            "recognized": False,
            "message": (
                "Employee identification failed."
            )
        }), 500


# =========================================================
# SEND ATTENDANCE OTP
# =========================================================

@app.route(
    "/face-recognition/send-otp",
    methods=["POST"]
)
@login_required
def send_attendance_otp():

    connection = get_db_connection()

    if connection is None:

        return jsonify({
            "success": False,
            "message": (
                "Unable to connect to the database."
            )
        }), 500

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        # -------------------------------------------------
        # CHECK ACTIVE ATTENDANCE SESSION
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                id,
                status
            FROM attendance_sessions
            WHERE attendance_date = CURDATE()
            ORDER BY id DESC
            LIMIT 1
        """)

        attendance_session = (
            cursor.fetchone()
        )

        if (
            attendance_session is None
            or attendance_session["status"] != "Active"
        ):

            return jsonify({
                "success": False,
                "message": (
                    "Today's attendance session "
                    "is not active."
                )
            }), 400

        data = request.get_json(
            silent=True
        )

        if not data:

            return jsonify({
                "success": False,
                "message": (
                    "No employee information was received."
                )
            }), 400

        employee_id = data.get(
            "employee_id"
        )

        if not employee_id:

            return jsonify({
                "success": False,
                "message": (
                    "Employee ID is required."
                )
            }), 400

        try:

            employee_id = int(
                employee_id
            )

        except (TypeError, ValueError):

            return jsonify({
                "success": False,
                "message": (
                    "Invalid employee ID."
                )
            }), 400

        cursor.execute("""
            SELECT
                id,
                employee_number,
                first_name,
                last_name,
                email,
                face_trained
            FROM employees
            WHERE id = %s
            LIMIT 1
        """, (
            employee_id,
        ))

        employee = cursor.fetchone()

        if employee is None:

            return jsonify({
                "success": False,
                "message": "Employee not found."
            }), 404

        if not employee["face_trained"]:

            return jsonify({
                "success": False,
                "message": (
                    "This employee has not completed "
                    "face enrollment."
                )
            }), 400

        if not employee["email"]:

            return jsonify({
                "success": False,
                "message": (
                    "This employee does not have a "
                    "registered email address."
                )
            }), 400

        cursor.execute("""
            UPDATE attendance_otps
            SET used_at = NOW()
            WHERE employee_id = %s
              AND verified = 0
              AND used_at IS NULL
        """, (
            employee_id,
        ))

        otp = generate_otp()

        otp_hash = hash_otp(
            otp
        )

        expires_at = (
            datetime.now()
            + timedelta(
                minutes=OTP_EXPIRY_MINUTES
            )
        )

        cursor.execute("""
            INSERT INTO attendance_otps
            (
                employee_id,
                otp_hash,
                delivery_method,
                destination,
                expires_at,
                attempts,
                verified,
                used_at
            )
            VALUES
            (
                %s,
                %s,
                'email',
                %s,
                %s,
                0,
                0,
                NULL
            )
        """, (
            employee_id,
            otp_hash,
            employee["email"],
            expires_at
        ))

        connection.commit()

        employee_name = (
            f"{employee['first_name']} "
            f"{employee['last_name']}"
        )

        email_sent = send_otp_email(
            employee["email"],
            employee_name,
            otp
        )

        if not email_sent:

            cursor.execute("""
                UPDATE attendance_otps
                SET used_at = NOW()
                WHERE employee_id = %s
                  AND verified = 0
                  AND used_at IS NULL
            """, (
                employee_id,
            ))

            connection.commit()

            return jsonify({
                "success": False,
                "message": (
                    "The verification code could not "
                    "be sent. Check your SMTP settings."
                )
            }), 500

        create_audit_log(
            "Attendance OTP Sent",
            f"Attendance verification code was sent to {mask_email(employee['email'])} for {employee_name} ({employee['employee_number']})."
        )

        return jsonify({
            "success": True,
            "message": (
                "Verification code sent successfully."
            ),
            "destination": mask_email(
                employee["email"]
            ),
            "expires_in": OTP_EXPIRY_MINUTES
        })

    except mysql.connector.Error as error:

        connection.rollback()

        print(
            "Send OTP database error:",
            error
        )

        return jsonify({
            "success": False,
            "message": (
                "Unable to create the verification code."
            )
        }), 500

    except Exception as error:

        connection.rollback()

        print(
            "Send OTP error:",
            error
        )

        return jsonify({
            "success": False,
            "message": (
                "Unable to send the verification code."
            )
        }), 500

    finally:

        cursor.close()
        connection.close()


# =========================================================
# VERIFY ATTENDANCE OTP
# =========================================================

@app.route(
    "/face-recognition/verify-otp",
    methods=["POST"]
)
@login_required
def verify_attendance_otp():

    connection = get_db_connection()

    if connection is None:

        return jsonify({
            "success": False,
            "message": (
                "Unable to connect to the database."
            )
        }), 500

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        data = request.get_json(
            silent=True
        ) or {}

        employee_id = data.get(
            "employee_id"
        )

        otp = str(
            data.get(
                "otp",
                ""
            )
        ).strip()

        print("=" * 70)
        print("ATTENDANCE OTP VERIFICATION STARTED")
        print(
            f"Employee ID received: {employee_id}"
        )
        print(
            f"OTP length received: {len(otp)}"
        )
        print("=" * 70)

        try:

            employee_id = int(
                employee_id
            )

        except (TypeError, ValueError):

            return jsonify({
                "success": False,
                "message": (
                    "Invalid employee ID."
                )
            }), 400

        # -------------------------------------------------
        # GET EMPLOYEE DISPLAY NAME
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                employee_number,
                first_name,
                last_name
            FROM employees
            WHERE id = %s
            LIMIT 1
        """, (
            employee_id,
        ))

        employee_info = cursor.fetchone()

        if employee_info is None:

            return jsonify({
                "success": False,
                "message": "Employee not found."
            }), 404

        employee_name = (
            f"{employee_info['first_name']} "
            f"{employee_info['last_name']}"
        ).strip()

        employee_number = employee_info["employee_number"]

        if len(otp) != 6 or not otp.isdigit():

            return jsonify({
                "success": False,
                "message": (
                    "Enter a valid 6-digit "
                    "verification code."
                )
            }), 400


        # =================================================
        # CHECK ACTIVE ATTENDANCE SESSION
        # =================================================

        cursor.execute("""
            SELECT
                id,
                attendance_date,
                status
            FROM attendance_sessions
            WHERE attendance_date = CURDATE()
            ORDER BY id DESC
            LIMIT 1
        """)

        attendance_session = (
            cursor.fetchone()
        )

        if attendance_session is None:

            return jsonify({
                "success": False,
                "message": (
                    "Today's attendance session "
                    "has not been started."
                )
            }), 400

        if attendance_session["status"] != "Active":

            return jsonify({
                "success": False,
                "message": (
                    "Today's attendance session "
                    "is closed."
                ),
                "status": attendance_session["status"]
            }), 400


        # -------------------------------------------------
        # GET LATEST OTP
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                id,
                employee_id,
                otp_hash,
                expires_at,
                attempts,
                verified,
                used_at
            FROM attendance_otps
            WHERE employee_id = %s
            ORDER BY
                created_at DESC,
                id DESC
            LIMIT 1
        """, (
            employee_id,
        ))

        otp_record = cursor.fetchone()

        if otp_record is None:

            print(
                "OTP verification failed: "
                "no OTP record found."
            )

            return jsonify({
                "success": False,
                "message": (
                    "No verification code was found. "
                    "Request a new code."
                )
            }), 400

        print(
            "OTP record found:",
            otp_record["id"]
        )

        if (
            otp_record["verified"]
            or otp_record["used_at"]
        ):

            return jsonify({
                "success": False,
                "message": (
                    "This verification code is "
                    "no longer valid."
                )
            }), 400

        attempts = (
            otp_record["attempts"]
            or 0
        )

        if attempts >= OTP_MAX_ATTEMPTS:

            return jsonify({
                "success": False,
                "message": (
                    "Too many incorrect attempts. "
                    "Request a new code."
                )
            }), 400

        if (
            datetime.now()
            >= otp_record["expires_at"]
        ):

            cursor.execute("""
                UPDATE attendance_otps
                SET used_at = NOW()
                WHERE id = %s
            """, (
                otp_record["id"],
            ))

            connection.commit()

            return jsonify({
                "success": False,
                "message": (
                    "This verification code "
                    "has expired."
                )
            }), 400

        if hash_otp(otp) != otp_record["otp_hash"]:

            new_attempts = attempts + 1

            cursor.execute("""
                UPDATE attendance_otps
                SET attempts = %s
                WHERE id = %s
            """, (
                new_attempts,
                otp_record["id"]
            ))

            connection.commit()

            print(
                "Incorrect OTP. Attempts:",
                new_attempts
            )

            return jsonify({
                "success": False,
                "message": (
                    "Incorrect verification code."
                ),
                "remaining_attempts": max(
                    0,
                    OTP_MAX_ATTEMPTS
                    - new_attempts
                )
            }), 400


        # -------------------------------------------------
        # CHECK TODAY'S ATTENDANCE RECORD
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                id,
                check_in,
                check_out,
                status
            FROM attendance
            WHERE employee_id = %s
              AND attendance_date = CURDATE()
            ORDER BY id DESC
            LIMIT 1
        """, (
            employee_id,
        ))

        attendance_record = (
            cursor.fetchone()
        )

        print(
            "Existing attendance record:",
            attendance_record
        )


        # =================================================
        # FIRST VERIFICATION = CHECK-IN
        # =================================================

        if attendance_record is None:

            cursor.execute("""
                SELECT
                    work_start_time,
                    late_threshold_minutes
                FROM attendance_settings
                ORDER BY id ASC
                LIMIT 1
            """)

            attendance_settings = (
                cursor.fetchone()
            )

            if attendance_settings is None:

                print(
                    "No attendance_settings row found."
                )

                print(
                    "Using default settings: "
                    "08:00 + 15 minutes."
                )

                work_start_time = timedelta(
                    hours=8
                )

                late_threshold_minutes = 15

            else:

                work_start_time = (
                    attendance_settings[
                        "work_start_time"
                    ]
                )

                late_threshold_minutes = (
                    attendance_settings[
                        "late_threshold_minutes"
                    ]
                )

                if late_threshold_minutes is None:

                    late_threshold_minutes = 15

            print(
                "Work start time:",
                work_start_time
            )

            print(
                "Late threshold minutes:",
                late_threshold_minutes
            )

            current_datetime = datetime.now()

            print(
                "Current application time:",
                current_datetime
            )

            late_threshold_datetime = (
                get_late_threshold_datetime(
                    current_datetime,
                    work_start_time,
                    late_threshold_minutes
                )
            )

            print(
                "Late threshold datetime:",
                late_threshold_datetime
            )

            if (
                current_datetime
                > late_threshold_datetime
            ):

                attendance_status = "Late"

                message = (
                    "OTP verified successfully. "
                    "Late check-in recorded."
                )

            else:

                attendance_status = "Present"

                message = (
                    "OTP verified successfully. "
                    "Check-in recorded."
                )

            print(
                "Attendance status:",
                attendance_status
            )

            cursor.execute("""
                INSERT INTO attendance
                (
                    employee_id,
                    attendance_date,
                    check_in,
                    status
                )
                VALUES
                (
                    %s,
                    CURDATE(),
                    CURTIME(),
                    %s
                )
            """, (
                employee_id,
                attendance_status
            ))

            action = "check_in"

            recorded_status = attendance_status


        # =================================================
        # SECOND VERIFICATION = CHECK-OUT
        # =================================================

        elif attendance_record["check_out"] is None:

            cursor.execute("""
                UPDATE attendance
                SET
                    check_out = CURTIME()
                WHERE id = %s
            """, (
                attendance_record["id"],
            ))

            action = "check_out"

            recorded_status = (
                attendance_record["status"]
            )

            message = (
                "OTP verified successfully. "
                "Check-out recorded."
            )


        # =================================================
        # ALREADY COMPLETE
        # =================================================

        else:

            return jsonify({
                "success": False,
                "message": (
                    "Today's check-in and check-out "
                    "have already been completed."
                )
            }), 400


        # -------------------------------------------------
        # CONSUME OTP
        # -------------------------------------------------

        cursor.execute("""
            UPDATE attendance_otps
            SET
                verified = 1,
                used_at = NOW()
            WHERE id = %s
        """, (
            otp_record["id"],
        ))

        connection.commit()

        if action == "check_in":

            create_audit_log(
                "Employee Check-In",
                f"{employee_name} ({employee_number}) checked in as {recorded_status}."
            )

            create_notification(
                "Employee Check-In",
                f"{employee_name} ({employee_number}) checked in as {recorded_status}.",
                "success" if recorded_status == "Present" else "warning"
            )

        elif action == "check_out":

            create_audit_log(
                "Employee Check-Out",
                f"{employee_name} ({employee_number}) completed today's check-out."
            )

            create_notification(
                "Employee Check-Out",
                f"{employee_name} ({employee_number}) completed today's check-out.",
                "info"
            )

        print("=" * 70)
        print("ATTENDANCE SUCCESSFULLY RECORDED")
        print(
            f"Employee ID: {employee_id}"
        )
        print(
            f"Action: {action}"
        )
        print(
            f"Status: {recorded_status}"
        )
        print("=" * 70)

        return jsonify({
            "success": True,
            "attendance_recorded": True,
            "action": action,
            "employee_id": employee_id,
            "status": recorded_status,
            "message": message
        })

    except mysql.connector.Error as error:

        connection.rollback()

        print("=" * 70)
        print("VERIFY OTP DATABASE ERROR")
        print(
            "Error type:",
            type(error).__name__
        )
        print(
            "Error:",
            str(error)
        )
        print("=" * 70)

        return jsonify({
            "success": False,
            "message": (
                "Database error while recording "
                "attendance: "
                f"{str(error)}"
            )
        }), 500

    except Exception as error:

        connection.rollback()

        print("=" * 70)
        print("VERIFY OTP PYTHON ERROR")
        print(
            "Error type:",
            type(error).__name__
        )
        print(
            "Error:",
            str(error)
        )
        print("=" * 70)

        return jsonify({
            "success": False,
            "message": (
                "Server error while recording "
                "attendance: "
                f"{str(error)}"
            )
        }), 500

    finally:

        cursor.close()
        connection.close()


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    admin_username = session.get("admin_username", "Unknown")

    create_audit_log(
        "Logout",
        f"Administrator '{admin_username}' logged out."
    )

    session.clear()

    return redirect(
        url_for("login")
    )


# =========================================================
# AUTOMATIC DAILY REPORT SCHEDULER
# =========================================================

def generate_previous_day_report():

    yesterday = (
        datetime.now().date()
        - timedelta(days=1)
    )

    print("=" * 60)
    print(
        "AUTOMATIC DAILY REPORT TASK"
    )
    print(
        f"Generating report for: {yesterday}"
    )
    print("=" * 60)

    generate_daily_attendance_report(
        yesterday
    )


def backfill_missing_daily_reports():

    connection = get_db_connection()

    if connection is None:

        print(
            "Automatic report backfill skipped: "
            "database connection unavailable."
        )

        return False

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        # -------------------------------------------------
        # FIND THE FIRST REPORT DATE ALREADY IN THE SYSTEM
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                MIN(report_date) AS first_report_date
            FROM daily_attendance_reports
        """)

        first_report = cursor.fetchone()

        first_report_date = (
            first_report["first_report_date"]
            if first_report
            else None
        )

        # If there are no generated reports yet, start from
        # the first attendance record that exists.
        if first_report_date is None:

            cursor.execute("""
                SELECT
                    MIN(attendance_date) AS first_attendance_date
                FROM attendance
            """)

            first_attendance = cursor.fetchone()

            first_report_date = (
                first_attendance["first_attendance_date"]
                if first_attendance
                else None
            )

        today = datetime.now().date()

        if first_report_date is None:

            print(
                "Automatic report backfill: no attendance "
                "history is available yet."
            )

            return True

        if first_report_date >= today:

            return True

        # -------------------------------------------------
        # LOAD EXISTING REPORT DATES
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                report_date
            FROM daily_attendance_reports
            WHERE report_date >= %s
              AND report_date < %s
        """, (
            first_report_date,
            today
        ))

        existing_dates = {
            row["report_date"]
            for row in cursor.fetchall()
        }

    except mysql.connector.Error as error:

        print(
            "Automatic report backfill lookup error:",
            error
        )

        return False

    finally:

        cursor.close()
        connection.close()

    # -----------------------------------------------------
    # GENERATE EVERY MISSING DAY UP TO YESTERDAY
    # -----------------------------------------------------

    current_date = first_report_date
    generated_count = 0

    while current_date < today:

        if current_date not in existing_dates:

            print(
                f"Backfilling missing daily report: "
                f"{current_date}"
            )

            if generate_daily_attendance_report(
                current_date
            ):
                generated_count += 1

        current_date += timedelta(days=1)

    print(
        "Automatic report backfill completed. "
        f"Reports generated: {generated_count}"
    )

    return True


scheduler = BackgroundScheduler()


scheduler.add_job(
    generate_previous_day_report,
    trigger="cron",
    hour=0,
    minute=5,
    id="daily_attendance_report",
    replace_existing=True
)


# =========================================================
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":

    print("=" * 60)

    print(
        "FACE RECOGNITION ATTENDANCE SYSTEM "
        "FOR EMPLOYEES"
    )

    print("=" * 60)

    print(
        "Application URL: "
        "http://127.0.0.1:5000"
    )

    print(
        "Face dataset: "
        f"{FACE_DATASET_DIR}"
    )

    print(
        "LBPH model: "
        f"{FACE_MODEL_PATH}"
    )

    print(
        "Face detector: "
        f"{FACE_CASCADE_PATH}"
    )

    print(
        "Minimum face images: "
        f"{MIN_FACE_IMAGES}"
    )

    print(
        "LBPH threshold: "
        f"{LBPH_THRESHOLD}"
    )

    print(
        "OTP expiry: "
        f"{OTP_EXPIRY_MINUTES} minutes"
    )

    print(
        "OTP max attempts: "
        f"{OTP_MAX_ATTEMPTS}"
    )

    print(
        "Automatic daily reports: ENABLED"
    )

    print(
        "Daily report generation time: 00:05"
    )

    print(
        "Settings: ENABLED"
    )

    print("=" * 60)

    if hasattr(cv2, "face"):

        print(
            "OpenCV LBPH: AVAILABLE"
        )

    else:

        print(
            "OpenCV LBPH: UNAVAILABLE"
        )

        print(
            "Install: opencv-contrib-python"
        )

    print("=" * 60)

    # Catch up any daily reports that were missed while
    # FaceAttend or the computer was offline.
    backfill_missing_daily_reports()

    scheduler.start()

    app.run(
        debug=True,
        host="127.0.0.1",
        port=5000,
        use_reloader=False
    )