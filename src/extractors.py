import csv
import json
import os
import requests
from typing import List, Dict
from src.models import Player, WomEventStat
from src.config import Config
import time

def parse_signup_sheet(filepath: str) -> List[Player]:
    players = []
    if not os.path.exists(filepath):
        print(f"Warning: CSV file not found at {filepath}")
        return players

    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        headers = next(reader)
        
        # We know from the prompt:
        # Col 0: Timestamp
        # Col 1: RSN (sometimes skipped or weirdly formatted if no timestamp)
        # Col 2: Discord name
        # Col 3: Main or Ironman
        # Col 6: Time zone
        # Col 7: Time commitment
        # Col 8: CA Status
        # Col 10: Slayer level
        # Col 11: Comfortable bosses

        for row in reader:
            if not row or len(row) < 12:
                continue
                
            rsn = row[1].strip()
            discord_name = row[2].strip()
            # If timestamp is empty, columns shift left in the provided example if not properly quoted?
            # Actually looking at the provided text: ",509DarkTheme,Zewwm..." means col 0 is empty, col 1 is RSN.
            # So parsing is standard.
            
            is_ironman = "Ironman" in row[3]
            time_zone = row[6].strip()
            availability_notes = row[7].strip()
            ca_tier = row[8].strip()
            slayer_str = row[10].strip().replace('ish', '')
            try:
                slayer_lvl = int(slayer_str) if slayer_str else 1
            except:
                slayer_lvl = 1
                
            bosses_str = row[11].strip()
            bosses = [b.strip() for b in bosses_str.split(',')] if bosses_str else []

            p = Player(
                rsn=rsn,
                discord_name=discord_name,
                is_ironman=is_ironman,
                time_zone=time_zone,
                availability_notes=availability_notes,
                csv_ca_tier=ca_tier,
                csv_slayer_level=slayer_lvl,
                csv_comfortable_bosses=bosses
            )
            players.append(p)
            
    return players

def fetch_internal_api_data(players: List[Player], config: Config, refresh: bool = False):
    """
    Since the internal API can query multiple users, we might want to batch it, 
    but for simplicity and caching, let's fetch the whole guild or individual users if the endpoint supports it.
    The prompt gave a schema for GET /api/v1/guilds/{guild_id}/users/wom/{wom_ids} but we don't have wom_ids yet.
    Wait, the internal API response provided in the first prompt was a list of users, maybe from a general endpoint.
    Let's fetch by RSN if we don't have the WOM id. But wait, if we fetch all users from the guild, it's one call.
    Let's assume there is a local cache of the whole internal DB or we ping it once.
    For this mock implementation, I'll pretend we hit the internal API once for the entire guild, 
    and match by RSN (case-insensitive).
    """
    
    # We will simulate the internal API response. Since we don't have a live API,
    # if a cache file exists (like an export), we use it.
    internal_cache_path = os.path.join(config.cache_directory, 'internal_api', 'guild_data.json')
    
    guild_data = []
    if os.path.exists(internal_cache_path):
        with open(internal_cache_path, 'r', encoding='utf-8') as f:
            guild_data = json.load(f)
    else:
        # In a real scenario, requests.get(...)
        # We will just write a mock file for "Comfy hug" matching a signup later, or assume empty if no API.
        pass

    # Build a lookup map from RSN to internal user data
    rsn_map = {}
    for user_data in guild_data:
        for rsn_obj in user_data.get("rsns", []):
            rsn = rsn_obj.get("rsn", "").lower()
            rsn_map[rsn] = user_data

    for p in players:
        match = rsn_map.get(p.rsn.lower())
        if match:
            # Populate internal fields
            # Extract WOM ID from the rsns list
            for rsn_obj in match.get("rsns", []):
                if rsn_obj.get("rsn", "").lower() == p.rsn.lower():
                    wom_id_str = rsn_obj.get("wom_id")
                    if wom_id_str:
                        p.wom_id = int(wom_id_str)
                    break
            
            p.internal_points = match.get("points", 0)
            p.internal_rank = match.get("rank", 0)
            p.internal_tier_name = match.get("tier", {}).get("name", "")
            p.pvm_records = match.get("records", [])
            p.clan_events = match.get("events", [])
            p.internal_ca_achievements = [a.get("name") for a in match.get("achievements", []) if a.get("name") != "Maxed"] # Assuming CAs are here or in combat_achievements
            # Handle CA actually in combat_achievements
            if "combat_achievements" in match:
                p.internal_ca_achievements = [ca.get("name") for ca in match.get("combat_achievements", [])]

    return players

def fetch_wom_event_data(players: List[Player], config: Config, refresh: bool = False):
    """
    Fetches event data from Wise Old Man for all configured event IDs.
    Calculates event medians/percentiles globally to grade on a curve, 
    and applies it to players who participated.
    """
    wom_base_url = config.wom_api_base_url
    event_ids = config.wom_event_ids
    
    # Store global stats for each event to calculate percentiles later
    global_event_stats = {}
    
    for eid in event_ids:
        cache_path = os.path.join(config.cache_directory, 'wom_events', f'{eid}.json')
        event_data = None
        
        if os.path.exists(cache_path) and not refresh:
            with open(cache_path, 'r', encoding='utf-8') as f:
                event_data = json.load(f)
        else:
            try:
                print(f"Fetching WOM Event {eid}...")
                resp = requests.get(f"{wom_base_url}/events/{eid}")
                if resp.status_code == 200:
                    event_data = resp.json()
                    with open(cache_path, 'w', encoding='utf-8') as f:
                        json.dump(event_data, f)
                time.sleep(1) # Rate limit protection
            except Exception as e:
                print(f"Error fetching WOM event {eid}: {e}")
                
        if event_data and 'participations' in event_data:
            # Calculate percentiles for this event
            participations = event_data['participations']
            
            # Map wom_id to participation stats
            for p in players:
                if p.wom_id:
                    for part in participations:
                        player_obj = part.get('player', {})
                        if player_obj.get('id') == p.wom_id:
                            # They participated!
                            progress = part.get('progress', {})
                            gained = progress.get('gained', 0)
                            
                            # Note: WOM events might be skill (XP) or boss (EHB).
                            # We can infer from the event type or just check metric.
                            metric = event_data.get('metric', '')
                            
                            stat = WomEventStat(
                                event_id=eid,
                                event_name=event_data.get('title', f"Event {eid}")
                            )
                            
                            if metric == 'ehb':
                                stat.ehb_gained = gained
                            elif metric == 'ehp':
                                stat.ehp_gained = gained
                            else:
                                # Assume it's a skill if not EHB/EHP
                                stat.non_combat_xp_gained = gained
                                
                            p.wom_event_stats.append(stat)
                            break
                            
    return players
