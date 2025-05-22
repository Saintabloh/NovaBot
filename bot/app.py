import os
import google.generativeai as genai
from flask import (
    Flask, request, jsonify, render_template, url_for,
    session, redirect, flash, g
)
from flask_cors import CORS
from dotenv import load_dotenv
from functools import wraps
import json
import numpy as np
import logging

# Firebase Admin SDK
import firebase_admin
from firebase_admin import credentials, auth

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(name)s - [%(funcName)s] - %(message)s')

load_dotenv()

app = Flask(__name__) 
CORS(app)

# Now you can use app.logger
app.logger.info(".env file loaded (or attempted to load).")

app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'a_very_default_and_insecure_secret_key_fallback')
if app.config['SECRET_KEY'] == 'a_very_default_and_insecure_secret_key_fallback':
    app.logger.warning("SECURITY WARNING: Using default Flask SECRET_KEY. Set a proper FLASK_SECRET_KEY in your .env file!")

VECTOR_STORE_PATH = "university_vector_store.json"
UNIVERSITY_KNOWLEDGE_BASE = []
EMBEDDING_MODEL_FOR_QUERY = "models/embedding-001"

firebase_app_initialized = False
try:
    app.logger.info("Attempting Firebase Admin SDK Initialization...")
    firebase_sdk_json_path = os.getenv('FIREBASE_ADMIN_SDK_JSON_PATH')
    app.logger.info(f"Path to Firebase Admin SDK JSON from .env: '{firebase_sdk_json_path}'")

    if not firebase_sdk_json_path:
        app.logger.critical("CRITICAL: FIREBASE_ADMIN_SDK_JSON_PATH is not set in the .env file.")
        raise ValueError("FIREBASE_ADMIN_SDK_JSON_PATH environment variable not set.")

    project_root = os.path.dirname(os.path.abspath(__file__))
    absolute_sdk_path = os.path.join(project_root, firebase_sdk_json_path)
    app.logger.info(f"Absolute path to Firebase Admin SDK JSON: '{absolute_sdk_path}'")

    if not os.path.exists(absolute_sdk_path):
        app.logger.critical(f"CRITICAL: Firebase Admin SDK JSON file NOT FOUND at resolved path: {absolute_sdk_path}")
        app.logger.critical(f"Please ensure the file '{firebase_sdk_json_path}' exists in the project root or the path is correct in .env.")
        raise FileNotFoundError(f"Firebase Admin SDK JSON file not found at {absolute_sdk_path}")

    cred = credentials.Certificate(absolute_sdk_path)
    firebase_admin.initialize_app(cred)
    firebase_app_initialized = True
    app.logger.info("Firebase Admin SDK initialized successfully.")

except ValueError as e:
    app.logger.critical(f"Firebase Admin SDK Initialization ValueError: {e}", exc_info=True)
except FileNotFoundError as e:
    app.logger.critical(f"Firebase Admin SDK Initialization FileNotFoundError: {e}", exc_info=True)
except Exception as e:
    app.logger.critical(f"An unexpected error occurred during Firebase Admin SDK initialization: {e}", exc_info=True)

if not firebase_app_initialized:
    app.logger.critical("CRITICAL FAILURE: Firebase Admin SDK could not be initialized. Firebase dependent features will not work.")

try:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY not found.")
    genai.configure(api_key=api_key)
    app.logger.info("Gemini API configured successfully.")
except ValueError as e:
    app.logger.critical(f"Gemini API Configuration Error: {e}")
MODEL_NAME = 'gemini-1.5-pro-latest'
try:
    model = genai.GenerativeModel(MODEL_NAME)
    app.logger.info(f"Successfully initialized generative model: {MODEL_NAME}")
except Exception as e:
    app.logger.error(f"Error initializing generative model '{MODEL_NAME}': {e}")
    model = None

def load_knowledge_base():
    global UNIVERSITY_KNOWLEDGE_BASE
    try:
        if os.path.exists(VECTOR_STORE_PATH):
            with open(VECTOR_STORE_PATH, "r") as f:
                UNIVERSITY_KNOWLEDGE_BASE = json.load(f)
            app.logger.info(f"Successfully loaded {len(UNIVERSITY_KNOWLEDGE_BASE)} chunks into knowledge base from {VECTOR_STORE_PATH}.")
        else:
            app.logger.warning(f"{VECTOR_STORE_PATH} not found. University Info mode will rely on general AI knowledge or may not work as expected.")
            UNIVERSITY_KNOWLEDGE_BASE = []
    except Exception as e:
        app.logger.error(f"An unexpected error occurred while loading knowledge base: {e}")
        UNIVERSITY_KNOWLEDGE_BASE = []

with app.app_context():
    load_knowledge_base()

