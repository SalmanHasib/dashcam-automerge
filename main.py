#!/usr/bin/env python3

import os
import re
import subprocess
import argparse
import datetime
import json
import sys
from collections import defaultdict

def parse_filename(filename):
    """
    Parse dashcam filename to extract timestamp and camera type.
    Supports multiple dashcam formats:
    
    1. Main format: [YYYYMMDD]_[HHMMSS]_[type][direction].mp4
       where direction is 'F' for front camera or 'R' for rear camera
    
    2. BlackVue format: [prefix]_[YYYYMMDD]_[HHMMSS]_[direction].mp4
    
    3. Generic format with date/time in filename and front/rear indicator
    
    Returns a dict with timestamp, camera_type, and filename if successful,
    None otherwise.
    """
    # Try main format [YYYYMMDD]_[HHMMSS]_[type][direction].mp4
    main_pattern = r'(\d{8})_(\d{6})_\w+([FR])\.mp4'
    match = re.match(main_pattern, filename)
    
    if match:
        date_str, time_str, direction = match.groups()
        timestamp_str = f"{date_str}_{time_str}"
        try:
            timestamp = datetime.datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
            return {
                "timestamp": timestamp,
                "camera_type": "front" if direction == "F" else "rear",
                "filename": filename
            }
        except ValueError:
            # Invalid date/time format
            pass
    
    # Try BlackVue format
    blackvue_pattern = r'.*_(\d{8})_(\d{6})_([FR])\.mp4'
    match = re.match(blackvue_pattern, filename)
    
    if match:
        date_str, time_str, camera_type = match.groups()
        timestamp_str = f"{date_str}_{time_str}"
        try:
            timestamp = datetime.datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
            return {
                "timestamp": timestamp,
                "camera_type": "front" if camera_type == "F" else "rear",
                "filename": filename
            }
        except ValueError:
            # Invalid date/time format
            pass
    
    # Try alternative formats
    # Pattern that looks for date (YYYYMMDD) and time (HHMMSS) anywhere in filename
    alt_pattern = r'.*(\d{8}).*(\d{6}).*'
    match = re.match(alt_pattern, filename)
    
    if match:
        date_str, time_str = match.groups()
        timestamp_str = f"{date_str}_{time_str}"
        try:
            timestamp = datetime.datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
            
            # Try to determine camera type from filename
            camera_type = "unknown"
            if re.search(r'front|fwd|frnt|f\b', filename.lower()):
                camera_type = "front"
            elif re.search(r'rear|back|rr|r\b', filename.lower()):
                camera_type = "rear"
                
            return {
                "timestamp": timestamp,
                "camera_type": camera_type,
                "filename": filename
            }
        except ValueError:
            # Invalid date/time format
            pass
    
    # No supported format found
    return None

