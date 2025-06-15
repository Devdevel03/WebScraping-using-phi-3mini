import sys
import os
from flask import Flask, render_template, request, redirect, url_for

# Import our fixed summarizer functions
from summarizer_llm import get_text_from_url, summarize_text, check_model_availability, MODEL_NAME, test_ollama_connection

# Initialize the Flask application
app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def index():
    """Handles the main page, both for displaying the form and processing it."""
    if request.method == 'POST':
        url = request.form.get('url')
        if not url:
            return render_template('index.html', error="Please enter a URL.")

        # Add basic URL validation
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        # 1. Get text from the URL
        print(f"Fetching content from: {url}")
        article_text = get_text_from_url(url)

        if article_text is None:
            return render_template('index.html', error="Could not fetch or read content from the URL. Please check the URL and try again.")
        
        if len(article_text.strip()) < 100:
            return render_template('index.html', error="The page doesn't seem to have enough content to summarize. Please try a different URL.")
        
        # 2. Summarize the text using the model
        print("Content fetched. Summarizing with Ollama...")
        summary = summarize_text(article_text)
        print("Summary generated.")

        # 3. Show the result page
        return render_template('result.html', 
                             summary=summary, 
                             url=url, 
                             original_length=len(article_text))

    # For a GET request, just show the main page
    return render_template('index.html')

@app.route('/test')
def test_connection():
    """Debug route to test Ollama connection."""
    test_ollama_connection()
    return "Check console for connection test results."

def start_app():
    """Checks for model availability and starts the Flask app."""
    print("--- AI Web Summarizer ---")
    print("Checking if Ollama and the model are available...")
    
    # First, let's test the connection
    print("\nRunning connection diagnostics...")
    test_ollama_connection()
    
    if not check_model_availability():
        print(f"\nError: Model '{MODEL_NAME}' not found or Ollama is not running.")
        print("\nTroubleshooting steps:")
        print("1. Make sure Ollama is installed and running")
        print("2. Check if Ollama is running: Open another terminal and run 'ollama list'")
        print(f"3. Pull the model: ollama pull {MODEL_NAME}")
        print("4. If you're using a different model, update MODEL_NAME in the code")
        print("\nAvailable troubleshooting:")
        print("- Visit http://127.0.0.1:5000/test to run connection diagnostics")
        
        # Don't exit immediately, let them test the connection
        print("\nStarting server anyway for troubleshooting...")
        print("Open your browser and go to http://127.0.0.1:5000")
        print("Visit http://127.0.0.1:5000/test to see detailed connection info")
        app.run(host='127.0.0.1', port=5000, debug=True)
        return
        
    print(f"Model '{MODEL_NAME}' is available. Starting web server...")
    print("Open your browser and go to http://127.0.0.1:5000")
    app.run(host='127.0.0.1', port=5000, debug=True)

if __name__ == '__main__':
    start_app()