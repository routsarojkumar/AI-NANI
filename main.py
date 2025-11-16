import os
import requests
from bs4 import BeautifulSoup
import chromadb
import pyttsx3
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

try:
    import openai
except Exception:
    openai = None

try:
    import PyPDF2
except Exception:
    PyPDF2 = None

# PDF folder structure
PDF_FOLDER = "d:\\App\\AiNani\\stories_pdf"

# External categories file (one entry per line: key=Display Name)
CATEGORIES_FILE = os.path.join(os.path.dirname(__file__), "categories.txt")

# Default categories (used to populate the file the first time)
DEFAULT_CATEGORIES = {
    "mythological": "Mythological Stories",
    "historical": "Historical Stories",
    "moral": "Moral Stories",
    "funny": "Funny Stories",
    "web": "Web Stories"
}

def ensure_default_categories():
    """Create categories.txt with defaults if missing."""
    try:
        if not os.path.exists(CATEGORIES_FILE):
            with open(CATEGORIES_FILE, "w", encoding="utf-8") as f:
                for k, v in DEFAULT_CATEGORIES.items():
                    f.write(f"{k}={v}\n")
    except Exception:
        pass

def load_categories():
    """Load categories from categories.txt and return dict {key: display_name}."""
    ensure_default_categories()
    cats = {}
    try:
        with open(CATEGORIES_FILE, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                if "=" in s:
                    key, val = s.split("=", 1)
                    key = key.strip()
                    val = val.strip()
                    if key:
                        cats[key] = val or key
                else:
                    key = s.strip()
                    cats[key] = key
    except Exception:
        return dict(DEFAULT_CATEGORIES)
    # ensure defaults exist if file is incomplete
    for k, v in DEFAULT_CATEGORIES.items():
        cats.setdefault(k, v)
    return cats

def save_categories(categories_dict):
    """Save categories dict to categories.txt (overwrite)."""
    try:
        with open(CATEGORIES_FILE, "w", encoding="utf-8") as f:
            for k, v in categories_dict.items():
                f.write(f"{k}={v}\n")
        return True
    except Exception:
        return False

def add_category(key, display_name=None):
    """Add a category (key) to the file; returns True if added."""
    cats = load_categories()
    if key in cats:
        return False
    cats[key] = display_name or key
    return save_categories(cats)

def remove_category(key):
    """Remove a category by key; returns True if removed."""
    cats = load_categories()
    if key not in cats:
        return False
    cats.pop(key)
    return save_categories(cats)

# Load categories for runtime use
CATEGORIES = load_categories()

# External story URLs file (one URL per line)
STORY_URLS_FILE = os.path.join(os.path.dirname(__file__), "story_urls.txt")

# Default URLs (used to populate the file the first time)
DEFAULT_STORY_URLS = [
    "https://www.moralstories.org/seek-a-revenge-or-give-forgiveness/",
    "https://www.moralstories.org/the-weight-of-soil/",
    "https://www.moralstories.org/tenali-rama-and-the-trader/",
    "https://www.moralstories.org/a-man-with-a-lamp/"
]

def ensure_default_story_urls():
    """Ensure the story_urls.txt exists; create with defaults if missing."""
    try:
        if not os.path.exists(STORY_URLS_FILE):
            with open(STORY_URLS_FILE, "w", encoding="utf-8") as f:
                for u in DEFAULT_STORY_URLS:
                    f.write(u.strip() + "\n")
    except Exception:
        pass

def load_story_urls():
    """Load story URLs from STORY_URLS_FILE, return list of non-empty lines."""
    ensure_default_story_urls()
    urls = []
    try:
        with open(STORY_URLS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s and not s.startswith("#"):
                    urls.append(s)
    except Exception:
        # Fallback to DEFAULT_STORY_URLS if file read fails
        return list(DEFAULT_STORY_URLS)
    return urls

def save_story_urls(urls):
    """Overwrite the story_urls file with provided list."""
    try:
        with open(STORY_URLS_FILE, "w", encoding="utf-8") as f:
            for u in urls:
                f.write(u.strip() + "\n")
        return True
    except Exception:
        return False

def add_story_url(url):
    """Add a URL to the story_urls file if not already present."""
    urls = load_story_urls()
    if url not in urls:
        urls.append(url)
        save_story_urls(urls)
        return True
    return False

def remove_story_url(url):
    """Remove a URL from the story_urls file if present."""
    urls = load_story_urls()
    if url in urls:
        urls.remove(url)
        save_story_urls(urls)
        return True
    return False

# Provide STORY_URLS variable for backwards compatibility (app.py and other code)
STORY_URLS = load_story_urls()

# List of URLs to scrape stories from
# STORY_URLS is populated at import time for backwards compatibility
# but scrape_stories() will use the external story_urls.txt by default
# STORY_URLS = [
#     "https://www.moralstories.org/seek-a-revenge-or-give-forgiveness/",
#     "https://www.moralstories.org/the-weight-of-soil/",
#     "https://www.moralstories.org/tenali-rama-and-the-trader/",
#     "https://www.moralstories.org/a-man-with-a-lamp/"
# ]

# Function to extract text from PDF
def extract_text_from_pdf(pdf_path):
    if PyPDF2 is None:
        print("PyPDF2 not installed. Skipping PDF extraction.")
        return ""
    
    try:
        text = ""
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                text += page.extract_text() + "\n"
        return text
    except Exception as e:
        print(f"Error extracting text from {pdf_path}: {str(e)}")
        return ""

# Function to split PDF text into stories (improved: better segmentation)
def split_pdf_into_stories(text, pdf_name):
    stories = []
    
    # Split by double newlines as paragraph breaks
    paragraphs = text.split('\n\n')
    
    current_story = ""
    story_title = "Untitled"
    para_count = 0
    
    for para in paragraphs:
        para = para.strip()
        
        # Skip very short paragraphs
        if not para or len(para) < 20:
            continue
        
        # Detect potential story titles (short, capitalized, no period at end)
        is_title = (
            len(para) < 80 and 
            para[0].isupper() and 
            not para.endswith(('.', '?', '!')) and
            '\n' not in para and
            len(para.split()) <= 10
        )
        
        # If we have a complete story and find a new title, save it
        if current_story and is_title and para_count >= 2:
            if len(current_story) > 150:  # Only save substantial stories
                stories.append({
                    "content": current_story.strip(),
                    "source": pdf_name,
                    "title": story_title
                })
            current_story = ""
            para_count = 0
            story_title = para
            continue
        
        # If this looks like a title and no current story, set it as title
        if is_title and not current_story:
            story_title = para
            continue
        
        # Accumulate paragraph into current story
        if current_story:
            current_story += "\n\n" + para
        else:
            current_story = para
        
        para_count += 1
        
        # If story gets very long, consider it complete and save
        if len(current_story) > 1200:
            stories.append({
                "content": current_story.strip(),
                "source": pdf_name,
                "title": story_title
            })
            current_story = ""
            para_count = 0
            story_title = "Untitled"
    
    # Save remaining story
    if current_story and len(current_story) > 150:
        stories.append({
            "content": current_story.strip(),
            "source": pdf_name,
            "title": story_title
        })
    
    return stories

# Function to load stories from PDFs by category
def load_stories_from_pdfs(category):
    stories = []
    category_path = os.path.join(PDF_FOLDER, category)
    
    if not os.path.exists(category_path):
        print(f"Category folder not found: {category_path}")
        return stories
    
    for pdf_file in os.listdir(category_path):
        if pdf_file.endswith('.pdf'):
            pdf_path = os.path.join(category_path, pdf_file)
            print(f"Loading PDF: {pdf_file}")
            
            text = extract_text_from_pdf(pdf_path)
            if text:
                pdf_stories = split_pdf_into_stories(text, pdf_file)
                stories.extend(pdf_stories)
                print(f"Extracted {len(pdf_stories)} stories from {pdf_file}\n")
    
    return stories

# Update scrape_stories to accept optional urls parameter and use it
def scrape_stories(urls=None):
    if urls is None:
        urls = load_story_urls()
    all_stories = []
    
    for url in urls:
        try:
            print(f"Scraping from: {url}")
            response = requests.get(url, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')

            stories = []
            # Find headings and grab following paragraphs until next heading
            for h in soup.find_all('h2'):
                title = h.get_text(strip=True)
                paragraphs = []
                for sib in h.find_next_siblings():
                    if sib.name and sib.name.startswith('h'):
                        break
                    if sib.name == 'p':
                        paragraphs.append(sib.get_text(strip=True))
                content = title
                if paragraphs:
                    content += "\n\n" + "\n".join(paragraphs)
                if content.strip():
                    stories.append(content)
            
            # Add source URL metadata to each story
            for story in stories:
                all_stories.append({
                    "content": story,
                    "source": url
                })
            
            print(f"Successfully scraped {len(stories)} stories from this URL.\n")
        
        except Exception as e:
            print(f"Failed to scrape {url}: {str(e)}\n")
            continue

    return all_stories

# Function to store stories in ChromaDB by category
def store_in_chromadb(stories, category="web"):
    client = chromadb.Client()
    collection_name = f"stories_{category}"
    
    try:
        collection = client.get_collection(name=collection_name)
    except Exception:
        collection = client.create_collection(name=collection_name)

    ids = [f"{category}_story_{i}" for i in range(len(stories))]
    metadatas = [
        {
            "index": i,
            "source": stories[i]["source"],
            "category": category,
            "title": stories[i].get("title", "Untitled")
        }
        for i in range(len(stories))
    ]
    documents = [story["content"] for story in stories]

    try:
        collection.add(documents=documents, metadatas=metadatas, ids=ids)
    except Exception:
        try:
            for _id in ids:
                collection.delete(ids=[_id])
        except Exception:
            pass
        collection.add(documents=documents, metadatas=metadatas, ids=ids)

# Function to retrieve relevant documents from ChromaDB
def retrieve_relevant_docs(query, category="web", top_k=3):
    client = chromadb.Client()
    collection_name = f"stories_{category}"
    
    try:
        collection = client.get_collection(name=collection_name)
    except Exception:
        return []

    # Query and get documents with metadata
    results = collection.query(query_texts=[query], n_results=top_k)
    docs = results.get("documents", [[]])[0]
    # Filter out empty strings
    docs = [d for d in docs if d]
    return docs

# Helper to locate OpenAI API key from env or file
def get_openai_key():
    """
    Try multiple sources for the OpenAI API key:
    1) Environment variables: OPENAI_API_KEY, OPENAI_API_KEY_AI_NANI, OPENAI_KEY
    2) File: openai_key.txt in the project directory (first non-empty line)
    Returns the key string or None.
    """
    candidates = [
        "OPENAI_API_KEY",
        "OPENAI_API_KEY_AI_NANI",
        "OPENAI_KEY",
    ]
    for name in candidates:
        val = os.getenv(name)
        if val and val.strip():
            return val.strip()

    # fallback to file next to main.py
    try:
        key_file = os.path.join(os.path.dirname(__file__), "openai_key.txt")
        if os.path.exists(key_file):
            with open(key_file, "r", encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if s:
                        return s
    except Exception:
        pass

    return None

# Function to perform simple RAG using OpenAI (if available)
def generate_with_rag(query, context_docs):
    # Use helper to find key (checks multiple env names and fallback file)
    openai_key = get_openai_key()
    # If openai package isn't installed but a key exists, inform user
    if openai is None and openai_key:
        # Admin-friendly message; do not print the key
        return ("OpenAI python package not installed in this environment. "
                "Install it with `pip install openai` to enable AI generation. "
                "Falling back to retrieved document (if any).\n\n" +
                (context_docs[0] if context_docs else "No relevant stories found in the local DB."))

    # If no key or openai not available, fallback to returning a retrieved doc(s)
    if openai is None or not openai_key:
        if not context_docs:
            return "No relevant stories found in the local DB."
        return "Retrieved source documents:\n\n" + "\n\n---\n\n".join(context_docs)

    # normal flow: use OpenAI
    openai.api_key = openai_key
    context = "\n\n---\n\n".join(context_docs) if context_docs else ""

    system_msg = (
        "You are a helpful assistant that must write a story using ONLY the information "
        "provided in the context. Do not add your own imagination or unrelated ideas. "
        "If the context does not contain enough information, clearly say so. "
        "Write a short story (~150–300 words) for kids based strictly on the provided source."
    )

    #user_msg = f"Context (source stories):\n{context}\n\nTask: Write a short story for kids about: {query}\nKeep it ~150-300 words, include a short note naming which source fragments were used."
    user_msg = (
        f"Use the following source material strictly as reference:\n\n{context}\n\n"
        f"Now, write a short story for children about '{query}', making sure that all facts, names, and morals "
        f"come directly from the sources above. Include short citations in parentheses when possible."
        )
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=400,
            temperature=0.3,
        )
        text = resp["choices"][0]["message"]["content"].strip()
        return text
    except Exception as e:
        # fallback to returning only the top retrieved doc if API call fails
        if context_docs:
            primary = context_docs[0]
            fallback = "Failed to contact OpenAI: " + str(e) + "\n\nReturning the most relevant retrieved story:\n\n" + primary
        else:
            fallback = "Failed to contact OpenAI: " + str(e) + "\n\nNo documents."
        return fallback

# Enhanced RAG function with preferences and category
def generate_with_rag_enhanced(preferences, context_docs, category="web"):
    openai_key = get_openai_key()
    if openai is None and openai_key:
        return ("OpenAI python package not installed in this environment. "
                "Install it with `pip install openai` to enable AI generation. "
                "Falling back to the most relevant retrieved story.\n\n" +
                (context_docs[0] if context_docs else "No relevant stories found in the local DB."))

    if openai is None or not openai_key:
        if not context_docs:
            return "No relevant stories found in the local DB."
        # Return only the most relevant retrieved document as fallback
        primary = context_docs[0]
        return f"Note: OpenAI key not available — returning the most relevant retrieved story for {CATEGORIES.get(category,'stories')}:\n\n{primary}"

    openai.api_key = openai_key
    context = "\n\n---\n\n".join(context_docs) if context_docs else ""

    system_msg = (
        f"You are a helpful assistant that writes engaging, kid-friendly {CATEGORIES.get(category, 'stories')}. "
        "Use the source stories as inspiration. Keep stories simple and suitable for children."
    )

    user_msg = (
        f"Context (source stories):\n{context}\n\n"
        f"Task: Write a {preferences['tone']} story for kids about: {preferences['topic']}\n"
        f"Length: {preferences['length']}\n"
        f"Include a short note about which source fragments inspired this story."
    )

    try:
        resp = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=600,
            temperature=0.3,
        )
        text = resp.choices[0].message.content.strip()
        return text
    except Exception as e:
        if context_docs:
            primary = context_docs[0]
            fallback = "Failed to contact OpenAI: " + str(e) + "\n\nReturning the most relevant retrieved story:\n\n" + primary
        else:
            fallback = "Failed to contact OpenAI: " + str(e) + "\n\nNo documents."
        return fallback

# Function to convert text to speech
def text_to_speech(text):
    engine = pyttsx3.init()
    try:
        voices = engine.getProperty('voices') or []
        selected_voice = None

        # Prefer voices that look like Indian-accent voices
        indian_keys = ("indian", "india", "aditi", "neena", "hindi", "en_in", "en-in", "en_in.utf8")
        for v in voices:
            name_id = " ".join(filter(None, [getattr(v, "name", ""), getattr(v, "id", "")])).lower()
            if any(k in name_id for k in indian_keys):
                selected_voice = v
                break

        # Try languages metadata (some drivers expose languages like b'\x05en-IN')
        if not selected_voice:
            for v in voices:
                langs = getattr(v, "languages", None)
                if langs:
                    if any("in" in str(l).lower() for l in langs):
                        selected_voice = v
                        break

        # Fallback to female-sounding voice if no explicit Indian voice found
        if not selected_voice:
            for v in voices:
                name_id = " ".join(filter(None, [getattr(v, "name", ""), getattr(v, "id", "")])).lower()
                if any(k in name_id for k in ("female", "zira", "samantha", "karen")):
                    selected_voice = v
                    break

        # Final fallbacks
        if not selected_voice and len(voices) > 1:
            selected_voice = voices[1]
        if not selected_voice and voices:
            selected_voice = voices[0]

        if selected_voice:
            engine.setProperty('voice', selected_voice.id)

        # Slightly adjust rate for clarity (keep near-default)
        try:
            rate = engine.getProperty('rate')
            engine.setProperty('rate', int(rate * 0.98))
        except Exception:
            pass

    except Exception:
        # proceed with default voice on any error
        pass

    engine.say(text)
    engine.runAndWait()

# Global variables
scraped_stories = []
current_category = "web"

# Function to display all available stories
def display_available_stories():
    if not scraped_stories:
        print("No stories available.")
        return
    
    print(f"\n=== Available {CATEGORIES.get(current_category, 'Stories')} ===\n")
    for i, story_obj in enumerate(scraped_stories, 1):
        story = story_obj["content"]
        source = story_obj["source"]
        title = story_obj.get("title", "Untitled")
        preview = story[:100] + "..." if len(story) > 100 else story
        print(f"{i}. [{title}]")
        print(f"   Source: {source}")
        print(f"   Preview: {preview}\n")
    
    print(f"Total stories available: {len(scraped_stories)}")
    
    try:
        story_num = input("\nEnter story number to view full text (or press Enter to skip): ").strip()
        if story_num.isdigit() and 1 <= int(story_num) <= len(scraped_stories):
            idx = int(story_num) - 1
            title = scraped_stories[idx].get('title', 'Story')
            source = scraped_stories[idx]['source']
            print(f"\n--- {title} ---\n")
            print(scraped_stories[idx]["content"])
            print(f"\nSource: {source}")
            print("\n--- End ---\n")
    except Exception:
        pass

# Function to display story sources
def display_story_sources():
    print(f"\n=== Story Sources ({CATEGORIES.get(current_category, 'Stories')}) ===\n")
    
    if current_category == "web":
        for i, url in enumerate(STORY_URLS, 1):
            print(f"{i}. {url}")
    else:
        sources = set(story["source"] for story in scraped_stories)
        for i, source in enumerate(sorted(sources), 1):
            print(f"{i}. {source}")
    print()

# Function to display menu and get user choice
def display_menu():
    print("\n=== Story Generation Menu ===")
    print("1. Generate a new story")
    print("2. Regenerate previous story with different prompt")
    print("3. Listen to current story")
    print("4. Browse available stories")
    print("5. Switch story category")
    print("6. View story sources")
    print("7. Exit")
    choice = input("Select option (1-7): ").strip()
    return choice

# Function to select story category
def select_story_category():
    print("\n=== Select Story Category ===\n")
    categories_list = list(CATEGORIES.items())
    
    for i, (key, name) in enumerate(categories_list, 1):
        print(f"{i}. {name}")
    
    choice = input("\nSelect category (1-" + str(len(categories_list)) + "): ").strip()
    
    if choice.isdigit() and 1 <= int(choice) <= len(categories_list):
        return categories_list[int(choice) - 1][0]
    
    print("Invalid choice. Defaulting to web stories.")
    return "web"

# Function to get story preferences from user
def get_story_preferences():
    print("\n--- Story Preferences ---")
    topic = input("Enter story topic/theme: ").strip()
    if not topic:
        print("Topic cannot be empty.")
        return None
    
    print("Preferred length: (1) Short (~150 words), (2) Medium (~300 words), (3) Long (~500 words)")
    length = input("Select (1-3, default 2): ").strip() or "2"
    
    print("Tone: (1) Moral lesson, (2) Adventure, (3) Funny, (4) Mysterious")
    tone = input("Select (1-4, default 1): ").strip() or "1"
    
    tone_map = {"1": "moral lesson", "2": "adventure", "3": "funny", "4": "mysterious"}
    length_map = {"1": "~150 words", "2": "~300 words", "3": "~500 words"}
    
    return {
        "topic": topic,
        "length": length_map.get(length, "~300 words"),
        "tone": tone_map.get(tone, "moral lesson")
    }

# Main function with interactive menu
def main():
    global scraped_stories, current_category
    
    print("=== AI Story Generator ===")
    
    # Select category
    current_category = select_story_category()
    print(f"\nSelected category: {CATEGORIES.get(current_category)}")
    
    # Load stories based on category
    if current_category == "web":
        print("Scraping stories from web sources (this may take a few seconds)...\n")
        scraped_stories = scrape_stories()
    else:
        print(f"Loading {CATEGORIES.get(current_category)} from PDFs...\n")
        scraped_stories = load_stories_from_pdfs(current_category)
    
    if not scraped_stories:
        print(f"No stories found in {CATEGORIES.get(current_category)}.")
        return

    print(f"Storing {len(scraped_stories)} stories in ChromaDB...")
    store_in_chromadb(scraped_stories, current_category)
    
    current_story = None

    while True:
        choice = display_menu()
        
        if choice == "1":
            prefs = get_story_preferences()
            if not prefs:
                continue
            
            print("\nRetrieving relevant documents from ChromaDB...")
            docs = retrieve_relevant_docs(prefs["topic"], current_category, top_k=3)
            
            print("Generating story...")
            current_story = generate_with_rag_enhanced(prefs, docs, current_category)
            
            print("\n--- Generated Story ---\n")
            print(current_story)
            print("\n--- End ---\n")
        
        elif choice == "2":
            if not current_story:
                print("No story generated yet. Please generate a story first.")
                continue
            
            prefs = get_story_preferences()
            if not prefs:
                continue
            
            print("\nRetrieving relevant documents from ChromaDB...")
            docs = retrieve_relevant_docs(prefs["topic"], current_category, top_k=3)
            
            print("Regenerating story...")
            current_story = generate_with_rag_enhanced(prefs, docs, current_category)
            
            print("\n--- Regenerated Story ---\n")
            print(current_story)
            print("\n--- End ---\n")
        
        elif choice == "3":
            if not current_story:
                print("No story to listen to. Please generate a story first.")
                continue
            
            try:
                # Print only the extracted story text (no extra labels), then speak it in female voice
                print(current_story)
                text_to_speech(current_story)
            except Exception:
                print("Text-to-speech failed or not available on this system.")
        
        elif choice == "4":
            display_available_stories()
        
        elif choice == "5":
            new_category = select_story_category()
            if new_category != current_category:
                current_category = new_category
                print(f"\nLoading {CATEGORIES.get(current_category)} stories...\n")
                
                if current_category == "web":
                    scraped_stories = scrape_stories()
                else:
                    scraped_stories = load_stories_from_pdfs(current_category)
                
                if scraped_stories:
                    print(f"Storing {len(scraped_stories)} stories in ChromaDB...")
                    store_in_chromadb(scraped_stories, current_category)
                    current_story = None
                else:
                    print(f"No stories found in {CATEGORIES.get(current_category)}.")
        
        elif choice == "6":
            display_story_sources()
        
        elif choice == "7":
            print("Thank you for using AI Story Generator. Goodbye!")
            break
        
        else:
            print("Invalid choice. Please select 1-7.")

if __name__ == "__main__":
    main()