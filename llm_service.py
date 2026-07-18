import os
import streamlit as st
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load the environment variables from your local .env file
#load_dotenv()

# Explicitly bind the secret to an environment variable if it isn't already set locally
if "GEMINI_API_KEY" in st.secrets:
    os.environ["GEMINI_API_KEY"] = st.secrets["GEMINI_API_KEY"]

def call_gemini_engine(system_instruction: str, user_prompt: str) -> str:
    """
    A pure pass-through network layer. Takes the pre-engineered instructions 
    and prompt strings directly from setlist_engine.py and invokes the API.
    """
    # The client will now automatically pick up the GEMINI_API_KEY from the loaded environment
    client = genai.Client()
    
    response = client.models.generate_content(
        model='gemini-3.1-flash-lite', # Swap this to your preferred model string if needed
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.7 
        )
    )
    
    return response.text