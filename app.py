import streamlit as st
import os
import threading
import time
import pyttsx3
from pathlib import Path
from main import (
    CATEGORIES, STORY_URLS, PDF_FOLDER,
    load_stories_from_pdfs, scrape_stories,
    store_in_chromadb, retrieve_relevant_docs,
    generate_with_rag_enhanced, load_story_urls,
    add_story_url, load_categories, add_category
)

# Helper to safely force a rerun across Streamlit versions
def safe_rerun():
    try:
        # preferred if available
        st.experimental_rerun()
        return
    except Exception:
        pass
    try:
        # fallback: tweak query params to trigger rerun if supported
        params = {}
        try:
            params = st.experimental_get_query_params()
        except Exception:
            params = {}
        params["_refresh"] = [str(time.time())]
        try:
            st.experimental_set_query_params(**params)
            return
        except Exception:
            pass
    except Exception:
        pass
    # last resort: instruct user to refresh
    st.info("Please refresh the page to see changes (manual refresh required).")

# Page configuration
st.set_page_config(
    page_title="AI Nani (AI Story Generator)",
    page_icon="📖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
    <style>
    .main-header {
        text-align: center;
        color: #2E86AB;
        margin-bottom: 30px;
    }
    .story-container {
        background-color: #F0F8FF;
        padding: 20px;
        border-radius: 10px;
        margin-top: 20px;
        border-left: 5px solid #2E86AB;
    }
    .story-title {
        color: #A23B72;
        font-size: 24px;
        font-weight: bold;
        margin-bottom: 10px;
    }

    /* Button styling for Streamlit buttons (global) */
    .stButton>button {
        background: linear-gradient(180deg, #2E86AB 0%, #1F76A0 100%);
        color: #ffffff;
        border: none;
        padding: 8px 12px;
        border-radius: 8px;
        font-weight: 600;
        box-shadow: none;
        transition: transform 0.08s ease, filter 0.08s ease;
    }
    .stButton>button:hover {
        filter: brightness(0.95);
        transform: translateY(-1px);
        cursor: pointer;
    }

    /* Different color palette for buttons inside the sidebar */
    [data-testid="stSidebar"] .stButton>button {
        background: linear-gradient(180deg, #A23B72 0%, #8b2f5f 100%);
        color: #ffffff;
    }
    [data-testid="stSidebar"] .stButton>button:hover {
        filter: brightness(0.95);
    }

    /* Slightly smaller look for inline small buttons */
    .stButton>button[role="button"] {
        padding: 6px 10px;
        border-radius: 6px;
    }

    /* Ensure file uploader and other inputs keep good spacing with new button styles */
    .css-1v3fvcr, .css-1d391kg {
        margin-bottom: 8px;
    }

    </style>
""", unsafe_allow_html=True)

# Initialize session state
if 'current_category' not in st.session_state:
    st.session_state.current_category = 'web'
if 'scraped_stories' not in st.session_state:
    st.session_state.scraped_stories = []
if 'current_story' not in st.session_state:
    st.session_state.current_story = None
if 'stories_loaded' not in st.session_state:
    st.session_state.stories_loaded = False

# Initialize audio control state
if 'audio_playing' not in st.session_state:
    st.session_state.audio_playing = False
if 'audio_paused' not in st.session_state:
    st.session_state.audio_paused = False
if 'audio_file_path' not in st.session_state:
    st.session_state.audio_file_path = None

# Function to generate audio file from text
def generate_audio_file(text):
    """Convert text to speech and save to MP3 file"""
    try:
        engine = pyttsx3.init()
        
        # Select Indian accent voice
        try:
            voices = engine.getProperty('voices') or []
            selected_voice = None
            
            indian_keys = ("indian", "india", "aditi", "neena", "hindi", "en_in", "en-in", "en_in.utf8")
            for v in voices:
                name_id = " ".join(filter(None, [getattr(v, "name", ""), getattr(v, "id", "")])).lower()
                if any(k in name_id for k in indian_keys):
                    selected_voice = v
                    break
            
            if not selected_voice:
                for v in voices:
                    langs = getattr(v, "languages", None)
                    if langs and any("in" in str(l).lower() for l in langs):
                        selected_voice = v
                        break
            
            if not selected_voice:
                for v in voices:
                    name_id = " ".join(filter(None, [getattr(v, "name", ""), getattr(v, "id", "")])).lower()
                    if any(k in name_id for k in ("female", "zira", "samantha", "karen")):
                        selected_voice = v
                        break
            
            if not selected_voice and len(voices) > 1:
                selected_voice = voices[1]
            
            if selected_voice:
                engine.setProperty('voice', selected_voice.id)
            
            rate = engine.getProperty('rate')
            engine.setProperty('rate', int(rate * 0.98))
        
        except Exception:
            pass
        
        # Create temp directory for audio files
        temp_dir = Path("./temp_audio")
        temp_dir.mkdir(exist_ok=True)
        
        # Save audio file
        audio_file = temp_dir / "story_audio.mp3"
        engine.save_to_file(text, str(audio_file))
        engine.runAndWait()
        
        return str(audio_file)
    
    except Exception as e:
        st.error(f"Error generating audio: {str(e)}")
        return None

# Header: centered large logo above the page title
logo_path = os.path.join(os.path.dirname(__file__), "image", "logo.png")
if os.path.exists(logo_path):
    # use a 3-column layout to center the image in the middle column
    left, middle, right = st.columns([1, 2, 1])
    with middle:
        st.image(logo_path, width=360)  # adjust width as desired (e.g., 360)
        st.markdown(
            "<h1 style='text-align:center; margin-top:10px; color:#2E86AB'>📖 AI Nani - AI Story Generator</h1>",
            unsafe_allow_html=True,
        )
else:
    st.markdown("<h1 class='main-header'>📖 AI Nani - AI Story Generator</h1>", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.header("⚙️ Settings")
    
    # Category selection
    st.subheader("Story Category")
    category_options = list(CATEGORIES.items())
    selected_idx = next((i for i, (k, v) in enumerate(category_options) if k == st.session_state.current_category), 0)
    selected_category = st.selectbox(
        "Select story category:",
        options=[cat[0] for cat in category_options],
        format_func=lambda x: CATEGORIES[x],
        index=selected_idx,
        key="category_select"
    )
    
    # Load stories when category changes
    if selected_category != st.session_state.current_category:
        st.session_state.current_category = selected_category
        st.session_state.stories_loaded = False
    
    if st.button("Load Stories", key="load_btn"):
        with st.spinner("Loading stories..."):
            if st.session_state.current_category == "web":
                st.session_state.scraped_stories = scrape_stories()
            else:
                st.session_state.scraped_stories = load_stories_from_pdfs(st.session_state.current_category)
            
            if st.session_state.scraped_stories:
                store_in_chromadb(st.session_state.scraped_stories, st.session_state.current_category)
                st.session_state.stories_loaded = True
                st.success(f"Loaded {len(st.session_state.scraped_stories)} stories!")
            else:
                st.error("No stories found in this category.")
    
    st.divider()
    
    # Story sources
    st.subheader("📚 Story Sources")
    if st.session_state.current_category == "web":
        for i, url in enumerate(STORY_URLS, 1):
            st.caption(f"{i}. {url}")
    else:
        if st.session_state.scraped_stories:
            sources = set(story["source"] for story in st.session_state.scraped_stories)
            for i, source in enumerate(sorted(sources), 1):
                st.caption(f"{i}. {source}")

    # Admin controls
    st.divider()
    st.subheader("🔐 Admin")
    with st.expander("Manage Categories & Upload PDFs", expanded=False):
        # Reload categories each render to get latest file state
        categories = load_categories()
        cat_keys = list(categories.keys())
        chosen_cat = st.selectbox("Select category for upload:", options=cat_keys, format_func=lambda k: categories[k])

        st.markdown("**Create a new category**")
        new_cat_key = st.text_input("Category key (no spaces)", placeholder="e.g., folklore")
        new_cat_display = st.text_input("Display name", placeholder="e.g., Folklore Stories")
        if st.button("➕ Create Category"):
            if not new_cat_key.strip():
                st.error("Category key required.")
            else:
                ok = add_category(new_cat_key.strip(), new_cat_display.strip() or new_cat_key.strip())
                # ensure folder exists
                new_dir = os.path.join(PDF_FOLDER, new_cat_key.strip())
                os.makedirs(new_dir, exist_ok=True)
                if ok:
                    st.success(f"Category '{new_cat_key}' added. Reloading UI...")
                    safe_rerun()
                else:
                    st.warning("Category already exists or failed to add.")

        st.markdown("---")
        st.markdown("**Upload PDFs to selected category**")
        uploaded = st.file_uploader("Choose PDF files", type=["pdf"], accept_multiple_files=True)
        if uploaded:
            if st.button("Upload PDFs"):
                saved = 0
                for up in uploaded:
                    try:
                        dest_dir = os.path.join(PDF_FOLDER, chosen_cat)
                        os.makedirs(dest_dir, exist_ok=True)
                        dest_path = os.path.join(dest_dir, up.name)
                        with open(dest_path, "wb") as f:
                            f.write(up.getbuffer())
                        saved += 1
                    except Exception as e:
                        st.error(f"Failed to save {up.name}: {str(e)}")
                if saved:
                    st.success(f"Saved {saved} file(s) to category '{categories[chosen_cat]}'")
                    # Extract stories from newly uploaded PDFs and store
                    new_stories = load_stories_from_pdfs(chosen_cat)
                    if new_stories:
                        store_in_chromadb(new_stories, chosen_cat)
                        st.success(f"Extracted and stored {len(new_stories)} story(ies) from uploaded PDFs.")
                    else:
                        st.info("No stories extracted from uploaded PDFs.")
                    safe_rerun()

    with st.expander("Manage Story URLs", expanded=False):
        st.markdown("Add a new story URL (one at a time)")
        new_url = st.text_input("New story URL", placeholder="https://example.com/story-page")
        if st.button("Add URL"):
            if not new_url.strip():
                st.error("Please enter a URL.")
            else:
                ok = add_story_url(new_url.strip())
                if ok:
                    st.success("URL added. Reloading URLs...")
                    safe_rerun()
                else:
                    st.warning("URL already present or failed to add.")

        st.markdown("**Current story URLs**")
        urls = load_story_urls()
        for i, u in enumerate(urls, 1):
            st.caption(f"{i}. {u}")

# Main content area
if not st.session_state.stories_loaded:
    st.info("👈 Please load stories from the sidebar to get started!")
else:
    tab1, tab2, tab3, tab4 = st.tabs(["🎯 Generate Story", "📋 Browse Stories", "🔊 Listen", "ℹ️ About"])
    
    with tab1:
        st.subheader("Generate a New Story")
        
        col1, col2 = st.columns(2)
        
        with col1:
            topic = st.text_input("📝 Story Topic/Theme", placeholder="e.g., kindness, friendship, adventure")
            length = st.selectbox(
                "📏 Preferred Length",
                options=["~150 words", "~300 words", "~500 words"],
                index=1
            )
        
        with col2:
            tone = st.selectbox(
                "🎭 Story Tone",
                options=["moral lesson", "adventure", "funny", "mysterious"],
                index=0
            )
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("✨ Generate Story", key="generate_btn", use_container_width=True):
                if not topic:
                    st.error("Please enter a story topic!")
                else:
                    with st.spinner("Retrieving relevant stories..."):
                        docs = retrieve_relevant_docs(topic, st.session_state.current_category, top_k=3)
                    
                    with st.spinner("Generating story..."):
                        prefs = {
                            "topic": topic,
                            "length": length,
                            "tone": tone
                        }
                        st.session_state.current_story = generate_with_rag_enhanced(
                            prefs, docs, st.session_state.current_category
                        )
                    
                    st.success("Story generated successfully!")
        
        with col2:
            if st.button("🔄 Regenerate", key="regenerate_btn", use_container_width=True, disabled=st.session_state.current_story is None):
                if st.session_state.current_story is None:
                    st.error("Generate a story first!")
                else:
                    with st.spinner("Retrieving relevant stories..."):
                        docs = retrieve_relevant_docs(topic, st.session_state.current_category, top_k=3)
                    
                    with st.spinner("Regenerating story..."):
                        prefs = {
                            "topic": topic,
                            "length": length,
                            "tone": tone
                        }
                        st.session_state.current_story = generate_with_rag_enhanced(
                            prefs, docs, st.session_state.current_category
                        )
                    
                    st.success("Story regenerated!")
        
        if st.session_state.current_story:
            st.divider()
            st.markdown("<div class='story-container'>", unsafe_allow_html=True)
            st.markdown(f"<div class='story-title'>Generated Story</div>", unsafe_allow_html=True)
            st.write(st.session_state.current_story)
            st.markdown("</div>", unsafe_allow_html=True)
    
    with tab2:
        st.subheader("📚 Browse Available Stories")
        
        if st.session_state.scraped_stories:
            story_count = len(st.session_state.scraped_stories)
            st.info(f"Total stories available: {story_count}")
            
            # Create columns for story display
            for i, story_obj in enumerate(st.session_state.scraped_stories):
                with st.expander(f"📖 {story_obj.get('title', 'Untitled')} - {story_obj['source']}", expanded=False):
                    st.write(story_obj["content"])
                    st.caption(f"Source: {story_obj['source']}")
        else:
            st.warning("No stories loaded. Please load stories from the sidebar.")
    
    with tab3:
        st.subheader("🔊 Listen to Story")
        
        if st.session_state.current_story:
            st.write("Click the button below to generate and listen to the story:")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if st.button("🎵 Generate Audio", key="generate_audio_btn", use_container_width=True):
                    with st.spinner("Generating audio file..."):
                        audio_file = generate_audio_file(st.session_state.current_story)
                        if audio_file and os.path.exists(audio_file):
                            st.session_state.audio_file_path = audio_file
                            st.success("✅ Audio generated successfully!")
                        else:
                            st.error("Failed to generate audio file")
            
            with col2:
                if st.button("🗑️ Clear Audio", key="clear_audio_btn", use_container_width=True):
                    st.session_state.audio_file_path = None
                    st.info("Audio cleared")
            
            with col3:
                if st.button("🔄 Regenerate Audio", key="regen_audio_btn", use_container_width=True):
                    with st.spinner("Regenerating audio file..."):
                        audio_file = generate_audio_file(st.session_state.current_story)
                        if audio_file and os.path.exists(audio_file):
                            st.session_state.audio_file_path = audio_file
                            st.success("✅ Audio regenerated!")
                        else:
                            st.error("Failed to regenerate audio")
            
            st.divider()
            
            # Audio player
            if st.session_state.audio_file_path and os.path.exists(st.session_state.audio_file_path):
                st.subheader("🎧 Audio Player")
                with open(st.session_state.audio_file_path, 'rb') as audio_file:
                    st.audio(audio_file, format="audio/mp3")
                st.info("Use the player controls above to play, pause, or stop the audio")
            else:
                st.info("👆 Click 'Generate Audio' button above to create audio from the story")
            
            st.divider()
            st.markdown("<div class='story-container'>", unsafe_allow_html=True)
            st.markdown(f"<div class='story-title'>Story Text</div>", unsafe_allow_html=True)
            st.write(st.session_state.current_story)
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.warning("❌ No story generated yet. Please generate a story in the 'Generate Story' tab first.")

    with tab4:
        st.subheader("ℹ️ About AI Nani - AI Story Generator")
        
        st.markdown("""
        ### Features
        - 📚 **Multiple Story Sources**: Load stories from PDFs or web sources
        - 🎯 **Category Selection**: Choose from Mythological, Historical, Moral, or Web stories
        - ✨ **AI-Powered Generation**: Generate new stories using OpenAI (with fallback to retrieved stories)
        - 🔊 **Text-to-Speech**: Listen to stories with Indian-accented female voice
        - 🔍 **Smart Retrieval**: Uses ChromaDB for semantic search of relevant stories
        
        ### How to Use
        1. **Load Stories**: Select a category and click "Load Stories" in the sidebar
        2. **Generate**: Enter a topic, select tone and length, then click "Generate Story"
        3. **Browse**: View all available stories in the "Browse Stories" tab
        4. **Listen**: Click "Play Audio" to hear the story read aloud
        
        ### Categories
        - **Web Stories**: Scraped from moral stories websites
        - **Mythological**: Stories from PDF files in the mythological folder
        - **Historical**: Stories from PDF files in the historical folder
        - **Moral**: Stories from PDF files in the moral folder
        
        ### Requirements
        - OpenAI API key (optional, for full AI generation)
        - PyPDF2 (for PDF extraction)
        - ChromaDB (for semantic search)
        - pyttsx3 (for text-to-speech)
        """)

# Footer
st.divider()
st.markdown("<p style='text-align: center; color: #888;'>© 2025 AI Nani - AI Story Generator | Made with ❤️ using Streamlit</p>", unsafe_allow_html=True)
