from src.models import Player
from src.config import Config
import math

def calculate_ca_score(player: Player, config: Config) -> Player:
    ca_values = config.ca_tier_values
    
    # We ideally want to use internal CA data, but if it's just raw task completions
    # we would sum them. The prompt mentioned "internal_ca_achievements" is a list.
    # For now, let's heavily rely on the self-reported `csv_ca_tier` as requested in the plan
    # "If internal API is empty, we check the csv_ca_tier"
    
    tier_str = player.csv_ca_tier.lower()
    score = 0.0
    
    if "grandmaster" in tier_str or "gm" in tier_str:
        score = ca_values.get("Grandmaster", 0)
        player.tags.append("#GM")
    elif "master" in tier_str:
        score = ca_values.get("Master", 0)
        player.tags.append("#MasterCA")
    elif "elite" in tier_str:
        score = ca_values.get("Elite", 0)
    elif "hard" in tier_str:
        score = ca_values.get("Hard", 0)
        
    player.score_breakdown['ca_score'] = score
    player.raw_score += score
    return player

def calculate_pvm_score(player: Player, config: Config) -> Player:
    boss_tiers = config.boss_tiers
    score = 0.0
    
    tier_1_value = boss_tiers.get("tier_1_value", 50)
    tier_1_bosses = boss_tiers.get("tier_1_bosses", [])
    
    tier_2_value = boss_tiers.get("tier_2_value", 30)
    tier_2_bosses = boss_tiers.get("tier_2_bosses", [])
    
    tier_3_value = boss_tiers.get("tier_3_value", 15)
    tier_3_bosses = boss_tiers.get("tier_3_bosses", [])

    tier_4_value = boss_tiers.get("tier_4_value", 5)
    tier_4_bosses = boss_tiers.get("tier_4_bosses", [])
    
    # Check verified internal records first
    verified_bosses_hit = set()
    for record in player.pvm_records:
        b = record.get("boss_name")
        if b and b not in verified_bosses_hit:
            verified_bosses_hit.add(b)
            if b in tier_1_bosses:
                score += tier_1_value
            elif b in tier_2_bosses:
                score += tier_2_value
            elif b in tier_3_bosses:
                score += tier_3_value
            elif b in tier_4_bosses:
                score += tier_4_value
                
    # If they have no verified records, let's use their self-reported bosses but at a 50% penalty
    if not player.pvm_records and player.csv_comfortable_bosses:
        for b in player.csv_comfortable_bosses:
            b_lower = b.lower()
            # Loose text matching
            if "awakened" in b_lower or "inferno" in b_lower or "colosseum" in b_lower or "hard mode tob" in b_lower:
                score += (tier_1_value * 0.5)
            elif "theatre of blood" in b_lower or "chambers of xeric" in b_lower or "nex" in b_lower:
                score += (tier_2_value * 0.5)
            # Just rough approximations for self-reported
            
    player.score_breakdown['pvm_score'] = score
    player.raw_score += score
    
    if score > 100:
        player.tags.append("#PVM_Carry")
        
    return player

def calculate_activity_score(player: Player, config: Config) -> Player:
    score = 0.0
    
    # Very simple activity scoring based on SOTW / Bingo placements if available
    for event in player.clan_events:
        placement = event.get('placement', 999)
        if placement == 1:
            score += 15
        elif placement <= 3:
            score += 10
        elif placement <= 10:
            score += 5
            
    # WOM Event scoring (EHB / XP)
    total_ehb = sum(stat.ehb_gained for stat in player.wom_event_stats)
    total_xp = sum(stat.non_combat_xp_gained for stat in player.wom_event_stats)
    
    # +1 pt per 5 EHB gained across tracked events, cap at 50 pts
    ehb_score = min(total_ehb / 5.0, 50)
    score += ehb_score
    
    # +1 pt per 5m XP, cap at 30 pts
    xp_score = min(total_xp / 5000000.0, 30)
    score += xp_score
    
    if ehb_score > 20 or xp_score > 20:
        player.tags.append("#Grinder")

    # Availability text parsing
    avail_lower = player.availability_notes.lower()
    if "every day" in avail_lower or "go hard" in avail_lower or "active" in avail_lower:
        player.tags.append("#Active")
    if "festival" in avail_lower or "vacation" in avail_lower or "busy" in avail_lower:
        player.tags.append("#Limited_Time")

    player.score_breakdown['activity_score'] = score
    player.raw_score += score
    return player

def apply_s_curve_normalization(players: list[Player]) -> list[Player]:
    if not players:
        return players
        
    max_raw = max(p.raw_score for p in players)
    if max_raw == 0:
        max_raw = 1 # prevent div by zero
        
    for p in players:
        # Simple logistic/S-curve mapping
        # We map the raw score [0, max_raw] to an x value [-5, 5] for the sigmoid
        x = (p.raw_score / max_raw) * 10 - 5
        sigmoid = 1 / (1 + math.exp(-x))
        # Map sigmoid [0, 1] to [0, 100]
        p.total_score = round(sigmoid * 100, 2)
        
    return players
