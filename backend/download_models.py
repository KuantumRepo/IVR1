import urllib.request
import os
import sys

URLS = {
    # We download the standard ONNX model and the voices dictionary into the backend root
    "kokoro-v1.0.onnx": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
    "voices-v1.0.bin": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"
}

def download_file(url, filename):
    print(f"Downloading {filename} from {url}...")
    try:
        urllib.request.urlretrieve(url, filename)
        print(f"Successfully downloaded {filename}.")
    except Exception as e:
        print(f"Failed to download {filename}: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Ensure we are in the backend root directory (the parent of app/)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(current_dir)
    
    for filename, url in URLS.items():
        if not os.path.exists(filename):
            download_file(url, filename)
        else:
            print(f"{filename} already exists, skipping.")
    
    print("\nAll models downloaded! You can now run the backend locally with `uvicorn app.main:app` or via Docker.")
