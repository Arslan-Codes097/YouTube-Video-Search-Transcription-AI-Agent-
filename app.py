import re
import streamlit as st

from agent import run_agent
from config import ALLOWED_MODELS, DEFAULT_MODEL

st.set_page_config(page_title="VidScribe.AI", layout="centered")

# Header Section
st.title("VidScribe.AI")
st.caption("Agent powered by Groq + SerpApi")

st.markdown("##### Workflow: Think of a Topic → Get a YouTube Video Link + Verbatim Transcription")
st.markdown("---")

with st.sidebar:
    st.header("Settings")
    model = st.selectbox("Groq Model", ALLOWED_MODELS, index=ALLOWED_MODELS.index(DEFAULT_MODEL))

query = st.text_input("Enter a Topic or YT Video URL", placeholder="e.g. Neural Networks explained in 5 minutes or https://youtu.be/...")
run_button = st.button("Run VidScribe Agent", use_container_width=True)

if run_button and query.strip():
    status_container = st.status("Initializing VidScribe Agent workflow...", expanded=True)

    def on_progress(tool_name, state, data):
        if tool_name == "search_youtube_video":
            if state == "started":
                status_container.write("1. Searching YouTube via SerpApi...")
            elif state == "completed":
                title = data.get("title", "Video found")
                url = data.get("url", "")
                status_container.write(f"✓ Step 1 Completed: Found video '{title}' ({url})")
        elif tool_name == "transcribe_video":
            if state == "started":
                status_container.write("2. Extracting verbatim transcript via SerpApi...")
            elif state == "completed":
                saved_path = data.get("saved_path", "")
                status_container.write(f"✓ Step 2 Completed: Transcript extracted & saved to Knowledge Base ({saved_path})")

    result = run_agent(query, model=model, progress_callback=on_progress)
    
    if result.get("transcript"):
        status_container.update(label="VidScribe Workflow Completed Successfully!", state="complete", expanded=False)
    else:
        status_container.update(label="Workflow Encountered an Issue", state="error", expanded=True)

    if result["transcript"] is None:
        st.error(result["answer"])
    else:
        st.markdown("### Verbatim Transcript")
        st.text_area("Transcript Output", value=result["transcript"], height=350, label_visibility="collapsed")
        st.markdown(f"**Source Video:** [{result['source_url']}]({result['source_url']})")
        
        video_id_match = re.search(r"(?:v=|youtu\.be/)([\w-]+)", result["source_url"])
        vid_id = video_id_match.group(1) if video_id_match else "unknown"
        
        st.download_button(
            label="Download Transcript (.txt)",
            data=f"Source: {result['source_url']}\n\n{result['transcript']}",
            file_name=f"transcript_{vid_id}.txt",
            mime="text/plain",
            use_container_width=True,
        )
