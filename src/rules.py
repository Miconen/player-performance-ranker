from src.models import Player
from src.config import Config
import math

def calculate_ca_score(player: Player, config: Config) -> Player:
    ca_values = config.ca_tier_values
    
    tier_str = player.csv_ca_tier.lower()
    score = 0.0
    
    # We heavily base this on the internal CA count since it reflects verified completions
    ca_count = len(player.internal_ca_achievements)
    
    if ca_count > 400:
        score = ca_values.get("Grandmaster", 40)
    elif ca_count > 300:
        score = ca_values.get("Master", 25)
    elif ca_count > 200:
        score = ca_values.get("Elite", 10)
    elif ca_count > 0:
        score = ca_values.get("Hard", 5)
    else:
        # Fallback to self-reported CSV if API returned no data
        if "grandmaster" in tier_str or "gm" in tier_str:
            score = ca_values.get("Grandmaster", 40)
        elif "master" in tier_str:
            score = ca_values.get("Master", 25)
        elif "elite" in tier_str:
            score = ca_values.get("Elite", 10)
        elif "hard" in tier_str:
            score = ca_values.get("Hard", 5)
        
    player.score_breakdown['raw_ca'] = score
    return player

def calculate_clan_records_score(player: Player, config: Config) -> Player:
    records_cache = getattr(config, 'guild_records_cache', {})
    global_records = records_cache.get('records', [])
    record_positions = {r.get('record_id'): r.get('position') for r in global_records}
    
    score = 0.0
    for record in player.pvm_records:
        rid = record.get('record_id')
        pos = record_positions.get(rid)
        if pos == 1:
            score += 15.0
        elif pos == 2:
            score += 10.0
        elif pos == 3:
            score += 5.0
            
    player.score_breakdown['raw_clan_records'] = score
    return player

def calculate_custom_ehb_score(player: Player, config: Config) -> Player:
    custom_ehb_pts = 0.0
    for boss_name, kills in player.boss_kills.items():
        boss_weight = config.custom_ehb_weights.get(boss_name, 0.0)
        custom_ehb_pts += (kills * boss_weight)
        
    player.score_breakdown['raw_custom_ehb'] = custom_ehb_pts
    return player

def calculate_ehp_score(player: Player, config: Config) -> Player:
    score = player.wom_ehp
    player.score_breakdown['raw_ehp'] = score
    return player

def calculate_activity_score(player: Player, config: Config) -> Player:
    score = 0.0
    
    # 75% Weight to Average Percentile Performance (Max ~75 points)
    performance_score = player.avg_event_percentile * 0.75
    score += performance_score
            
    # 25% Weight to Volume (Events played, XP)
    event_count_score = min(len(player.wom_event_stats) * 5, 10)
    
    total_xp = sum(stat.non_combat_xp_gained for stat in player.wom_event_stats)
    xp_score = min(total_xp / 5000000.0, 5)
    
    volume_score = event_count_score + xp_score
    score += volume_score

    # Add flat participation points for internal clan events
    for event in player.clan_events:
        placement = event.get('placement', 999)
        if placement == 1:
            score += 15
        elif placement <= 3:
            score += 10
        elif placement <= 10:
            score += 5

    player.score_breakdown['raw_activity'] = round(score, 2)
    return player

def apply_s_curve_normalization(players: list[Player]) -> list[Player]:
    if not players:
        return players
        
    categories = ['ca', 'clan_records', 'custom_ehb', 'ehp', 'activity']
    
    for cat in categories:
        raw_key = f"raw_{cat}"
        norm_key = f"norm_{cat}"
        max_raw = max((p.score_breakdown.get(raw_key, 0.0) for p in players), default=0.0)
        
        if max_raw == 0:
            max_raw = 1.0 # prevent div by zero
            
        for p in players:
            raw = p.score_breakdown.get(raw_key, 0.0)
            
            # Waning logarithmic curve
            ratio = math.log(raw + 1) / math.log(max_raw + 1)
            
            # Scale each category score out of 100 to balance them
            norm_score = ratio * 100.0
            
            # Add small maxed account bonus ONLY to EHP
            if cat == 'ehp' and getattr(p, 'is_maxed', False):
                norm_score = min(norm_score + 10.0, 100.0)
                
            p.score_breakdown[norm_key] = round(norm_score, 2)
            
    # Calculate Total Score by clamping raw points across all users
    for p in players:
        p.raw_score = round(sum(p.score_breakdown.get(f"raw_{c}", 0.0) for c in categories), 2)
        
    max_raw_total = max((p.raw_score for p in players), default=0.0)
    if max_raw_total == 0:
        max_raw_total = 1.0
        
    for p in players:
        ratio = math.log(p.raw_score + 1) / math.log(max_raw_total + 1)
        p.total_score = round(ratio * 100, 2)
        
    return players

def calculate_synergy(players: list[Player], config: Config) -> list[Player]:
    for p in players:
        # 1. Alt account check
        played_on_main = 0
        played_on_alt = 0
        for stat in p.wom_event_stats:
            if stat.wom_ids_used:
                if p.wom_id in stat.wom_ids_used:
                    played_on_main += 1
                else:
                    played_on_alt += 1
                    
        if played_on_alt >= played_on_main and played_on_alt > 0:
            p.played_mostly_on_alt = True

    # 3. Teammates check
    # Map each player to a set of their event teams
    player_teams = {}
    for p in players:
        teams = set()
        for stat in p.wom_event_stats:
            if stat.team_name:
                teams.add(f"wom_{stat.event_id}_{stat.team_name}")
                
        for event in p.clan_events:
            placement = event.get('placement', 999)
            solo = event.get('solo', True)
            if not solo and placement != 999:
                teams.add(f"clan_{event.get('name')}_{placement}")
        
        player_teams[p.rsn] = teams

    for p in players:
        teammate_counts = {}
        my_teams = player_teams.get(p.rsn, set())
        
        for other_p in players:
            if p.rsn == other_p.rsn:
                continue
            
            other_teams = player_teams.get(other_p.rsn, set())
            shared_teams = my_teams.intersection(other_teams)
            
            if shared_teams:
                teammate_counts[other_p.rsn] = len(shared_teams)

        synergy_list = []
        sorted_teammates = sorted(teammate_counts.items(), key=lambda item: item[1], reverse=True)
        for rsn, count in sorted_teammates:
            if count >= 2:
                synergy_list.append(f"{rsn} ({count} times)")
            else:
                synergy_list.append(f"{rsn}")
                
        p.frequently_plays_with = synergy_list
        
    return players

import re

def detect_region(players: list[Player]) -> list[Player]:
    na_keywords = [r'\bna\b', r'\best\b', r'\bcst\b', r'\bmst\b', r'\bpst\b', r'\bamerica\b', r'\busa\b', r'\bcanada\b', r'\bus\b', r'\beastern\b', r'\bcentral\b', r'\bpacific\b', r'\bmountain\b', r'\bca\b']
    eu_keywords = [r'\beu\b', r'\buk\b', r'\bgmt\b', r'\bbst\b', r'\bcet\b', r'\bcest\b', r'\beurope\b', r'\bengland\b', r'\bbelgium\b', r'\bnetherlands\b', r'\bgermany\b', r'\bgb\b']
    
    for p in players:
        tz = p.time_zone.lower()
        if any(re.search(kw, tz) for kw in na_keywords):
            p.region = "NA"
        elif any(re.search(kw, tz) for kw in eu_keywords):
            p.region = "EU"
        else:
            p.region = p.time_zone if p.time_zone.strip() else "Other"
    return players
