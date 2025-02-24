from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from pydantic import BaseModel
import subprocess
import requests
import time
import uvicorn
import os
import signal
import logging
import json

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

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()

# Define request model
class QueryRequest(BaseModel):
    prompt: str

@app.get("/", response_class=HTMLResponse)
async def get_chat_interface():
    """
    Serve the chat interface HTML page.
    """
    logger.info("Serving chat interface HTML page")
    return FileResponse("index.html")

# Store chat history
chat_history = []

def save_chat_history():
    """
    Save chat history to a file.
    """
    with open("chat_history.json", "w") as file:
        json.dump(chat_history, file)

def load_chat_history():
    """
    Load chat history from a file.
    """
    global chat_history
    if os.path.exists("chat_history.json"):
        with open("chat_history.json", "r") as file:
            chat_history = json.load(file)

@app.get("/history/")
async def get_chat_history():
    """
    Get the chat history.
    """
    logger.info("Retrieving chat history")
    logger.info(f"Chat history: {chat_history}")
    return {"history": chat_history}

@app.post("/reset/")
async def reset_chat_history():
    """
    Reset the chat history.
    """
    global chat_history
    chat_history = []
    save_chat_history()
    logger.info("Chat history reset")
    return {"message": "Chat history reset"}

@app.post("/query/")
async def query_model(request: QueryRequest):
    """
    Send a query to the Ollama model and return the response.
    """
    model_name = "deepseek-r1:latest"  # Replace with the correct model name
    logger.info(f"Received query: {request.prompt}")
    try:
        # Add the user's prompt to the chat history
        chat_history.append({"role": "user", "content": request.prompt})
        
        # Create the full prompt with chat history
        full_prompt = "\n".join([f"{entry['role']}: {entry['content']}" for entry in chat_history])
        
        response = requests.post(f"{OLLAMA_SERVER_URL}/api/generate", json={
            "model": model_name,
            "prompt": full_prompt
        }, stream=True)
        
        def response_generator():
            full_response = ""
            for line in response.iter_lines():
                if line:
                    part = line.decode('utf-8')
                    logger.info(f"Response part: {part}")
                    part_json = json.loads(part)
                    full_response += part_json["response"]
                    yield part_json["response"]
                    if part_json.get("done", False):
                        break
            # Add the model's response to the chat history
            chat_history.append({"role": "ollama", "content": full_response})
            # Save chat history to file
            save_chat_history()
            logger.info(f"Full response from Ollama: {full_response}")

        return StreamingResponse(response_generator(), media_type="text/plain")
    except Exception as e:
        logger.error(f"Exception occurred: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/shutdown/")
async def shutdown():
    """
    Shutdown the server gracefully
    """
    logger.info("Server is shutting down...")
    os.kill(os.getpid(), signal.SIGTERM)
    return {"message": "Server shutting down..."}

@app.get("/chats/index.json", response_class=FileResponse)
async def get_chat_index():
    """
    Serve the chats/index.json file.
    """
    logger.info("Serving chats/index.json file")
    if not os.path.exists("chats/index.json"):
        with open("chats/index.json", "w") as file:
            json.dump({}, file)
    return FileResponse("chats/index.json")

@app.get("/chats/{chat_id}.json", response_class=FileResponse)
async def get_chat_history_file(chat_id: int):
    """
    Serve individual chat history files.
    """
    logger.info(f"Serving chat history file for chat ID: {chat_id}")
    chat_file = f"chats/{chat_id}.json"
    if not os.path.exists(chat_file):
        raise HTTPException(status_code=404, detail="Chat history file not found")
    return FileResponse(chat_file)

@app.put("/chats/{chat_id}/rename/")
async def rename_chat_history(chat_id: int, new_summary: str):
    """
    Rename chat history files.
    """
    logger.info(f"Renaming chat history file for chat ID: {chat_id} to {new_summary}")
    index_file = "chats/index.json"
    if not os.path.exists(index_file):
        raise HTTPException(status_code=404, detail="Index file not found")
    with open(index_file, "r") as file:
        index_data = json.load(file)
    if str(chat_id) not in index_data:
        raise HTTPException(status_code=404, detail="Chat ID not found in index")
    index_data[str(chat_id)] = new_summary
    with open(index_file, "w") as file:
        json.dump(index_data, file)
    return {"message": "Chat history renamed"}

@app.delete("/chats/{chat_id}/delete/")
async def delete_chat_history(chat_id: int):
    """
    Delete chat history files.
    """
    logger.info(f"Deleting chat history file for chat ID: {chat_id}")
    chat_file = f"chats/{chat_id}.json"
    index_file = "chats/index.json"
    if not os.path.exists(chat_file):
        raise HTTPException(status_code=404, detail="Chat history file not found")
    os.remove(chat_file)
    if os.path.exists(index_file):
        with open(index_file, "r") as file:
            index_data = json.load(file)
        if str(chat_id) in index_data:
            del index_data[str(chat_id)]
            with open(index_file, "w") as file:
                json.dump(index_data, file)
    return {"message": "Chat history deleted"}

@app.post("/reset/")
async def reset_chat_history():
    """
    Reset the chat history.
    """
    global chat_history
    chat_history = []
    save_chat_history()
    logger.info("Chat history reset")
    # Clear all chat history files
    chats_folder = "chats"
    if os.path.exists(chats_folder):
        for file_name in os.listdir(chats_folder):
            file_path = os.path.join(chats_folder, file_name)
            if os.path.isfile(file_path):
                os.remove(file_path)
    # Recreate index.json file
    with open("chats/index.json", "w") as file:
        json.dump({}, file)
    return {"message": "Chat history reset"}

if __name__ == "__main__":
    load_chat_history()
    init_ollama()
    uvicorn.run(app, host="0.0.0.0", port=8000)
