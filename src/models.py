from dataclasses import dataclass, field
from typing import List, Dict, Optional

@dataclass
class WomEventStat:
    event_id: int
    event_name: str
    ehb_gained: float = 0.0
    ehp_gained: float = 0.0
    combat_xp_gained: int = 0
    non_combat_xp_gained: int = 0

@dataclass
class Player:
    # --- 1. Base Data (From the Sign-up CSV) ---
    rsn: str
    discord_name: str
    is_ironman: bool
    time_zone: str
    availability_notes: str
    csv_ca_tier: str
    csv_slayer_level: int
    csv_comfortable_bosses: List[str] = field(default_factory=list)
    
    # --- 2. Enriched Data (From Internal API) ---
    wom_id: Optional[int] = None
    internal_points: int = 0
    internal_rank: int = 0
    internal_tier_name: str = ""
    pvm_records: List[Dict] = field(default_factory=list)
    clan_events: List[Dict] = field(default_factory=list)
    internal_ca_achievements: List[str] = field(default_factory=list)
    
    # --- 3. Enriched Data (From WOM API Events) ---
    wom_event_stats: List[WomEventStat] = field(default_factory=list)
    
    # --- 4. Scoring & Output (From the Rule Engine) ---
    score_breakdown: Dict[str, float] = field(default_factory=dict) 
    raw_score: float = 0.0
    total_score: float = 0.0  # Clamped score
    tags: List[str] = field(default_factory=list) 
    frequently_plays_with: List[str] = field(default_factory=list)

    # Relative performance metrics across all events
    avg_event_percentile: float = 0.0
    peak_event_percentile: float = 0.0
