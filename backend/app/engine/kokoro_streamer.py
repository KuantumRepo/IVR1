import logging
from kokoro import KPipeline

logger = logging.getLogger(__name__)

# Cache pipeline globally to avoid reloading models on every call
_pipeline = None

def get_kokoro_pipeline():
    global _pipeline
    if _pipeline is None:
        logger.info("Initializing Kokoro TTS Pipeline for low-latency streaming")
        # Load English model natively. Use CPU by default as per Docker setup.
        _pipeline = KPipeline(lang_code='a') 
    return _pipeline

async def generate_tts_stream(text: str, voice: str = "af_heart"):
    """
    Generates TTS audio on the fly directly into memory buffers 
    instead of touching the disk, radically reducing latency.
    """
    pipeline = get_kokoro_pipeline()
    
    # Returns a generator for instant progressive streaming
    generator = pipeline(text, voice=voice, speed=1)
    
    # In a true streaming environment communicating with FreeSWITCH, 
    # we would pipe these chunks directly via uuid_broadcast using raw L16 PCM formats over an open socket.
    for i, (gs, ps, audio) in enumerate(generator):
        yield audio
