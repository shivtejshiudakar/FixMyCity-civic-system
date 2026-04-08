import sys
try:
    from app import app
    print("App imported successfully! No syntax errors in app.py")
    
    with app.test_client() as client:
        # Test index page
        res = client.get('/')
        assert res.status_code == 200
        print("GET / OK")
        
        # Test about page
        res = client.get('/about')
        assert res.status_code == 200
        print("GET /about OK")
        
        # Test register page
        res = client.get('/register')
        assert res.status_code == 200
        print("GET /register OK")
        
        print("All basic routing tests passed.")
except Exception as e:
    print(f"Error starting app: {e}")
    sys.exit(1)
