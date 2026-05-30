from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    google_api_key: str = ""
    phoenix_api_key: str = ""
    phoenix_client_url: str = "https://app.phoenix.arize.com"
    iris_port: int = 8081
    iris_env: str = "development"

    # Phoenix project + MCP server (single source of truth — agents read these)
    phoenix_project_name: str = "iris-clinical"
    phoenix_mcp_package: str = "@arizeai/phoenix-mcp@4.0.8"
    mcp_timeout_seconds: float = 120.0

    # Pattern detector thresholds
    pattern_window_minutes: int = 30
    pattern_min_samples: int = 2
    pattern_hallucination_threshold: float = 0.15  # 15%

    # Eval score thresholds
    score_pass_threshold: float = 7.0
    score_warning_threshold: float = 5.0

    gemini_model: str = "gemini-2.5-flash"
    eval_gemini_model: str = "gemini-2.5-flash"
    # MCP agents (pattern_detector, mcp_probe) use Pro: Flash frequently emits
    # MALFORMED_FUNCTION_CALL against the Phoenix MCP tool schemas.
    mcp_gemini_model: str = "gemini-2.5-pro"

    # Self-healing pipeline
    # Prompts are versioned per-agent in Phoenix as "{agent_slug}-system" (see prompt_identity.py).
    # The former single healing_prompt_name is gone — each agent owns its own namespace.
    healing_improvement_threshold: float = 0.5            # score improvement required (0-10 scale)
    healing_auto_approve: bool = True                    # True = skip human gate (demo mode only)
    healing_validation_examples: int = 5                  # failure examples to validate against
    healing_dataset_prefix: str = "iris-failures"         # dataset name = {prefix}-{query_type}
    healing_use_experiments: bool = True                  # run a Phoenix experiment to validate (SDK); fall back to in-process counterfactual

    # Autonomous scan trigger guards
    heal_cooldown_minutes: int = 30           # minimum gap before re-healing same (agent, prompt, query_type) cluster
    scan_debounce_seconds: int = 60           # minimum gap between any two scans (all tiers)
    event_trigger_multiplier: int = 3         # event-driven trigger fires when critical failure
                                              # count >= pattern_min_samples × this value

    # Seed prompt used when the clinical safety prompt does not yet exist in Phoenix.
    # Intentionally specific — gives the mutation engine concrete constraints to improve on,
    # so validation scores are high enough to pass the gate on the first heal cycle.
    healing_seed_prompt: str = (
        "You are a clinical AI assistant providing patient-specific recommendations.\n\n"
        "Safety rules you must always follow:\n"
        "1. RENAL DOSING: For medications cleared by the kidneys (vancomycin, gentamicin, "
        "methotrexate, carboplatin, etc.), check the patient's creatinine clearance (CrCl) "
        "from the retrieved context. Adjust dose or interval for CrCl < 60 mL/min. State "
        "the patient's CrCl and your adjustment explicitly.\n"
        "2. ALLERGY CHECK: Before recommending any drug, confirm the patient has no documented "
        "allergy to that drug class. If allergies are listed, name them and flag contraindications.\n"
        "3. WEIGHT-BASED DOSING: When dosing depends on body weight, use the patient's weight_kg "
        "from the retrieved context. Show the mg/kg calculation.\n"
        "4. DRUG INTERACTIONS: Check the patient's current medication list for interactions "
        "with the proposed drug. Name any interactions found.\n"
        "5. GROUNDING: Every clinical recommendation must cite the specific patient value "
        "(lab result, weight, allergy, medication) from the retrieved context that supports it. "
        "Do not infer values not present in the record."
    )

    def mcp_server_args(self) -> list[str]:
        """npx args for the Arize Phoenix MCP server. One place, used by every agent."""
        return [
            "-y",
            self.phoenix_mcp_package,
            "--baseUrl", self.phoenix_client_url,
            "--apiKey", self.phoenix_api_key,
        ]

    def healing_dataset_name(self, query_type: str) -> str:
        return f"{self.healing_dataset_prefix}-{query_type}"


settings = Settings()
