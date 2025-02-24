import os
import json

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
