from werkzeug.security import generate_password_hash

from database import get_db_connection


USERNAME = "admin"
PASSWORD = "admin123"


connection = get_db_connection()

if connection is None:
    print("DATABASE CONNECTION FAILED!")
    exit()


cursor = connection.cursor()


# Check whether admin exists
cursor.execute(
    "SELECT id FROM admins WHERE username = %s",
    (USERNAME,)
)

admin = cursor.fetchone()


if admin:

    # Update existing admin password
    password_hash = generate_password_hash(PASSWORD)

    cursor.execute(
        """
        UPDATE admins
        SET password_hash = %s
        WHERE username = %s
        """,
        (password_hash, USERNAME)
    )

    connection.commit()

    print("ADMIN PASSWORD RESET SUCCESSFULLY!")
    print("Username: admin")
    print("Password: admin123")


else:

    # Create admin if it does not exist
    password_hash = generate_password_hash(PASSWORD)

    cursor.execute(
        """
        INSERT INTO admins
        (username, password_hash, full_name)
        VALUES (%s, %s, %s)
        """,
        (
            USERNAME,
            password_hash,
            "System Administrator"
        )
    )

    connection.commit()

    print("ADMIN ACCOUNT CREATED SUCCESSFULLY!")
    print("Username: admin")
    print("Password: admin123")


cursor.close()
connection.close()