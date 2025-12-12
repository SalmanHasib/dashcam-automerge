# BlackVue Footage Consolidation Tool

A tool for consolidating dashcam footage into continuous video segments, and automatically handling trimming overlaps for front and rear camera footage separately.

## Features

- Automatically identifies front and rear camera footage from dashcam files
- Combines video files into continuous segments
- Trims overlapping footage to prevent duplication
- Creates separate videos for non-continuous time periods
- Organizes output files with clear time-based naming convention
- Supports multiple dashcam file naming formats
- GPU acceleration support for faster processing (NVIDIA, Intel QSV, VAAPI, VideoToolbox)
- Quality preservation to match source video
- Real-time progress tracking during video processing
- Summary mode to analyze footage without processing

## Requirements

- Python 3.6 or higher
- ffmpeg (must be installed and available in your system PATH)

## Installation

1. Ensure you have Python 3 installed
2. Install ffmpeg:
   ```
   # Ubuntu/Debian
   sudo apt-get install ffmpeg
   
   # macOS with Homebrew
   brew install ffmpeg
   
   # Windows
   # Download from https://ffmpeg.org/download.html
   ```
3. Clone or download this repository

## Usage

```
python main.py <input_directory> [output_directory] [options]
```

Arguments:
- `input_directory`: Directory containing the dashcam footage
- `output_directory`: Directory to save consolidated videos (not required with --summary-only)

Options:
- `--max-gap SECONDS`: Maximum time gap in seconds between clips to consider them continuous (default: 30.0)
- `--no-gpu`: Disable GPU acceleration for video processing
- `--cpu-threads THREADS`: Number of CPU threads to use for encoding (0=auto)
- `--camera {front,rear}`: Process only the specified camera type if you have footage from a dual camera system
- `--summary-only`: Only analyze and show summary without processing any files

## Summary Mode

The tool can analyze your dashcam footage and provide a detailed summary without processing any files. This is useful to:
- Check what footage you have
- See how it will be grouped into continuous segments
- Get total duration information
- Plan which segments you want to process

To use summary mode:
```
python main.py ~/Dashcam/Videos --summary-only
```

Example output:
```
Found 120 MP4 files
Analyzing files... 120/120 - Done!        

Found videos by camera type:
  front: 60 videos
  rear: 60 videos

Analyzing front camera videos...
  Analyzing time continuity...
  Found 3 continuous segments
  Group 1: 15 videos, 2023-06-15 09:10:23 to 2023-06-15 09:40:56, Duration: 30:33
  Group 2: 25 videos, 2023-06-15 12:15:45 to 2023-06-15 13:05:12, Duration: 49:27
  Group 3: 20 videos, 2023-06-15 17:30:22 to 2023-06-15 18:10:45, Duration: 40:23
  Total front camera footage: 2h 0m 23s

Analyzing rear camera videos...
  Analyzing time continuity...
  Found 3 continuous segments
  Group 1: 15 videos, 2023-06-15 09:10:23 to 2023-06-15 09:40:56, Duration: 30:33
  Group 2: 25 videos, 2023-06-15 12:15:45 to 2023-06-15 13:05:12, Duration: 49:27
  Group 3: 20 videos, 2023-06-15 17:30:22 to 2023-06-15 18:10:45, Duration: 40:23
  Total rear camera footage: 2h 0m 23s

Summary complete. No files were processed.
```

You can combine summary mode with other options:
```
python main.py ~/Dashcam/Videos --summary-only --camera front --max-gap 60
```

## Progress Tracking

The tool displays a real-time progress bar during the FFmpeg processing:

```
Processing: [##############################                    ] 60%
```

This helps you monitor the conversion process, especially for large files.

## GPU Acceleration

The tool automatically detects and uses available GPU acceleration to speed up the video merging process:

- **NVIDIA GPUs**: Uses NVENC hardware encoder for fast processing
- **Intel CPUs with QuickSync**: Uses QSV acceleration (Windows)
- **Linux systems with VAAPI**: Uses VA-API acceleration
- **Mac computers**: Uses VideoToolbox acceleration

To disable GPU acceleration (e.g., if you encounter issues), use the `--no-gpu` flag:

```
python main.py ~/Downloads/BlackVue_Footage ~/Videos/Dashcam_Consolidated --no-gpu
```

## Quality Preservation

The tool analyzes your source video files and attempts to match their quality settings:

- Preserves original video bitrate when possible
- Uses visually lossless encoding parameters (CRF 18 for CPU encoding)
- Maintains high-quality audio (192kbps AAC)

This ensures your combined videos maintain similar quality to the original footage.

## Examples

Basic consolidation:
```
python main.py ~/Dashcam/Videos ~/Consolidated
```

Process only front camera footage:
```
python main.py ~/Dashcam/Videos ~/Consolidated --camera front
```

Process with a larger time gap tolerance:
```
python main.py ~/Dashcam/Videos ~/Consolidated --max-gap 60
```

## Supported Dashcam Formats

This tool is designed to work with various dashcam footage formats:

### Main Format
```
[YYYYMMDD]_[HHMMSS]_[type][direction].mp4
```

Where:
- `YYYYMMDD` is the date in year/month/day format
- `HHMMSS` is the time in hours/minutes/seconds format
- `type` is the recording type (e.g., 'N' for normal, 'E' for event, 'M' for manual)
- `direction` is 'F' for front camera or 'R' for rear camera

Example: `20230615_172045_NF.mp4`

### BlackVue Format (Legacy Support)
```
[prefix]_[YYYYMMDD]_[HHMMSS]_[direction].mp4
```

Where:
- `[prefix]` is typically the model number or other identifier
- `YYYYMMDD` is the date in year/month/day format
- `HHMMSS` is the time in hours/minutes/seconds format
- `[direction]` is "F" for front camera or "R" for rear camera

Example: `BlackVue_20230615_172045_F.mp4`

### Generic Format

The tool also supports other dashcam formats as long as:

1. The filename contains a date in YYYYMMDD format and time in HHMMSS format
2. The filename contains an indicator of front/rear camera (e.g., "front", "rear", "F", "R", etc.)

Examples:
- `DashCam_Front_20230615_172045.mp4`
- `RoadCam_20230615_172045_rear.mp4`

## How Overlap Handling Works

Dashcam footage often contains overlapping segments. This tool handles these overlaps by:

1. Sorting videos by their timestamps
2. Analyzing the start and end times of each video
3. Trimming the beginning of each video that overlaps with the end of the previous video
4. Joining the trimmed videos to create a single continuous video without repetition

This ensures the final video shows each moment only once, creating a seamless viewing experience. 

## Known Issues
- Audio artifacts at some merge points
- Missing footage for some clips with overlapping time -> this is inconsistent, still trying to figure out what causes it.
