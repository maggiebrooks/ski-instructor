import json
import logging
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from ski.analysis.turn_analyzer import TurnAnalyzer
from ski.analysis.turn_insights import TurnInsights
from ski.processing.session_processor import SessionProcessor
from transformations.process_session import discover_sessions, PROCESSING_VERSION

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
)
logger = logging.getLogger(__name__)

print("=== Generating fake session ===")
subprocess.run([sys.executable, "ingestion/generate_fake_session.py"])

print()
print("=== Processing real session (White River 2-22) ===")

project_root = os.path.dirname(os.path.abspath(__file__))
data_dir = os.path.join(project_root, "data")
processed_dir = os.path.join(data_dir, "processed")
output_dir = os.path.join(project_root, "output")
db_path = os.path.join(data_dir, "ski.db")

os.makedirs(processed_dir, exist_ok=True)
os.makedirs(output_dir, exist_ok=True)

sessions = discover_sessions(data_dir)
logger.info("Found %d session(s)", len(sessions))

processor = SessionProcessor(
    db_path=db_path,
    processing_version=PROCESSING_VERSION,
)

all_summaries = {}
for session_dir in sessions:
    label = os.path.basename(session_dir)
    session_id = label.replace(" ", "_").replace("/", "_")
    summary = processor.process(
        session_id=session_id,
        raw_path=Path(session_dir),
        processed_dir=Path(processed_dir),
        output_dir=Path(output_dir),
    )
    all_summaries[label] = summary

overview_path = os.path.join(processed_dir, "all_sessions_overview.json")
with open(overview_path, "w") as f:
    json.dump(all_summaries, f, indent=2)

print()
print("=== Session insights ===")
analyzer = TurnAnalyzer(db_path)
insights = TurnInsights()
conn = sqlite3.connect(db_path)
for (session_id,) in conn.execute("SELECT session_id FROM sessions ORDER BY session_id"):
    print(f"--- {session_id} ---")
    for line in insights.session_report(analyzer, session_id):
        print(f"  {line}")
    print()
conn.close()

print("Pipeline complete.")
