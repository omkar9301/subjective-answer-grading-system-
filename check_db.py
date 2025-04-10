from app import db, app  # Import Flask app and db

with app.app_context():  # Push application context
    with db.engine.connect() as connection:  # Establish connection
        result = connection.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in result]
        print("Tables in database:", tables)
