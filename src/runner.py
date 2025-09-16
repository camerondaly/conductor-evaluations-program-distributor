# main.py
from collector_scheduler import CollectorScheduler
from src.config import SHEET_IDS

def main():
    for event_type, sheet_id in SHEET_IDS.items():
        distributor = CollectorScheduler(event_type, sheet_id)
        distributor.run()

if __name__ == "__main__":
    main()
