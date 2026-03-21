import csv
import random
import time
import os
import uuid
import logging

session_id = str(uuid.uuid4())
user_id = "will_test_user"
def generate_fake_session(duration_seconds=60, sample_rate=10):
    rows = []
    total_samples = duration_seconds * sample_rate

    for i in range(total_samples):
        timestamp = time.time() + i * (1/sample_rate)

        row = {
            "session_id": session_id,
            "user_id": user_id,
            "timestamp": timestamp,
            "accel_x": random.uniform(-2, 2),
            "accel_y": random.uniform(-2, 2),
            "accel_z": random.uniform(8, 11),
            "gyro_x": random.uniform(-1, 1),
            "gyro_y": random.uniform(-1, 1),
            "gyro_z": random.uniform(-1, 1),
        }

        rows.append(row)

    return rows


def save_to_csv(rows, filename):
    keys = rows[0].keys()
    with open(filename, "w", newline="") as output_file:
        dict_writer = csv.DictWriter(output_file, fieldnames=keys)
        dict_writer.writeheader()
        dict_writer.writerows(rows)


if __name__ == "__main__":
    session_data = generate_fake_session()
    os.makedirs("data/raw", exist_ok=True)
    save_to_csv(session_data, "data/raw/session_1.csv")
    logging.info("Fake session saved.")