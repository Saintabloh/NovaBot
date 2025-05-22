import os
from dotenv import load_dotenv
from docx import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
import google.generativeai as genai
import json
import time
import logging

# Config
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

load_dotenv()

# Configuration
WORD_DOC_PATH = "data/Novaguide.docx" 
OUTPUT_VECTOR_STORE_PATH = "university_vector_store.json"
EMBEDDING_MODEL_NAME = "models/embedding-001"
CHUNK_SIZE = 1200 
CHUNK_OVERLAP = 200 
API_RETRY_DELAY = 5 
API_MAX_RETRIES = 3 

def configure_gemini_api():
    """Configures the Gemini API using the environment variable."""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logging.error("GOOGLE_API_KEY not found in .env file or environment variables.")
        raise ValueError("GOOGLE_API_KEY not found.")
    genai.configure(api_key=api_key)
    logging.info("Gemini API configured successfully for preprocessing.")

def extract_text_from_docx(filepath):
    logging.info(f"Attempting to extract text from: {filepath}")
    if not os.path.exists(filepath):
        logging.error(f"Word document not found at path: {filepath}")
        raise FileNotFoundError(f"Word document not found at path: {filepath}")
    
    doc = Document(filepath)
    full_text = []
    for para in doc.paragraphs:
        if para.text.strip(): 
            full_text.append(para.text)
    

    logging.info(f"Extracted {len(full_text)} paragraphs/text segments.")
    return '\n\n'.join(full_text)

def chunk_text(text, chunk_size, chunk_overlap):
    logging.info(f"Chunking text with size={chunk_size}, overlap={chunk_overlap}")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        add_start_index=False, 
        separators=["\n\n", "\n", ". ", ", ", " ", ""] 
    )
    chunks = text_splitter.split_text(text)
    logging.info(f"Created {len(chunks)} chunks.")
    return chunks

def get_embeddings_batched(texts, model_name, batch_size=100, task_type="RETRIEVAL_DOCUMENT"):
    logging.info(f"Generating embeddings for {len(texts)} chunks using model {model_name} (batch size: {batch_size})")
    all_embeddings = []
    if not texts:
        logging.warn("No texts provided to get_embeddings_batched.")
        return all_embeddings

    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i:i + batch_size]
        content_for_api = [str(text) for text in batch_texts if text.strip()]
        
        if not content_for_api:
            logging.warn(f"  Skipping empty batch at index {i}")
            all_embeddings.extend([None] * len(batch_texts)) 
            continue

        retries = 0
        while retries < API_MAX_RETRIES:
            try:
                result = genai.embed_content(
                    model=model_name,
                    content=content_for_api,
                    task_type=task_type
                )
                all_embeddings.extend(result['embedding'])
                logging.info(f"  Processed batch {i//batch_size + 1}/{(len(texts)-1)//batch_size + 1} (size: {len(content_for_api)})")
                break 
            except Exception as e:
                retries += 1
                logging.error(f"  Error generating embeddings for batch (index {i}, attempt {retries}/{API_MAX_RETRIES}): {e}")
                if retries >= API_MAX_RETRIES:
                    logging.error(f"  Max retries reached for batch (index {i}). Adding None for this batch.")
                    all_embeddings.extend([None] * len(content_for_api)) 
                else:
                    logging.info(f"  Retrying in {API_RETRY_DELAY} seconds...")
                    time.sleep(API_RETRY_DELAY)
        time.sleep(1) 
    return all_embeddings

def main():
    try:
        configure_gemini_api()
    except ValueError as e:
        logging.critical(f"Failed to configure Gemini API: {e}")
        return

    try:
        university_data_text = extract_text_from_docx(WORD_DOC_PATH)
        if not university_data_text or not university_data_text.strip():
            logging.error("No text extracted from the document. Please check the path and content of the Word file.")
            return

        text_chunks = chunk_text(university_data_text, CHUNK_SIZE, CHUNK_OVERLAP)
        if not text_chunks:
            logging.error("No chunks were created from the text. The document might be too short or empty after extraction.")
            return

        chunk_embeddings = get_embeddings_batched(text_chunks, EMBEDDING_MODEL_NAME)

        indexed_data = []
        failed_embeddings_count = 0
        for i, (chunk, embedding) in enumerate(zip(text_chunks, chunk_embeddings)):
            if embedding is not None and isinstance(embedding, list): # Check embedding
                indexed_data.append({"id": f"chunk_{WORD_DOC_PATH}_{i}", "text_chunk": chunk, "embedding": embedding})
            else:
                failed_embeddings_count += 1
                logging.warning(f"Skipping chunk {i} ('{chunk[:50]}...') due to failed or invalid embedding generation.")

        if failed_embeddings_count > 0:
            logging.warning(f"Total {failed_embeddings_count} out of {len(text_chunks)} chunks were skipped due to embedding errors.")
        
        if not indexed_data:
            logging.error("No data was successfully indexed. Check for widespread embedding errors or empty chunks.")
            return

        with open(OUTPUT_VECTOR_STORE_PATH, "w") as f:
            json.dump(indexed_data, f, indent=2)
        
        logging.info(f"Successfully processed and indexed {len(indexed_data)} chunks.")
        logging.info(f"Vector store saved to: {OUTPUT_VECTOR_STORE_PATH}")

    except FileNotFoundError:
        logging.error(f"CRITICAL: The Word document was not found at '{WORD_DOC_PATH}'. Preprocessing cannot continue.")
    except Exception as e:
        logging.critical(f"An unexpected critical error occurred during preprocessing: {e}", exc_info=True)

if __name__ == "__main__":
    main()