def find_relevant_chunks(query_text, top_n=3):
    if not UNIVERSITY_KNOWLEDGE_BASE:
        app.logger.warning("Attempted to find relevant chunks, but knowledge base is empty.")
        return []
    if not query_text or not query_text.strip():
        app.logger.warning("Attempted to find relevant chunks with an empty query.")
        return []
    try:
        query_embedding_response = genai.embed_content(
            model=EMBEDDING_MODEL_FOR_QUERY,
            content=str(query_text),
            task_type="RETRIEVAL_QUERY"
        )
        query_embedding = np.array(query_embedding_response['embedding'])
    except Exception as e:
        app.logger.error(f"Error generating embedding for query '{query_text[:50]}...': {e}")
        return []
    similarities = []
    for item in UNIVERSITY_KNOWLEDGE_BASE:
        if "embedding" not in item or not isinstance(item["embedding"], list):
            app.logger.warning(f"Skipping item in knowledge base due to missing or invalid embedding: {item.get('id', 'Unknown ID')}")
            continue
        doc_embedding = np.array(item["embedding"])
        similarity = np.dot(query_embedding, doc_embedding)
        similarities.append((similarity, item["text_chunk"]))
    similarities.sort(key=lambda x: x[0], reverse=True)
    relevant_chunks = [chunk for _, chunk in similarities[:top_n]]
    app.logger.info(f"Found {len(relevant_chunks)} relevant chunks for query '{query_text[:50]}...'.")
    return relevant_chunks

@app.before_request
def load_logged_in_user_from_session():
    g.user = None
    if 'firebase_uid' in session:
        g.user = {
            'uid': session['firebase_uid'],
            'email': session.get('user_email', 'N/A')
        }

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.user is None:
            flash('You need to be logged in to access this page.', 'warning')
            return redirect(url_for('login_page', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/auth/sessionLogin', methods=['POST'])
def session_login():
    global firebase_app_initialized
    if not firebase_app_initialized:
        app.logger.error("Firebase not initialized. Cannot process session login.")
        return jsonify({"error": "Internal server error: Firebase not configured."}), 500
    try:
        data = request.get_json()
        if not data:
            app.logger.error("No JSON data received in /auth/sessionLogin")
            return jsonify({"error": "Invalid request format: No JSON data."}), 400

        id_token = data.get('idToken')
        app.logger.debug(f"Backend received ID Token (first 30 chars): {id_token[:30] if id_token else 'None'}")

        if not id_token:
            app.logger.error("ID token is missing in the received JSON payload.")
            return jsonify({"error": "ID token is missing."}), 400

        decoded_token = auth.verify_id_token(id_token)
        uid = decoded_token['uid']
        email = decoded_token.get('email') 
        name = decoded_token.get('name', 'User') 

        session.clear()
        session['firebase_uid'] = uid
        if email:
            session['user_email'] = email
        session['user_name'] = name 
        session.permanent = True

        app.logger.info(f"User {uid} (Email: {email}, Name: {name}) logged in successfully via Firebase token.")
        return jsonify({"status": "success", "uid": uid, "email": email, "name": name}), 200
    except auth.InvalidIdTokenError:
        app.logger.warning("Invalid Firebase ID token received.", exc_info=True)
        return jsonify({"error": "Invalid ID token. Please try signing in again."}), 401
    except auth.ExpiredIdTokenError:
        app.logger.warning("Expired Firebase ID token received.", exc_info=True)
        return jsonify({"error": "Your session has expired. Please sign in again."}), 401
    except firebase_admin.exceptions.FirebaseError as fa_error:
        app.logger.error(f"Firebase error during session login: {fa_error}", exc_info=True)
        if "The default Firebase app does not exist" in str(fa_error):
             app.logger.critical("Caught 'default Firebase app does not exist' within session_login. This indicates a severe initialization problem.")
             return jsonify({"error": "Internal server error: Firebase configuration issue."}), 500
        return jsonify({"error": f"A Firebase error occurred. Please try again."}), 500
    except Exception as e:
        app.logger.error(f"Error during Firebase session login: {e}", exc_info=True)
        return jsonify({"error": f"An internal error occurred. Please try again."}), 500

@app.route('/auth/sessionLogout', methods=['POST'])
def session_logout_server():
    session.clear()
    app.logger.info("User session cleared from server.")
    return jsonify({"status": "success", "message": "Server session cleared"}), 200

@app.route('/login')
def login_page():
    if g.user:
        next_page_url = request.args.get('next')
        if next_page_url:
            return redirect(next_page_url)
        return redirect(url_for('university_home'))
    firebase_config = {
        "apiKey": os.getenv("FIREBASE_API_KEY"),
        "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN"),
        "projectId": os.getenv("FIREBASE_PROJECT_ID"),
        "storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET"),
        "messagingSenderId": os.getenv("FIREBASE_MESSAGING_SENDER_ID"),
        "appId": os.getenv("FIREBASE_APP_ID"),
        "measurementId": os.getenv("FIREBASE_MEASUREMENT_ID")
    }
    return render_template('login.html', firebase_config=json.dumps(firebase_config))

