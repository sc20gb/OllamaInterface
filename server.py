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
import uuid

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

class ChatSummary(BaseModel):
    id: str
    name: str

class ChatHistory(BaseModel):
    id: str
    history: list

@app.get("/", response_class=HTMLResponse)
async def get_chat_interface():
    """
    Serve the chat interface HTML page.
    """
    logger.info("Serving chat interface HTML page")
    return FileResponse("index.html")

# Store chat history
chat_histories = {}
index_file = "chats/index.json"

def save_chat_history(chat_id):
    """
    Save chat history to a file.
    """
    with open(f"chats/{chat_id}.json", "w") as file:
        json.dump(chat_histories[chat_id], file)

def load_chat_history(chat_id):
    """
    Load chat history from a file.
    """
    if os.path.exists(f"chats/{chat_id}.json"):
        with open(f"chats/{chat_id}.json", "r") as file:
            chat_histories[chat_id] = json.load(file)
    else:
        chat_histories[chat_id] = []

def save_index():
    """
    Save the index file.
    """
    with open(index_file, "w") as file:
        json.dump([{"id": chat_id, "name": chat["name"]} for chat_id, chat in chat_histories.items()], file)

def load_index():
    """
    Load the index file.
    """
    if os.path.exists(index_file):
        with open(index_file, "r") as file:
            index = json.load(file)
            for chat in index:
                load_chat_history(chat["id"])

@app.get("/history/{chat_id}")
async def get_chat_history(chat_id: str):
    """
    Get the chat history for a specific chat.
    """
    logger.info(f"Retrieving chat history for chat {chat_id}")
    return {"history": chat_histories.get(chat_id, [])}

@app.post("/reset/{chat_id}")
async def reset_chat_history(chat_id: str):
    """
    Reset the chat history for a specific chat.
    """
    chat_histories[chat_id] = []
    save_chat_history(chat_id)
    logger.info(f"Chat history reset for chat {chat_id}")
    return {"message": f"Chat history reset for chat {chat_id}"}

@app.post("/query/{chat_id}")
async def query_model(chat_id: str, request: QueryRequest):
    """
    Send a query to the Ollama model and return the response for a specific chat.
    """
    model_name = "deepseek-r1:latest"  # Replace with the correct model name
    logger.info(f"Received query: {request.prompt}")
    try:
        # Add the user's prompt to the chat history
        chat_histories[chat_id].append({"role": "user", "content": request.prompt})
        
        # Create the full prompt with chat history
        full_prompt = "\n".join([f"{entry['role']}: {entry['content']}" for entry in chat_histories[chat_id]])
        
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
            chat_histories[chat_id].append({"role": "ollama", "content": full_response})
            # Save chat history to file
            save_chat_history(chat_id)
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

@app.get("/chats/")
async def get_chats():
    """
    Get the list of chat summaries.
    """
    logger.info("Retrieving chat summaries")
    return {"chats": [{"id": chat_id, "name": chat["name"]} for chat_id, chat in chat_histories.items()]}

@app.post("/chats/")
async def create_chat():
    """
    Create a new chat.
    """
    chat_id = str(uuid.uuid4())
    chat_histories[chat_id] = {"name": f"Chat {len(chat_histories) + 1}", "history": []}
    save_chat_history(chat_id)
    save_index()
    logger.info(f"Created new chat with id {chat_id}")
    return {"id": chat_id, "name": chat_histories[chat_id]["name"]}

@app.put("/chats/{chat_id}")
async def update_chat(chat_id: str, summary: ChatSummary):
    """
    Update the name of a chat.
    """
    if chat_id in chat_histories:
        chat_histories[chat_id]["name"] = summary.name
        save_index()
        logger.info(f"Updated chat {chat_id} name to {summary.name}")
        return {"message": f"Chat {chat_id} updated"}
    else:
        raise HTTPException(status_code=404, detail="Chat not found")

@app.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str):
    """
    Delete a chat.
    """
    if chat_id in chat_histories:
        del chat_histories[chat_id]
        os.remove(f"chats/{chat_id}.json")
        save_index()
        logger.info(f"Deleted chat {chat_id}")
        return {"message": f"Chat {chat_id} deleted"}
    else:
        raise HTTPException(status_code=404, detail="Chat not found")

if __name__ == "__main__":
    load_index()
    init_ollama()
    uvicorn.run(app, host="0.0.0.0", port=8000)
