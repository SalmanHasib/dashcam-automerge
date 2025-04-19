#!/usr/bin/env python3

import os
import argparse
import datetime
import random
import subprocess
from pathlib import Path

def create_dummy_video(output_path, duration=10, width=1280, height=720):
    """
    Create a dummy MP4 video file with the specified duration and resolution.
    Requires ffmpeg to be installed.
    """
    cmd = [
        "ffmpeg",
        "-f", "lavfi",
        "-i", f"color=c=blue:s={width}x{height}:d={duration}",
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-pix_fmt", "yuv420p",
        "-y",  # Overwrite output file
        output_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error creating dummy video: {result.stderr}")
        return False
    
    return True

def create_test_files(output_dir, num_front=5, num_rear=5, has_gap=True):
    """
    Create test files simulating dashcam footage.
    
    Args:
        output_dir: Directory to save the test files
        num_front: Number of front camera videos to create
        num_rear: Number of rear camera videos to create
        has_gap: Whether to create a time gap in the footage (for testing continuity)
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # Define base time
    base_time = datetime.datetime(2023, 6, 15, 12, 0, 0)
    video_duration = 10  # seconds
    event_types = ["N", "E", "M"]  # Normal, Event, Manual recording types
    
    # Create front camera videos
    for i in range(num_front):
        # Create a time gap after half the videos if requested
        if has_gap and i == num_front // 2:
            base_time += datetime.timedelta(minutes=5)
        
        # Current time for this video
        current_time = base_time + datetime.timedelta(seconds=i * video_duration)
        time_str = current_time.strftime("%Y%m%d_%H%M%S")
        
        # Random recording type
        event_type = random.choice(event_types)
        
        # Create dashcam style filename with the correct format
        filename = os.path.join(output_dir, f"{time_str}_{event_type}F.mp4")
        print(f"Creating front camera video: {filename}")
        
        # Create dummy video file
        create_dummy_video(filename, duration=video_duration)
    
    # Reset base time for rear camera videos
    base_time = datetime.datetime(2023, 6, 15, 12, 0, 0)
    
    # Create rear camera videos
    for i in range(num_rear):
        # Create a time gap after half the videos if requested
        if has_gap and i == num_rear // 2:
            base_time += datetime.timedelta(minutes=5)
        
        # Current time for this video
        current_time = base_time + datetime.timedelta(seconds=i * video_duration)
        time_str = current_time.strftime("%Y%m%d_%H%M%S")
        
        # Random recording type
        event_type = random.choice(event_types)
        
        # Create dashcam style filename with the correct format
        filename = os.path.join(output_dir, f"{time_str}_{event_type}R.mp4")
        print(f"Creating rear camera video: {filename}")
        
        # Create dummy video file
        create_dummy_video(filename, duration=video_duration)
    
    print(f"\nCreated {num_front} front camera videos and {num_rear} rear camera videos in {output_dir}")
    if has_gap:
        print("A 5-minute gap was inserted in the middle of the footage to test continuity detection")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create test files for the Dashcam Video Consolidation Tool")
    parser.add_argument("output_dir", help="Directory to save the test files")
    parser.add_argument("--front", type=int, default=5, help="Number of front camera videos to create (default: 5)")
    parser.add_argument("--rear", type=int, default=5, help="Number of rear camera videos to create (default: 5)")
    parser.add_argument("--no-gap", action="store_true", help="Don't create a time gap in the footage")
    
    args = parser.parse_args()
    
    create_test_files(args.output_dir, args.front, args.rear, not args.no_gap) 