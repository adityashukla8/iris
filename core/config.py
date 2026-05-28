from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    google_api_key: str = ""
    phoenix_api_key: str = ""
    phoenix_client_url: str = "https://app.phoenix.arize.com"
    iris_port: int = 8081
    iris_env: str = "development"

    # Pattern detector thresholds
    pattern_window_minutes: int = 30
    pattern_min_samples: int = 2
    pattern_hallucination_threshold: float = 0.15  # 15%

    # Eval score thresholds
    score_pass_threshold: float = 7.0
    score_warning_threshold: float = 5.0

    gemini_model: str = "gemini-2.5-pro"
    eval_gemini_model: str = "gemini-2.5-flash"
    mcp_gemini_model: str = "gemini-2.5-flash"

    # Self-healing pipeline
    healing_prompt_name: str = "orion-clinical-safety"   # name of the prompt in Phoenix
    healing_improvement_threshold: float = 1.5            # score improvement required (0-10 scale)
    healing_auto_approve: bool = True                    # True = skip human gate (demo mode only)
    healing_validation_examples: int = 5                  # failure examples to validate against


settings = Settings()
