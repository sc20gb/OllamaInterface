from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from backend.models import QueryRequest
from backend.ollama import is_ollama_running, start_ollama, init_ollama
from backend.chat_history import save_chat_history, load_chat_history, chat_history
import uvicorn
import os
import signal
import logging
import json

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()

@app.get("/", response_class=HTMLResponse)
async def get_chat_interface():
    """
    Serve the chat interface HTML page.
    """
    logger.info("Serving chat interface HTML page")
    return FileResponse("index.html")

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

if __name__ == "__main__":
    load_chat_history()
    init_ollama()
    uvicorn.run(app, host="0.0.0.0", port=8000)
