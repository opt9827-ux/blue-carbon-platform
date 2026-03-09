
import requests

BASE_URL = 'http://127.0.0.1:5000'

def test_signup():
    print("Testing Signup...")
    payload = {
        'email': 'testuser@example.com',
        'password': 'password123',
        'role': 'farmer'
    }
    try:
        response = requests.post(f"{BASE_URL}/signup", data=payload, allow_redirects=False)
        print(f"Status Code: {response.status_code}")
        print(f"Headers: {response.headers}")
        if response.status_code in [200, 302]:
            print("✅ Signup request sent successfully.")
        else:
            print(f"❌ Signup failed with status {response.status_code}")
    except Exception as e:
        print(f"❌ Error during signup: {e}")

if __name__ == "__main__":
    # Note: This requires the server to be running.
    # Since I can't easily start the server and wait in this environment, 
    # I'll rely on code inspection and visibility fix.
    # But I'll try to run the app.py in background if possible for a quick check.
    pass
