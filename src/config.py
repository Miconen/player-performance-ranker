import yaml

class Config:
    def __init__(self, config_path: str):
        with open(config_path, 'r') as f:
            self._config = yaml.safe_load(f)

    @property
    def internal_api_base_url(self) -> str:
        return self._config.get("internal_api_base_url", "")
    
    @property
    def guild_id(self) -> str:
        return self._config.get("guild_id", "")

    @property
    def wom_api_base_url(self) -> str:
        return self._config.get("wom_api_base_url", "")

    @property
    def default_csv_path(self) -> str:
        return self._config.get("default_csv_path", "./data/signups.csv")

    @property
    def output_csv_path(self) -> str:
        return self._config.get("output_csv_path", "./data/draft_ratings.csv")

    @property
    def cache_directory(self) -> str:
        return self._config.get("cache_directory", "./data_cache")

    @property
    def wom_event_ids(self) -> list[int]:
        return self._config.get("wom_event_ids", [])

    @property
    def boss_tiers(self) -> dict:
        return self._config.get("boss_tiers", {})

    @property
    def ca_tier_values(self) -> dict:
        return self._config.get("ca_tier_values", {})

    @property
    def event_percentile_weights(self) -> dict:
        return self._config.get("event_percentile_weights", {})
