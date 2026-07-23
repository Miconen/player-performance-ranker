import csv
from typing import List
from src.config import Config
from src.models import Player
from src.extractors import parse_signup_sheet, fetch_internal_api_data, fetch_wom_event_data
from src.rules import calculate_ca_score, calculate_pvm_score, calculate_activity_score, apply_s_curve_normalization, calculate_synergy, detect_region

def run_pipeline(config_path: str):
    config = Config(config_path)
    print("Starting Draft Pipeline...")

    # 1. Ingestion
    print(f"Parsing CSV from {config.default_csv_path}")
    players = parse_signup_sheet(config.default_csv_path)
    print(f"Loaded {len(players)} players.")

    # 2. Extraction
    print("Fetching internal API data...")
    players = fetch_internal_api_data(players, config)

    print("Fetching WOM event data...")
    players = fetch_wom_event_data(players, config)

    # 3. Scoring
    print("Applying scoring rules...")
    for p in players:
        calculate_ca_score(p, config)
        calculate_pvm_score(p, config)
        calculate_activity_score(p, config)
        
    print("Calculating synergy...")
    players = calculate_synergy(players, config)

    print("Detecting regions...")
    players = detect_region(players)
        
    print("Normalizing scores...")
    players = apply_s_curve_normalization(players)

    # 4. Export
    export_to_csv(players, config.output_csv_path)
    print(f"Pipeline complete! Output saved to {config.output_csv_path}")

def export_to_csv(players: List[Player], output_path: str):
    # Sort by total score descending
    players.sort(key=lambda p: p.total_score, reverse=True)
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            "RSN", "Total Score (0-100)", "Raw Points",
            "PvM Score", "Activity Score", "CA Score",
            "Played Mostly on Alt", "Region", "Avg Event Percentile", "Peak Event Percentile", "Frequently Plays With"
        ])
        
        for p in players:
            writer.writerow([
                p.rsn,
                p.total_score,
                p.raw_score,
                p.score_breakdown.get('pvm_score', 0),
                p.score_breakdown.get('activity_score', 0),
                p.score_breakdown.get('ca_score', 0),
                "Yes" if p.played_mostly_on_alt else "No",
                p.region,
                p.avg_event_percentile,
                p.peak_event_percentile,
                ", ".join(p.frequently_plays_with)
            ])
