import subprocess
import requests
import time
import os

OLLAMA_SERVER_URL = "http://localhost:11434"

def is_ollama_running():
    try:
        response = requests.get(f"{OLLAMA_SERVER_URL}/api/version")
        return response.status_code == 200
    except:
        return False

def start_ollama():
    try:
        subprocess.Popen(["ollama", "serve"])
        # Wait for Ollama to start
        for _ in range(5):  # Try for 5 seconds
            if is_ollama_running():
                return True
            time.sleep(1)
        return False
    except Exception as e:
        print("Error starting Ollama:", e)
        return False

def init_ollama():
    if not is_ollama_running():
        if not start_ollama():
            os.system("ollama serve deepseek-R1 &")
