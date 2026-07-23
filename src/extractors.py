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
    Fetches the internal API data for all players using their RSNs.
    """
    internal_cache_path = os.path.join(config.cache_directory, 'internal_api', 'guild_data.json')
    
    guild_data = []
    if os.path.exists(internal_cache_path) and not refresh:
        try:
            with open(internal_cache_path, 'r', encoding='utf-8') as f:
                guild_data = json.load(f)
        except:
            guild_data = []

    # If cache is empty or we are refreshing, we fetch from the API
    if not guild_data or refresh:
        rsns = [p.rsn for p in players if p.rsn]
        # We can chunk RSNs if there are too many, but for now we fetch all at once
        rsn_str = ",".join(rsns)
        url = f"{config.internal_api_base_url}/api/v1/guilds/{config.guild_id}/users/rsn/{rsn_str}"
        print(f"Fetching internal data for {len(rsns)} RSNs...")
        try:
            resp = requests.get(url)
            if resp.status_code == 200:
                guild_data = resp.json()
                
                # Ensure the directory exists before saving the cache
                cache_dir = os.path.dirname(internal_cache_path)
                os.makedirs(cache_dir, exist_ok=True)
                
                with open(internal_cache_path, 'w', encoding='utf-8') as f:
                    json.dump(guild_data, f)
            else:
                print(f"Failed to fetch internal data. Status: {resp.status_code}")
        except Exception as e:
            print(f"Error fetching internal data: {e}")

    # Also fetch the global records to map teammates for synergy
    records_cache_path = os.path.join(config.cache_directory, 'internal_api', 'guild_records.json')
    guild_records = {}
    if os.path.exists(records_cache_path) and not refresh:
        try:
            with open(records_cache_path, 'r', encoding='utf-8') as f:
                guild_records = json.load(f)
        except:
            guild_records = {}
            
    if not guild_records or refresh:
        url_records = f"{config.internal_api_base_url}/api/v1/guilds/{config.guild_id}/records"
        try:
            resp = requests.get(url_records)
            if resp.status_code == 200:
                guild_records = resp.json()
                cache_dir = os.path.dirname(records_cache_path)
                os.makedirs(cache_dir, exist_ok=True)
                with open(records_cache_path, 'w', encoding='utf-8') as f:
                    json.dump(guild_records, f)
        except Exception as e:
            print(f"Error fetching guild records: {e}")

    # Attach teammates data to players globally or handle it in rules
    # It's cleaner to save it temporarily in config or just pass it out. We will stash it in config.
    config.guild_records_cache = guild_records

    # Build a lookup map from RSN to internal user data
    rsn_map = {}
    for user_data in guild_data:
        for rsn_obj in user_data.get("rsns", []):
            rsn = rsn_obj.get("rsn", "").lower()
            rsn_map[rsn] = user_data

    for p in players:
        # Also try their discord name if RSN isn't found
        match = rsn_map.get(p.rsn.lower())
        if not match and p.discord_name.lower() in rsn_map:
            match = rsn_map.get(p.discord_name.lower())
            
        if match:
            # Populate internal fields
            p.internal_user_id = match.get("user_id")
            
            # Extract WOM ID from the rsns list
            for rsn_obj in match.get("rsns", []):
                wom_id_str = rsn_obj.get("wom_id")
                if wom_id_str:
                    wom_id_int = int(wom_id_str)
                    if wom_id_int not in p.wom_ids:
                        p.wom_ids.append(wom_id_int)
                    
                    if rsn_obj.get("rsn", "").lower() == p.rsn.lower():
                        p.wom_id = wom_id_int
                        
            if p.wom_id is None and p.wom_ids:
                p.wom_id = p.wom_ids[0]
            
            p.internal_points = match.get("points", 0)
            p.internal_rank = match.get("rank", 0)
            p.internal_tier_name = match.get("tier", {}).get("name", "")
            p.pvm_records = match.get("records", [])
            p.clan_events = match.get("events", [])
            
            p.internal_ca_achievements = [a.get("name") for a in match.get("achievements", []) if a.get("name") != "Maxed"]
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
        cache_dir = os.path.join(config.cache_directory, 'wom_events')
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, f'{eid}.json')
        event_data = None
        
        if os.path.exists(cache_path) and not refresh:
            with open(cache_path, 'r', encoding='utf-8') as f:
                event_data = json.load(f)
        else:
            try:
                print(f"Fetching WOM Event {eid}...")
                resp = requests.get(f"{wom_base_url}/competitions/{eid}")
                if resp.status_code == 200:
                    event_data = resp.json()
                    with open(cache_path, 'w', encoding='utf-8') as f:
                        json.dump(event_data, f)
                else:
                    print(f"Failed to fetch WOM event {eid}. Status: {resp.status_code}")
                time.sleep(1) # Rate limit protection
            except Exception as e:
                print(f"Error fetching WOM event {eid}: {e}")
                
        if event_data and 'participations' in event_data:
            # Calculate percentiles for this event
            participations = event_data['participations']
            all_gains = [part.get('progress', {}).get('gained', 0) for part in participations]
            all_gains = [g for g in all_gains if g > 0]
            all_gains.sort()
            total_participants = len(all_gains)
            
            # Map wom_id to participation stats
            for p in players:
                if p.wom_ids:
                    # We might have multiple accounts participating.
                    # Sum the gains from all accounts for this user in the same event
                    total_gained = 0
                    wom_ids_used = []
                    team_name = ""
                    for part in participations:
                        player_obj = part.get('player', {})
                        if player_obj.get('id') in p.wom_ids:
                            # They participated!
                            progress = part.get('progress', {})
                            gained = progress.get('gained', 0)
                            if gained > 0:
                                total_gained += gained
                                if player_obj.get('id') not in wom_ids_used:
                                    wom_ids_used.append(player_obj.get('id'))
                                if 'teamName' in part and part['teamName']:
                                    team_name = part['teamName']
                    
                    if total_gained > 0:
                        percentile = 0.0
                        if total_participants > 0:
                            # Number of people strictly less than their total gained amount
                            less_than = len([g for g in all_gains if g < total_gained])
                            percentile = (less_than / total_participants) * 100
                        
                        metric = event_data.get('metric', '')
                        
                        stat = WomEventStat(
                            event_id=eid,
                            event_name=event_data.get('title', f"Event {eid}"),
                            percentile=percentile,
                            wom_ids_used=wom_ids_used,
                            team_name=team_name
                        )
                        
                        combat_skills = {'attack', 'strength', 'defence', 'hitpoints', 'ranged', 'magic', 'prayer'}
                        
                        if metric == 'ehb':
                            stat.ehb_gained = total_gained
                        elif metric == 'ehp':
                            stat.ehp_gained = total_gained
                        elif metric in combat_skills:
                            stat.combat_xp_gained = total_gained
                        else:
                            # Assume it's a non-combat skill if not EHB/EHP and not combat
                            stat.non_combat_xp_gained = total_gained
                            
                        p.wom_event_stats.append(stat)
                            
    for p in players:
        if p.wom_event_stats:
            percentiles = [stat.percentile for stat in p.wom_event_stats]
            p.avg_event_percentile = round(sum(percentiles) / len(percentiles), 2)
            p.peak_event_percentile = round(max(percentiles), 2)
                            
    return players
