import os
import streamlit as st
from google import genai
from google.genai import types

def call_gemini_engine(system_instruction: str, user_prompt: str) -> str:
    """
    A pure pass-through network layer. Takes the pre-engineered instructions 
    and prompt strings directly from setlist_engine.py and invokes the API.
    """
    # Force alignment immediately before creating the network channel
    if "GEMINI_API_KEY" in st.secrets:
        os.environ["GEMINI_API_KEY"] = st.secrets["GEMINI_API_KEY"]
        
    # Moving this inside the function guarantees it reads the live environment variables
    client = genai.Client()
    
    response = client.models.generate_content(
        model='gemini-3.1-flash-lite', 
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.7 
        )
    )
    
    return response.text