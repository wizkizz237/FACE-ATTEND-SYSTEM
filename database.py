import os

import mysql.connector
from mysql.connector import Error

from dotenv import load_dotenv


# =========================================================
# LOAD ENVIRONMENT VARIABLES
# =========================================================

load_dotenv()


# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_db_connection():

    try:

        connection = mysql.connector.connect(

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

            # IMPORTANT:
            # Use Python implementation instead
            # of the crashing C extension.
            use_pure=True
        )

        return connection

    except Error as error:

        print(
            f"Database connection error: {error}"
        )

        return None


# =========================================================
# DATABASE CONNECTION TEST
# =========================================================

if __name__ == "__main__":

    connection = get_db_connection()

    if connection:

        print(
            "DATABASE CONNECTED SUCCESSFULLY!"
        )

        connection.close()

    else:

        print(
            "DATABASE CONNECTION FAILED!"
        )