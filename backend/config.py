import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

class Settings:
    @property
    def DEEPGRAM_API_KEY(self) -> str:
        load_dotenv(dotenv_path=env_path, override=True)
        return os.getenv("DEEPGRAM_API_KEY", "").strip()
    
    @property
    def GEMINI_API_KEY(self) -> str:
        load_dotenv(dotenv_path=env_path, override=True)
        return os.getenv("GEMINI_API_KEY", "").strip()
    
    @property
    def GEMINI_MODEL(self) -> str:
        load_dotenv(dotenv_path=env_path, override=True)
        return os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    
    @property
    def ELEVENLABS_API_KEY(self) -> str:
        load_dotenv(dotenv_path=env_path, override=True)
        return os.getenv("ELEVENLABS_API_KEY", "").strip()
    
    @property
    def ELEVENLABS_VOICE_ID(self) -> str:
        return os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM").strip()
    
    @property
    def ELEVENLABS_MODEL_ID(self) -> str:
        return os.getenv("ELEVENLABS_MODEL_ID", "eleven_turbo_v2_5").strip()
    
    # Server
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"
    
    # Database
    DATA_DIR: Path = Path(__file__).resolve().parent.parent / "data"

settings = Settings()
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
