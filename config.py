"""
Configuration for WanderAI LLM Modules
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support"""
    
    # API Keys
    GROQ_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    
    # LLM Configuration
    PRIMARY_LLM: str = "groq"  # "groq" or "gemini"
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GEMINI_MODEL: str = "gemini-1.5-flash"
    
    # API Configuration
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_VERSION: str = "v1"
    
    # RAG Configuration
    KNOWLEDGE_BASE_PATH: str = "knowledge_base"
    MAX_CONTEXT_DOCS: int = 3
    
    # Rate Limiting
    MAX_REQUESTS_PER_MINUTE: int = 30
    
    # Timeouts
    LLM_TIMEOUT_SECONDS: int = 30
    
    # Logging
    LOG_LEVEL: str = "INFO"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Global settings instance
settings = Settings()


# Validation
def validate_api_keys():
    """Validate that at least one API key is configured"""
    if not settings.GROQ_API_KEY and not settings.GEMINI_API_KEY:
        raise ValueError(
            "At least one API key must be configured. "
            "Set GROQ_API_KEY or GEMINI_API_KEY in .env file or environment variables."
        )
    
    if settings.PRIMARY_LLM == "groq" and not settings.GROQ_API_KEY:
        print("Warning: PRIMARY_LLM is 'groq' but GROQ_API_KEY is not set. Falling back to Gemini.")
        settings.PRIMARY_LLM = "gemini"
    
    if settings.PRIMARY_LLM == "gemini" and not settings.GEMINI_API_KEY:
        print("Warning: PRIMARY_LLM is 'gemini' but GEMINI_API_KEY is not set. Falling back to Groq.")
        settings.PRIMARY_LLM = "groq"


# Example .env file content
ENV_TEMPLATE = """
# WanderAI LLM Configuration
# Copy this to .env and fill in your API keys

# Get Groq API key from: https://console.groq.com/keys
GROQ_API_KEY=your_groq_api_key_here

# Get Gemini API key from: https://aistudio.google.com/apikey
GEMINI_API_KEY=your_gemini_api_key_here

# Primary LLM to use (groq or gemini)
PRIMARY_LLM=groq

# Optional: Override default models
# GROQ_MODEL=llama-3.3-70b-versatile
# GEMINI_MODEL=gemini-1.5-flash

# Optional: API Configuration
# API_HOST=0.0.0.0
# API_PORT=8000

# Optional: Logging
# LOG_LEVEL=INFO
"""


if __name__ == "__main__":
    # Create .env.example file
    with open(".env.example", "w") as f:
        f.write(ENV_TEMPLATE.strip())
    print("Created .env.example file. Copy it to .env and add your API keys.")
