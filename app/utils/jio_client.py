import requests
from app.config import settings

def jio_headers(api_key, agent_id):
    return {
        "x-apikey": api_key,
        "agentid": agent_id,
        "Content-Type": "application/json"
    }

def check_capability(api_key, agent_id, mobile):
    url = f"{settings.JIO_BASE_URL}/api/v1/checkCapability"
    payload = {"PhoneNumbers": mobile}

    resp = requests.post(url, json=payload, headers=jio_headers(api_key, agent_id), timeout=10)
    return resp.status_code, resp.json()

def upload_file(api_key, agent_id, file_path):
    url = f"{settings.JIO_BASE_URL}/api/v1/uploadFile"

    headers = {
        "x-apikey": api_key,
        "agentid": agent_id
    }

    with open(file_path, "rb") as f:
        files = {"file": f}
        resp = requests.post(url, files=files, headers=headers, timeout=30)

    return resp.status_code, resp.json()

def send_message(api_key, agent_id, payload):
    url = f"{settings.JIO_BASE_URL}/api/v1/sendMessage"
    resp = requests.post(url, json=payload, headers=jio_headers(api_key, agent_id), timeout=10)
    return resp.status_code, resp.json()