@app.route('/logout_page')
def logout_page_route():
    firebase_config = {
        "apiKey": os.getenv("FIREBASE_API_KEY"),
        "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN"),
        "projectId": os.getenv("FIREBASE_PROJECT_ID")
    }
    return render_template('logout.html', firebase_config=json.dumps(firebase_config))

@app.route('/')
@login_required
def university_home():
    user_name = session.get('user_name', g.user.get('email', 'User'))
    return render_template('university_home.html', user_name=user_name)

@app.route('/about')
@login_required
def about():
    user_name = session.get('user_name', g.user.get('email', 'User'))
    return render_template('about.html', user_name=user_name)

@app.route('/programs')
@login_required
def programs():
    user_name = session.get('user_name', g.user.get('email', 'User'))
    return render_template('programs.html', user_name=user_name)

@app.route('/admissions')
@login_required
def admissions():
    user_name = session.get('user_name', g.user.get('email', 'User'))
    return render_template('admissions.html', user_name=user_name)

@app.route('/contact')
@login_required
def contact():
    user_name = session.get('user_name', g.user.get('email', 'User'))
    return render_template('contact.html', user_name=user_name)

@app.route('/chatbot')
@login_required
def chatbot_ui_page_route():
    user_name = session.get('user_name', g.user.get('email', 'User'))
    return render_template('chatbot_ui_page.html', user_name=user_name)

@app.route('/generate', methods=['POST'])
@login_required
def generate():
    if not model:
        app.logger.error("Generative model (Gemini) not initialized. Cannot process chat.")
        return jsonify({"error": "AI Model not initialized. Please contact support."}), 500
    try:
        data = request.get_json()
        if not data:
            app.logger.error("Request to /generate is not JSON or empty.")
            return jsonify({"error": "Invalid request format."}), 400
        user_prompt = data.get('prompt')
        client_conversation_history = data.get('conversation', [])
        if not user_prompt or not str(user_prompt).strip():
            return jsonify({"error": "No prompt provided or prompt is empty."}), 400
        user_prompt = str(user_prompt)
        gemini_history = []
        for msg_from_client in client_conversation_history:
            role = msg_from_client.get('role')
            parts_array = msg_from_client.get('parts')
            if not role or role not in ['user', 'model'] or \
               not parts_array or not isinstance(parts_array, list) or len(parts_array) == 0:
                app.logger.warning(f"Skipping history message with invalid structure: {msg_from_client}")
                continue
            text_content_obj = parts_array[0]
            if not isinstance(text_content_obj, dict):
                app.logger.warning(f"Skipping history message, part is not a dict: {text_content_obj}")
                continue
            actual_text = text_content_obj.get('text')
            if actual_text is None:
                app.logger.error(f"History message part has 'None' text content: {msg_from_client}. Skipping.")
                continue
            gemini_history.append({'role': role, 'parts': [str(actual_text)]})
        app.logger.info(f"University Info Mode (Default) for query: '{user_prompt[:100]}...'")
        relevant_chunks = find_relevant_chunks(user_prompt, top_n=3)
        retrieved_context_for_log = "N/A"
        if relevant_chunks:
            context_str = "\n\n---\n\n".join(relevant_chunks)
            retrieved_context_for_log = context_str[:500] + "..." if len(context_str) > 500 else context_str
            final_prompt_to_gemini = f"""You are an AI assistant for NovaTech University.
Your primary task is to answer the user's question based *exclusively* on the "Provided Context" below, which comes from official NovaTech University documents.
Carefully review the "Provided Context" and use it to form your answer.
If the information needed to answer the question is not present in the "Provided Context", you MUST explicitly state that the information is not available in the provided documents.
Do not invent information or use any external knowledge outside of the "Provided Context".
Respond in a helpful, clear, and conversational manner.

Provided Context:
{context_str}
---
User's Question: {user_prompt}
---
Answer (based *only* on the Provided Context):"""
            app.logger.info(f"Context found. Using RAG prompt. Context snippet: {retrieved_context_for_log}")
        else:
            app.logger.info("No relevant context found. AI will be prompted to state this.")
            final_prompt_to_gemini = f"""You are an AI assistant for NovaTech University.
The user asked: "{user_prompt}"
No specific information related to this query was found in the university's private documents.
Please state that you don't have that specific information from the documents and cannot answer the question.
User's Question: {user_prompt}
---
Answer:"""
        app.logger.debug(f"Final prompt for Gemini (Context length {len(retrieved_context_for_log)}): {final_prompt_to_gemini[:300]}...")
        chat_session = model.start_chat(history=gemini_history)
        response = chat_session.send_message(final_prompt_to_gemini)
        bot_response_text = response.text
        response_payload = {"generated_text": bot_response_text}
        return jsonify(response_payload)
    except Exception as e:
        app.logger.error(f"Critical error in /generate endpoint: {e}", exc_info=True)
        return jsonify({"error": "An unexpected error occurred while communicating with the AI service."}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)