from app import app

if __name__ == "__main__":
    # This is only used when running directly with Gunicorn
    # Vercel will use the app variable from app.py
    app.run()