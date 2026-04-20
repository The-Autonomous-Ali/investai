"""
Kaggle notebook cell — self-host Gemma 3 12B via Ollama + expose over ngrok.

Paste this whole cell into a Kaggle notebook with a GPU accelerator (T4 x2 or P100).
Replace NGROK_TOKEN with your own token from https://dashboard.ngrok.com/get-started/your-authtoken
Do NOT commit your token. It should stay only in the Kaggle cell.

After running, copy the printed API URL and set it in backend/.env as:
  KAGGLE_LLM_URL=<url>
  KAGGLE_LLM_MODEL=gemma3:12b
  AI_PROVIDER=kaggle   # or 'auto' if you want per-agent routing
"""

# --- STEP 1: INSTALL SYSTEM DEPENDENCIES ---
print(">>> Installing system tools...")
get_ipython().system('apt-get update && apt-get install -y zstd')

# --- STEP 2: INSTALL OLLAMA ---
print(">>> Installing Ollama engine...")
get_ipython().system('curl -fsSL https://ollama.com/install.sh | sh')
get_ipython().system('pip install -q pyngrok')

# --- STEP 3: SET UP THE TUNNEL ---
from pyngrok import ngrok
import subprocess
import os
import time

NGROK_TOKEN = "PASTE_YOUR_NGROK_TOKEN_HERE"
ngrok.set_auth_token(NGROK_TOKEN)

# --- STEP 4: START OLLAMA IN THE BACKGROUND ---
print(">>> Starting AI Engine...")
os.environ["OLLAMA_HOST"] = "0.0.0.0"
subprocess.Popen(["ollama", "serve"])
time.sleep(10)

# --- STEP 5: DOWNLOAD GEMMA 3 12B ---
# gemma3:12b ~= 8 GB, fits comfortably on T4 (16 GB VRAM)
# If you have P100 or A100, you can switch to gemma3:27b (~17 GB) for better reasoning.
print(">>> Downloading Gemma 3 12B (takes 5-10 minutes on first run)...")
get_ipython().system('ollama pull gemma3:12b')

# --- STEP 6: GO LIVE ---
public_url = ngrok.connect(11434, "http")
print("\n" + "=" * 40)
print("SUCCESS — your Kaggle brain is live")
print(f"API URL: {public_url.public_url}")
print("=" * 40)
print("\nAdd to backend/.env in Codespace:")
print(f"KAGGLE_LLM_URL={public_url.public_url}")
print("KAGGLE_LLM_MODEL=gemma3:12b")