def get_video_duration(filepath):
    """Get the duration of a video file in seconds using ffprobe."""
    cmd = [
        "ffprobe", 
        "-v", "error", 
        "-show_entries", "format=duration", 
        "-of", "json", 
        filepath
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error getting duration for {filepath}: {result.stderr}")
        return None
    
    try:
        data = json.loads(result.stdout)
        return float(data['format']['duration'])
    except (json.JSONDecodeError, KeyError):
        print(f"Error parsing duration data for {filepath}")
        return None

def group_videos_by_continuity(videos, max_gap=120.0, input_dir=None):
    """
    Group videos into continuous sequences.
    max_gap: maximum allowed gap in seconds between videos to consider them continuous
    """
    if not videos:
        return []
    
    # Sort videos by timestamp
    sorted_videos = sorted(videos, key=lambda x: x["timestamp"])
    
    groups = []
    current_group = [sorted_videos[0]]
    
    for i in range(1, len(sorted_videos)):
        current_video = sorted_videos[i]
        prev_video = sorted_videos[i-1]
        
        # Get the path to the previous video
        prev_path = os.path.join(input_dir, prev_video["filename"])
        
        # Get duration of previous video
        prev_duration = get_video_duration(prev_path)
        if prev_duration is None:
            # If we can't get duration, assume videos are continuous
            current_group.append(current_video)
            continue
        
        # Calculate end time of previous video
        prev_end_time = prev_video["timestamp"] + datetime.timedelta(seconds=prev_duration)
        
        # Calculate time gap
        time_gap = (current_video["timestamp"] - prev_end_time).total_seconds()
        
        if time_gap <= max_gap:
            # Videos are continuous
            current_group.append(current_video)
        else:
            # Start a new group
            groups.append(current_group)
            current_group = [current_video]
    
    # Add the last group
    if current_group:
        groups.append(current_group)
    
    return groups

def generate_trim_info(video_files, input_dir):
    """
    Generate trimming information for each video to avoid overlaps.
    Returns a list of dicts with start_time, duration, and file_path.
    """
    if not video_files:
        return []
    
    # Parse video info and sort by timestamp
    video_info = []
    for file_path in video_files:
        filename = os.path.basename(file_path)
        info = parse_filename(filename)
        if info:
            info["file_path"] = file_path
            video_info.append(info)
    
    sorted_videos = sorted(video_info, key=lambda x: x["timestamp"])
    
    # Calculate trim points
    trim_info = []
    for i, video in enumerate(sorted_videos):
        # Get duration of current video
        duration = get_video_duration(video["file_path"])
        if duration is None:
            # Skip if we can't get duration
            continue
        
        # For the first video, include the whole clip
        if i == 0:
            trim_info.append({
                "file_path": video["file_path"],
                "start_time": 0,
                "duration": duration
            })
            continue
        
        # For subsequent videos, check overlap with previous
        prev_video = sorted_videos[i-1]
        prev_end_time = prev_video["timestamp"] + datetime.timedelta(seconds=get_video_duration(prev_video["file_path"]))
        
        # Calculate overlap
        current_start_time = video["timestamp"]
        overlap_seconds = max(0, (prev_end_time - current_start_time).total_seconds())
        
        # If there's overlap, trim the start of current video
        start_time = min(overlap_seconds, duration)
        new_duration = max(0, duration - start_time)
        
        # Only add if there's anything left after trimming
        if new_duration > 0:
            trim_info.append({
                "file_path": video["file_path"],
                "start_time": start_time,
                "duration": new_duration
            })
    
    return trim_info

def merge_videos_with_trim(video_files, output_file, input_dir, use_gpu=True, cpu_threads=0):
    """
    Merge video files using ffmpeg, trimming overlapping parts.
    Leverages GPU acceleration if available and preserves input quality.
    
    Args:
        video_files: List of video file paths to merge
        output_file: Path to the output file
        input_dir: Directory containing the input files
        use_gpu: Whether to attempt to use GPU acceleration
        cpu_threads: Number of CPU threads to use (0=auto)
    """
    # Generate trim information
    trim_info = generate_trim_info(video_files, input_dir)
    if not trim_info:
        print(f"  No valid videos to merge after analyzing overlaps")
        return False
    
    # Create filter complex for trimming and concatenating
    filter_complex = ""
    concat_parts = []
    
    # Determine if we can use GPU acceleration
    gpu_available = False
    gpu_codec = None
    
    if use_gpu:
        # Check for available hardware acceleration methods
        try:
            gpu_check = subprocess.run(
                ["ffmpeg", "-hide_banner", "-hwaccels"],
                capture_output=True, text=True, check=False
            )
            
            # Check for different hardware acceleration methods
            hw_accels = gpu_check.stdout.lower()
            
            if "cuda" in hw_accels:
                gpu_available = True
                gpu_codec = "h264_nvenc"
                print("  NVIDIA GPU acceleration available (NVENC)")
            elif "qsv" in hw_accels and os.name == 'nt':  # Windows-specific
                gpu_available = True
                gpu_codec = "h264_qsv"
                print("  Intel QuickSync acceleration available")
            elif "vaapi" in hw_accels:
                gpu_available = True
                gpu_codec = "h264_vaapi"
                print("  VAAPI acceleration available")
            elif "videotoolbox" in hw_accels:  # macOS
                gpu_available = True
                gpu_codec = "h264_videotoolbox"
                print("  VideoToolbox acceleration available (macOS)")
            else:
                print("  No supported GPU acceleration found, using CPU")
        except Exception as e:
            print(f"  Error checking GPU availability: {str(e)}")
            gpu_available = False
    
    # Get input video codec information for the first file to match quality
    probe_cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,bit_rate,width,height",
        "-of", "json",
        trim_info[0]["file_path"]
    ]
    
    try:
        probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
        codec_info = json.loads(probe_result.stdout)
        video_codec = codec_info['streams'][0].get('codec_name', 'h264')
        
        # Try to get bitrate, default to high quality if not available
        try:
            bitrate = int(codec_info['streams'][0].get('bit_rate', '8000000'))
        except (ValueError, TypeError):
            bitrate = 8000000  # 8 Mbps as default
        
        print(f"  Source video codec: {video_codec}, bitrate: {bitrate/1000000:.2f} Mbps")
    except Exception as e:
        print(f"  Error getting codec info: {str(e)}")
        video_codec = 'h264'
        bitrate = 8000000
    
    # Build the trim and concat filter complex
    for i, info in enumerate(trim_info):
        # Add trim filter
        filter_complex += f"[{i}:v]trim=start={info['start_time']}:duration={info['duration']},setpts=PTS-STARTPTS[v{i}];"
        filter_complex += f"[{i}:a]atrim=start={info['start_time']}:duration={info['duration']},asetpts=PTS-STARTPTS[a{i}];"
        
        # Add to concat list
        concat_parts.append(f"[v{i}][a{i}]")
    
    # Add concat filter
    filter_complex += f"{''.join(concat_parts)}concat=n={len(trim_info)}:v=1:a=1[outv][outa]"
    
    # Build ffmpeg command
    cmd = ["ffmpeg"]
    
    # Add inputs
    for info in trim_info:
        cmd.extend(["-i", info["file_path"]])
    
    # Add filter complex
    cmd.extend(["-filter_complex", filter_complex])
    
    # Add mapping
    cmd.extend(["-map", "[outv]", "-map", "[outa]"])
    
    # Set thread count if specified
    if cpu_threads > 0:
        cmd.extend(["-threads", str(cpu_threads)])
    
    # Add codec options based on GPU availability
    if gpu_available and gpu_codec:
        if "nvenc" in gpu_codec:
            # NVIDIA GPU settings with high quality preset
            cmd.extend([
                "-c:v", gpu_codec,
                "-preset", "p7",     # p7 is equivalent to "slow" - high quality
                "-tune", "hq",       # High quality tuning
                "-rc:v", "vbr",      # Variable bitrate mode
                "-cq:v", "19",       # Lower value means better quality
                "-b:v", str(bitrate), 
                "-maxrate:v", str(int(bitrate * 1.5)),
                "-bufsize:v", str(int(bitrate * 2))
            ])
        elif "qsv" in gpu_codec:
            # Intel QuickSync settings
            cmd.extend([
                "-c:v", gpu_codec,
                "-preset", "veryslow",
                "-global_quality", "19",  # Lower is better quality
                "-b:v", str(bitrate)
            ])
        elif "vaapi" in gpu_codec:
            # VAAPI (Intel/AMD) settings
            cmd.extend([
                "-c:v", gpu_codec,
                "-qp", "19",
                "-b:v", str(bitrate)
            ])
        elif "videotoolbox" in gpu_codec:
            # macOS VideoToolbox
            cmd.extend([
                "-c:v", gpu_codec,
                "-b:v", str(bitrate),
                "-allow_sw", "1"     # Allow software fallback
            ])
    else:
        # CPU encoding with quality focus - try to match source codec if possible
        if video_codec in ['h264', 'libx264']:
            cmd.extend([
                "-c:v", "libx264",
                "-preset", "medium",  # Balance between speed and quality
                "-crf", "18",         # Lower crf means better quality (18-23 is visually lossless)
                "-b:v", str(bitrate)
            ])
        else:
            # Default to high quality H.264
            cmd.extend([
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "18",
                "-b:v", str(bitrate)
            ])
    
    # Audio codec with high quality
    cmd.extend([
        "-c:a", "aac",
        "-b:a", "192k",
        "-y",  # Overwrite output
        output_file
    ])
    
    # Print command for debugging
    cmd_str = " ".join(cmd)
    print(f"  FFmpeg command: {cmd_str[:100]}...")
    
    # Execute command
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  Error merging videos: {result.stderr}")
            return False
        return True
    except Exception as e:
        print(f"  Error executing ffmpeg: {str(e)}")
        return False

