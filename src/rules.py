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
        player.tags.append("#GM")
    elif ca_count > 300:
        score = ca_values.get("Master", 25)
        player.tags.append("#MasterCA")
    elif ca_count > 200:
        score = ca_values.get("Elite", 10)
    elif ca_count > 0:
        score = ca_values.get("Hard", 5)
    else:
        # Fallback to self-reported CSV if API returned no data
        if "grandmaster" in tier_str or "gm" in tier_str:
            score = ca_values.get("Grandmaster", 40)
            player.tags.append("#GM")
        elif "master" in tier_str:
            score = ca_values.get("Master", 25)
            player.tags.append("#MasterCA")
        elif "elite" in tier_str:
            score = ca_values.get("Elite", 10)
        elif "hard" in tier_str:
            score = ca_values.get("Hard", 5)
        
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
    
    # 75% Weight to Average Percentile Performance (Max ~75 points)
    performance_score = player.avg_event_percentile * 0.75
    score += performance_score
            
    # 25% Weight to Volume (Events played, EHB, XP)
    event_count_score = min(len(player.wom_event_stats) * 5, 10)
    
    total_ehb = sum(stat.ehb_gained for stat in player.wom_event_stats)
    total_xp = sum(stat.non_combat_xp_gained for stat in player.wom_event_stats)
    
    # Cap EHB at 10 pts, XP at 5 pts
    ehb_score = min(total_ehb / 5.0, 10)
    xp_score = min(total_xp / 5000000.0, 5)
    
    volume_score = event_count_score + ehb_score + xp_score
    score += volume_score
    
    if total_ehb > 50 or total_xp > 50000000:
        player.tags.append("#Grinder")

    # Add flat participation points for internal clan events
    for event in player.clan_events:
        placement = event.get('placement', 999)
        if placement == 1:
            score += 15
        elif placement <= 3:
            score += 10
        elif placement <= 10:
            score += 5

    # Availability text parsing
    avail_lower = player.availability_notes.lower()
    if "every day" in avail_lower or "go hard" in avail_lower or "active" in avail_lower:
        player.tags.append("#Active")
    if "festival" in avail_lower or "vacation" in avail_lower or "busy" in avail_lower:
        player.tags.append("#Limited_Time")

    player.score_breakdown['activity_score'] = round(score, 2)
    player.raw_score += score
    return player

def apply_s_curve_normalization(players: list[Player]) -> list[Player]:
    if not players:
        return players
        
    max_raw = max(p.raw_score for p in players)
    if max_raw == 0:
        max_raw = 1 # prevent div by zero
        
    for p in players:
        # Use a logarithmic scale to compress extreme outliers and expand the middle pack.
        # This solves the issue of linear jumps flattening average players to 15/100.
        ratio = math.log(p.raw_score + 1) / math.log(max_raw + 1)
        p.total_score = round(ratio * 100, 2)
        
    return players

def calculate_synergy(players: list[Player], config: Config) -> list[Player]:
    # Build a lookup of internal_user_id -> player
    user_id_map = {p.internal_user_id: p for p in players if p.internal_user_id}
    
    # We use the global records cache to map record_id -> list of teammate user_ids
    guild_records = getattr(config, 'guild_records_cache', {})
    teammates_data = guild_records.get('teammates', [])
    
    # Map record_id -> set of user_ids
    record_to_users = {}
    for t in teammates_data:
        rid = t.get('record_id')
        uid = t.get('user_id')
        if rid and uid:
            if rid not in record_to_users:
                record_to_users[rid] = set()
            record_to_users[rid].add(uid)
    
    for p in players:
        teammate_counts = {} # teammate internal_user_id -> count of shared records
        for record in p.pvm_records:
            rid = record.get('record_id')
            if rid and rid in record_to_users:
                # Get the teammates on this specific record
                team_uids = record_to_users[rid]
                if len(team_uids) > 1:
                    for uid in team_uids:
                        if uid != p.internal_user_id and uid in user_id_map:
                            teammate_counts[uid] = teammate_counts.get(uid, 0) + 1
        
        # Now format it into a string
        synergy_list = []
        # Sort by most shared records
        sorted_teammates = sorted(teammate_counts.items(), key=lambda item: item[1], reverse=True)
        for uid, count in sorted_teammates:
            teammate = user_id_map[uid]
            name = teammate.discord_name if teammate.discord_name else teammate.rsn
            if count > 1:
                synergy_list.append(f"{name} ({count} records)")
            else:
                synergy_list.append(f"{name}")
                
        p.frequently_plays_with = synergy_list
        
    return players
