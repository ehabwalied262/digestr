from faster_whisper import WhisperModel
print("Downloading Whisper 'small' model (this may take a minute or two)...")
# This forces the download to your local HuggingFace cache
WhisperModel("small", device="cpu", compute_type="int8")
print("Download complete! Your local AI is ready.")