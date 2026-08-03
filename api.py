import requests
import json
from config import API_URL, API_KEY

def search_api(query):
    """Search the OSINT API"""
    try:
        url = f"{API_URL}?query={query}&key={API_KEY}"
        response = requests.get(url, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == True:
                return data.get("data", {})
            else:
                return {"error": data.get("error", "Unknown error")}
        else:
            return {"error": f"API Error: {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}

def extract_records(data):
    """Extract all records from API response"""
    records = []
    for source_name, source_data in data.items():
        if isinstance(source_data, dict):
            recs = source_data.get("records", [])
            for record in recs:
                if isinstance(record, dict):
                    records.append(record)
    return records