import argparse
from src.engine import run_pipeline

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Old School RuneScape Clan Draft Scorer")
    parser.add_argument("--config", default="config.yaml", help="Path to the configuration YAML file")
    
    args = parser.parse_args()
    
    run_pipeline(args.config)