def process_dashcam_videos(input_dir, output_dir, max_gap=120.0, use_gpu=True, cpu_threads=0):
    """Process dashcam videos from the input directory."""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Get all MP4 files
    all_files = [f for f in os.listdir(input_dir) if f.lower().endswith('.mp4')]
    if not all_files:
        print(f"No MP4 files found in {input_dir}")
        return
    
    print(f"Found {len(all_files)} MP4 files")
    
    # Parse filenames and organize by camera type
    videos_by_camera = defaultdict(list)
    
    print("Analyzing files...", end="", flush=True)
    for i, filename in enumerate(all_files):
        # Show progress indicator
        if i % 10 == 0:
            print(f"\rAnalyzing files... {i}/{len(all_files)}", end="", flush=True)
        
        video_info = parse_filename(filename)
        if video_info:
            videos_by_camera[video_info["camera_type"]].append(video_info)
    
    print(f"\rAnalyzing files... {len(all_files)}/{len(all_files)} - Done!        ")
    
    if not videos_by_camera:
        print("No valid dashcam videos found. Please check if the files follow the supported naming formats.")
        return
    
    # Print summary of found videos
    print("\nFound videos by camera type:")
    for camera_type, videos in videos_by_camera.items():
        print(f"  {camera_type}: {len(videos)} videos")
    
    # Process each camera type
    for camera_type, videos in videos_by_camera.items():
        print(f"\nProcessing {camera_type} camera videos...")
        
        # Group videos by continuity
        print("  Analyzing time continuity...")
        video_groups = group_videos_by_continuity(videos, max_gap, input_dir)
        print(f"  Found {len(video_groups)} continuous segments")
        
        for i, group in enumerate(video_groups):
            # Sort videos in each group by timestamp
            sorted_group = sorted(group, key=lambda x: x["timestamp"])
            
            # Get list of video files
            video_files = [os.path.join(input_dir, video["filename"]) for video in sorted_group]
            
            # Define output filename
            start_time = sorted_group[0]["timestamp"]
            end_time = sorted_group[-1]["timestamp"]
            
            start_str = start_time.strftime("%Y%m%d_%H%M%S")
            end_str = end_time.strftime("%Y%m%d_%H%M%S")
            
            output_file = os.path.join(
                output_dir, 
                f"{camera_type}_{start_str}_to_{end_str}.mp4"
            )
            
            print(f"  Merging group {i+1}/{len(video_groups)} with {len(video_files)} videos")
            print(f"  Output: {output_file}")
            
            # Merge videos with trimming
            print("  Starting FFmpeg merge with overlap handling...")
            success = merge_videos_with_trim(video_files, output_file, input_dir, use_gpu=use_gpu, cpu_threads=cpu_threads)
            if success:
                print(f"  Successfully merged videos to {output_file}")
            else:
                print(f"  Failed to merge videos to {output_file}")
    
    print("\nDashcam video consolidation complete!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dashcam Video Consolidation Tool")
    parser.add_argument("input_dir", help="Directory containing dashcam footage")
    parser.add_argument("output_dir", help="Directory to save consolidated videos")
    parser.add_argument("--max-gap", type=float, default=120.0,
                       help="Maximum gap in seconds between videos to consider them continuous (default: 120.0)")
    parser.add_argument("--no-gpu", action="store_true",
                       help="Disable GPU acceleration for video processing")
    parser.add_argument("--cpu-threads", type=int, default=0,
                       help="Number of CPU threads to use for encoding (0=auto)")
    
    args = parser.parse_args()
    
    process_dashcam_videos(args.input_dir, args.output_dir, args.max_gap, not args.no_gpu, args.cpu_threads)
