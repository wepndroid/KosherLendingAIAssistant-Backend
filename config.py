from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_ENV: str = "development"
    APP_PORT: int = 8000
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_STORAGE_BUCKET: str = "kosher-knowledge"

    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-6"
    ANTHROPIC_MAX_TOKENS: int = 4000

    OPENAI_API_KEY: str = ""
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"

    PERPLEXITY_API_KEY: str = ""
    PERPLEXITY_MODEL: str = "sonar-pro"

    GHL_API_KEY: str = ""
    GHL_LOCATION_ID: str = ""
    GHL_WEBHOOK_SECRET: str = ""

    JWT_SECRET: str = "change-me"
    JWT_ALG: str = "HS256"
    JWT_TTL_HOURS: int = 24

    BRAND_NAME: str = "KosherLending"
    BRAND_NMLS: str = "320841"
    BRAND_WEBSITE: str = "KosherLending.com"
    BRAND_CREATOR: str = "Jeffrey Ben-Davis"
    BRAND_COMPLIANCE: str = "Jeffrey Ben-Davis | NMLS #320841 | KosherLending.com | Equal Housing Lender"
    EXCLUDED_STATES: str = "NY"

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def excluded_states_list(self) -> list[str]:
        return [s.strip().upper() for s in self.EXCLUDED_STATES.split(",") if s.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
