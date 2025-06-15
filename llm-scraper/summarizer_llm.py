import ollama
import requests
from bs4 import BeautifulSoup

# --- CONFIGURATION ---
MODEL_NAME = "phi3:mini"
OLLAMA_HOST = "http://127.0.0.1:11434" 
client = ollama.Client(host=OLLAMA_HOST)

def check_model_availability(model_name: str = MODEL_NAME) -> bool:
    """Checks if the specified model is available locally via Ollama."""
    try:
        # First check if Ollama is running by trying to connect
        response = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        response.raise_for_status()
        
        # Parse the response to check for models
        models_data = response.json()
        models = models_data.get('models', [])
        
        # Check if our model is in the list
        for model in models:
            if model.get('name', '').startswith(model_name):
                return True
        return False
        
    except requests.exceptions.ConnectionError:
        print(f"Could not connect to Ollama at {OLLAMA_HOST}. Is Ollama running?")
        return False
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to Ollama: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error checking model availability: {e}")
        return False

def get_text_from_url(url: str) -> str | None:
    """
    Fetches and extracts the main text content from a given URL.
    Returns the text or None if fetching fails.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        
        # Try to find main content areas first
        main_content = None
        content_selectors = ['main', 'article', '.content', '.post-content', '.entry-content']
        
        for selector in content_selectors:
            main_content = soup.select_one(selector)
            if main_content:
                break
        
        # If no main content found, use all paragraphs
        if main_content:
            paragraphs = main_content.find_all('p')
        else:
            paragraphs = soup.find_all('p')
            
        if not paragraphs:
            # Fallback to getting all text if no paragraphs found
            return soup.get_text(strip=True, separator=' ')
            
        full_text = ' '.join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
        return full_text

    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        return None
    except Exception as e:
        print(f"Error parsing content from {url}: {e}")
        return None

def summarize_text(text_content: str, model: str = MODEL_NAME) -> str:
    """
    Sends the extracted text to the Ollama model for summarization.
    """
    if not text_content:
        return "Could not generate a summary because no text was provided."

    # Truncate text if it's too long (Ollama has context limits)
    max_chars = 8000  # Adjust based on your model's context window
    if len(text_content) > max_chars:
        text_content = text_content[:max_chars] + "..."

    prompt = f"""
    Based on the following article text, please provide a concise, easy-to-read summary.
    Focus on the main points and key takeaways. Keep the summary to 3-5 paragraphs.

    --- TEXT ---
    {text_content}
    --- END TEXT ---

    Summary:
    """
    
    try:
        # Use direct ollama.chat instead of client.chat
        response = ollama.chat(
            model=model,
            messages=[{'role': 'user', 'content': prompt}],
            stream=False
        )
        return response['message']['content']
    except Exception as e:
        print(f"Error communicating with Ollama model: {e}")
        return f"Error: Failed to get a summary from the AI model. Details: {str(e)}"

def test_ollama_connection():
    """Test function to debug Ollama connection issues."""
    print("Testing Ollama connection...")
    
    try:
        # Test basic connection
        response = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        print(f"Connection status: {response.status_code}")
        
        if response.status_code == 200:
            models_data = response.json()
            print(f"Available models: {[model.get('name') for model in models_data.get('models', [])]}")
        
        # Test ollama library directly
        models = ollama.list()
        print(f"Ollama library response: {models}")
        
    except Exception as e:
        print(f"Connection test failed: {e}")

if __name__ == "__main__":
    # Run connection test
    test_ollama_connection()
    
    # Test model availability
    if check_model_availability():
        print(f"Model '{MODEL_NAME}' is available!")
    else:
        print(f"Model '{MODEL_NAME}' is not available.")