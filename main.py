#!/usr/bin/env python3

import os
import re
import subprocess
import argparse
import datetime
import json
import sys
from collections import defaultdict
import shutil

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

def group_videos_by_continuity(videos, max_gap=30.0, input_dir=None):
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
    Uses a hierarchical batch approach to reduce memory usage by processing 
    in batches of 10 files at a time.
    
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
    
    # Determine if we can use GPU acceleration
    gpu_available = False
    gpu_codec = None
    hw_device = None
    
    if use_gpu:
        # Check for available hardware acceleration methods
        try:
            # Try to detect GPU capabilities
            gpu_check = subprocess.run(
                ["ffmpeg", "-hide_banner", "-hwaccels"],
                capture_output=True, text=True, check=False
            )
            hw_accels = gpu_check.stdout.lower()
            
            # Check available encoders
            encoders_check = subprocess.run(
                ["ffmpeg", "-hide_banner", "-encoders"],
                capture_output=True, text=True, check=False
            )
            encoders = encoders_check.stdout.lower()
            
            print("  Detected hardware acceleration methods:", hw_accels.strip())
            
            # NVIDIA GPU
            if "cuda" in hw_accels and "h264_nvenc" in encoders:
                gpu_available = True
                gpu_codec = "h264_nvenc"
                print("  NVIDIA GPU acceleration available (NVENC)")
            # Intel QuickSync
            elif "qsv" in hw_accels and "h264_qsv" in encoders:
                gpu_available = True
                gpu_codec = "h264_qsv"
                hw_device = "-init_hw_device qsv=qsv:hw -filter_hw_device qsv"
                print("  Intel QuickSync acceleration available")
            # VAAPI (Linux)
            elif "vaapi" in hw_accels and "h264_vaapi" in encoders:
                gpu_available = True
                gpu_codec = "h264_vaapi"
                hw_device = "-vaapi_device /dev/dri/renderD128"
                print("  VAAPI acceleration available")
            # VideoToolbox (macOS)
            elif "videotoolbox" in hw_accels and "h264_videotoolbox" in encoders:
                gpu_available = True
                gpu_codec = "h264_videotoolbox"
                print("  VideoToolbox acceleration available (macOS)")
            else:
                print("  No supported GPU acceleration found, using CPU")
        except Exception as e:
            print(f"  Error checking GPU availability: {str(e)}")
            gpu_available = False
    
    # Get input video codec information for quality matching
    try:
        probe_cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_name,bit_rate,width,height",
            "-of", "json",
            trim_info[0]["file_path"]
        ]
        
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
    
    # Calculate total duration for progress reporting
    total_duration = 0
    for info in trim_info:
        total_duration += info['duration']
    print(f"  Total video duration: {total_duration:.2f} seconds")
    
    # Create temporary directory for intermediate files
    # Use os.path.dirname to ensure we're getting just the directory
    output_dir = os.path.dirname(os.path.abspath(output_file))
    # Use basename to get just the filename without the path
    output_basename = os.path.basename(output_file)
    # Create a unique temp dir name
    temp_dir = os.path.join(output_dir, f"temp_{int(datetime.datetime.now().timestamp())}")
    
    # Create the temp directory if it doesn't exist
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    
    try:
        # First, create trimmed segments of each video
        print("  Trimming individual segments...")
        trimmed_segments = []
        
        for i, info in enumerate(trim_info):
            # Create a temporary file for each trimmed segment with absolute path
            temp_file = os.path.join(temp_dir, f"segment_{i}.mp4")
            trimmed_segments.append(temp_file)
            
            # Build ffmpeg command for trimming
            trim_cmd = ["ffmpeg", "-hide_banner", "-y", "-i", info["file_path"]]
            
            # Add hardware acceleration if available
            if gpu_available and hw_device:
                trim_cmd.extend(hw_device.split())
            
            # Add trim options
            trim_cmd.extend([
                "-ss", str(info["start_time"]), 
                "-t", str(info["duration"]),
                "-c:v"
            ])
            
            # Add codec options based on GPU availability
            if gpu_available and gpu_codec:
                if "nvenc" in gpu_codec:
                    trim_cmd.extend([
                        gpu_codec,
                        "-preset", "p7",     # p7 is equivalent to "slow" - high quality
                        "-rc:v", "vbr",      # Variable bitrate mode
                        "-cq:v", "18",       # Lower value means better quality
                        "-b:v", str(bitrate)
                    ])
                elif "qsv" in gpu_codec:
                    trim_cmd.extend([
                        gpu_codec,
                        "-preset", "veryslow",
                        "-global_quality", "19",
                        "-b:v", str(bitrate)
                    ])
                elif "vaapi" in gpu_codec:
                    trim_cmd.extend([
                        gpu_codec,
                        "-qp", "19",
                        "-b:v", str(bitrate)
                    ])
                elif "videotoolbox" in gpu_codec:
                    trim_cmd.extend([
                        gpu_codec,
                        "-b:v", str(bitrate),
                        "-allow_sw", "1"
                    ])
            else:
                # CPU encoding
                trim_cmd.extend([
                    "libx264",
                    "-preset", "medium",
                    "-crf", "18",
                    "-b:v", str(bitrate)
                ])
            
            # Add audio options and output file
            trim_cmd.extend([
                "-c:a", "aac",
                "-b:a", "192k",
                temp_file
            ])
            
            # Run the trim command
            print(f"  Trimming segment {i+1}/{len(trim_info)}: {info['duration']:.2f} seconds")
            result = subprocess.run(trim_cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"  Error trimming segment {i+1}: {result.stderr}")
                raise Exception(f"FFmpeg error: {result.stderr}")
        
        # Second phase: hierarchical concatenation in batches of 10
        print("  Starting hierarchical concatenation in batches...")
        
        # Function to concatenate a batch of files
        def concatenate_batch(input_files, output_file, batch_num, level=1):
            print(f"  Concatenating batch {batch_num} (level {level}) with {len(input_files)} clips...")
            
            # Create a concat file with absolute paths
            concat_file = os.path.join(temp_dir, f"concat_batch_{level}_{batch_num}.txt")
            with open(concat_file, 'w') as f:
                for file_path in input_files:
                    # Make sure to use the absolute path and escape backslashes for Windows
                    escaped_path = file_path.replace('\\', '\\\\')
                    f.write(f"file '{escaped_path}'\n")
                # Add final newline to ensure EOF newline
                f.write("\n")
            
            # Build the concat command
            concat_cmd = [
                "ffmpeg", 
                "-hide_banner", 
                "-y", 
                "-safe", "0", 
                "-f", "concat", 
                "-i", concat_file
            ]
            
            # Add progress monitoring
            concat_cmd.extend(["-progress", "pipe:1", "-stats"])
            
            # Set thread count if specified
            if cpu_threads > 0:
                concat_cmd.extend(["-threads", str(cpu_threads)])
            
            # Add hardware acceleration if available
            if gpu_available and hw_device:
                concat_cmd.extend(hw_device.split())
            
            # Configure video and audio codec options
            if gpu_available and gpu_codec:
                concat_cmd.extend(["-c:v", gpu_codec])
                
                if "nvenc" in gpu_codec:
                    concat_cmd.extend([
                        "-preset", "p4",      # p4 is medium quality/speed balance
                        "-rc:v", "vbr",       # Variable bitrate mode
                        "-cq:v", "19",        # Quality level (18-20 is good for batch processing)
                        "-b:v", str(bitrate)
                    ])
                elif "qsv" in gpu_codec:
                    concat_cmd.extend([
                        "-preset", "medium",
                        "-global_quality", "20",
                        "-b:v", str(bitrate)
                    ])
                elif "vaapi" in gpu_codec:
                    concat_cmd.extend([
                        "-qp", "21",
                        "-b:v", str(bitrate)
                    ])
                elif "videotoolbox" in gpu_codec:
                    concat_cmd.extend([
                        "-b:v", str(bitrate),
                        "-allow_sw", "1"
                    ])
            else:
                # CPU encoding with moderate settings for batch processing
                concat_cmd.extend([
                    "-c:v", "libx264",
                    "-preset", "medium",
                    "-crf", "20",
                ])
            
            # Add audio codec and output file
            concat_cmd.extend([
                "-c:a", "copy",
                output_file
            ])
            
            # Print command for debugging
            cmd_str = " ".join(concat_cmd)
            print(f"  FFmpeg batch {batch_num} command: {cmd_str[:100]}...")
            
            # Execute command
            result = subprocess.run(concat_cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"  Error concatenating batch {batch_num}: {result.stderr}")
                # If GPU encoding failed, retry with CPU
                if gpu_available and "Error while opening encoder" in result.stderr:
                    print(f"  GPU encoding failed, falling back to CPU for this batch...")
                    # Build a new command without GPU acceleration
                    cpu_concat_cmd = [
                        "ffmpeg", "-hide_banner", "-y", "-safe", "0", 
                        "-f", "concat", "-i", concat_file
                    ]
                    
                    if cpu_threads > 0:
                        cpu_concat_cmd.extend(["-threads", str(cpu_threads)])
                    
                    cpu_concat_cmd.extend([
                        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                        "-c:a", "copy", output_file
                    ])
                    
                    print(f"  Retrying batch {batch_num} with CPU: {' '.join(cpu_concat_cmd)[:100]}...")
                    retry_result = subprocess.run(cpu_concat_cmd, capture_output=True, text=True)
                    
                    if retry_result.returncode != 0:
                        print(f"  CPU fallback also failed: {retry_result.stderr}")
                        raise Exception(f"FFmpeg batch error: Both GPU and CPU encoding failed")
                    return output_file
                else:
                    raise Exception(f"FFmpeg batch error: {result.stderr}")
            
            return output_file
        
        # Process the segments hierarchically
        current_level_files = trimmed_segments.copy()
        level = 1
        
        while len(current_level_files) > 1:
            print(f"  Level {level} concatenation: processing {len(current_level_files)} files")
            next_level_files = []
            
            # Process in batches of 10
            for i in range(0, len(current_level_files), 10):
                batch = current_level_files[i:i+10]
                if len(batch) == 1 and len(current_level_files) > 10:
                    # If only one file in batch and not the final level, just pass it through
                    next_level_files.append(batch[0])
                    continue
                
                # Concatenate this batch
                batch_output = os.path.join(temp_dir, f"level_{level}_batch_{i//10}.mp4")
                concatenated_file = concatenate_batch(batch, batch_output, i//10, level)
                next_level_files.append(concatenated_file)
            
            # Update for next level
            current_level_files = next_level_files
            level += 1
        
        # Final step - move/rename the last file to the output
        if len(current_level_files) == 1:
            # Either copy or rename based on whether they're on same filesystem
            try:
                os.replace(current_level_files[0], output_file)
            except OSError:
                # If replace fails (e.g., different filesystems), copy and delete
                shutil.copy2(current_level_files[0], output_file)
                os.remove(current_level_files[0])
            
            print(f"  Successfully merged {len(trimmed_segments)} segments into {output_file}")
            return True
        else:
            print(f"  Error: No files remaining after hierarchical merge")
            return False
            
    except Exception as e:
        print(f"  Error processing videos: {str(e)}")
        return False
    
    finally:
        # Clean up temporary files and directory
        try:
            if 'temp_dir' in locals() and os.path.exists(temp_dir):
                for file in os.listdir(temp_dir):
                    os.remove(os.path.join(temp_dir, file))
                os.rmdir(temp_dir)
        except Exception as e:
            print(f"  Warning: Error cleaning up temporary files: {str(e)}")
            # Continue even if cleanup fails

def process_dashcam_videos(input_dir, output_dir, max_gap=30.0, use_gpu=True, cpu_threads=0, camera_type=None, summary_only=False):
    """
    Process dashcam videos from the input directory.
    
    Args:
        input_dir: Directory containing dashcam footage
        output_dir: Directory to save consolidated videos
        max_gap: Maximum gap in seconds between videos to consider them continuous
        use_gpu: Whether to attempt to use GPU acceleration
        cpu_threads: Number of CPU threads to use (0=auto)
        camera_type: Optional filter to only process specific camera type (front, rear)
        summary_only: If True, only show summary information without processing files
    """
    if not summary_only and not os.path.exists(output_dir):
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
    for cam_type, videos in videos_by_camera.items():
        print(f"  {cam_type}: {len(videos)} videos")
    
    # Filter by camera type if specified
    if camera_type:
        if camera_type not in videos_by_camera:
            print(f"No videos found for camera type: {camera_type}")
            return
        process_cameras = [camera_type]
    else:
        process_cameras = list(videos_by_camera.keys())
    
    # For each camera type, analyze continuity
    for cam_type in process_cameras:
        videos = videos_by_camera[cam_type]
        print(f"\nAnalyzing {cam_type} camera videos...")
        
        # Group videos by continuity
        print("  Analyzing time continuity...")
        video_groups = group_videos_by_continuity(videos, max_gap, input_dir)
        print(f"  Found {len(video_groups)} continuous segments")
        
        # Print summary of each group
        total_duration = 0
        for i, group in enumerate(video_groups):
            # Sort videos in each group by timestamp
            sorted_group = sorted(group, key=lambda x: x["timestamp"])
            
            # Calculate group duration
            start_time = sorted_group[0]["timestamp"]
            end_time = sorted_group[-1]["timestamp"]
            
            # Try to get actual duration by adding up video durations with overlaps removed
            group_duration = 0
            for j, video in enumerate(sorted_group):
                video_path = os.path.join(input_dir, video["filename"])
                duration = get_video_duration(video_path)
                
                if duration is None:
                    continue
                
                # For first video, include full duration
                if j == 0:
                    group_duration += duration
                    continue
                
                # For subsequent videos, calculate overlap with previous
                prev_video = sorted_group[j-1]
                prev_path = os.path.join(input_dir, prev_video["filename"])
                prev_duration = get_video_duration(prev_path)
                
                if prev_duration is None:
                    group_duration += duration
                    continue
                
                # Calculate overlap
                prev_end_time = prev_video["timestamp"] + datetime.timedelta(seconds=prev_duration)
                current_start_time = video["timestamp"]
                overlap_seconds = max(0, (prev_end_time - current_start_time).total_seconds())
                
                # Add non-overlapping portion to duration
                non_overlap_duration = max(0, duration - overlap_seconds)
                group_duration += non_overlap_duration
            
            total_duration += group_duration
            
            # Format group info
            start_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
            end_str = end_time.strftime("%Y-%m-%d %H:%M:%S")
            duration_str = f"{int(group_duration // 60)}:{int(group_duration % 60):02d}"
            
            print(f"  Group {i+1}: {len(sorted_group)} videos, {start_str} to {end_str}, Duration: {duration_str}")
        
        # Print total duration
        hours = int(total_duration // 3600)
        minutes = int((total_duration % 3600) // 60)
        seconds = int(total_duration % 60)
        
        if hours > 0:
            duration_str = f"{hours}h {minutes}m {seconds}s"
        else:
            duration_str = f"{minutes}m {seconds}s"
        
        print(f"  Total {cam_type} camera footage: {duration_str}")
    
    # If summary only, exit here
    if summary_only:
        print("\nSummary complete. No files were processed.")
        return
    
    # Process each camera type
    for cam_type in process_cameras:
        videos = videos_by_camera[cam_type]
        print(f"\nProcessing {cam_type} camera videos...")
        
        # Group videos by continuity
        video_groups = group_videos_by_continuity(videos, max_gap, input_dir)
        
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
                f"{cam_type}_{start_str}_to_{end_str}.mp4"
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
    
    if not summary_only:
        print("\nDashcam video consolidation complete!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dashcam Video Consolidation Tool")
    parser.add_argument("input_dir", help="Directory containing dashcam footage")
    parser.add_argument("output_dir", nargs="?", help="Directory to save consolidated videos")
    parser.add_argument("--max-gap", type=float, default=30.0,
                       help="Maximum gap in seconds between videos to consider them continuous (default: 30.0)")
    parser.add_argument("--no-gpu", action="store_true",
                       help="Disable GPU acceleration for video processing")
    parser.add_argument("--cpu-threads", type=int, default=0,
                       help="Number of CPU threads to use for encoding (0=auto)")
    parser.add_argument("--camera", choices=["front", "rear"], 
                       help="Process only specified camera type (front or rear)")
    parser.add_argument("--summary-only", action="store_true",
                       help="Only show a summary of videos, don't process them")
    
    args = parser.parse_args()
    
    # Check if output_dir is required
    if not args.summary_only and not args.output_dir:
        parser.error("output_dir is required unless --summary-only is specified")
    
    # Use input_dir as output_dir for summary-only mode if not specified
    output_dir = args.output_dir if args.output_dir else args.input_dir
    
    # Process videos
    process_dashcam_videos(
        args.input_dir,
        output_dir,
        args.max_gap,
        not args.no_gpu,
        args.cpu_threads,
        args.camera,
        args.summary_only
    )
