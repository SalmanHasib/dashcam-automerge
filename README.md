# BlackVue Dashcam Video Consolidation Tool

A tool for consolidating dashcam footage into continuous video segments, automatically handling front and rear camera footage separately.

## Features

- Automatically identifies front and rear camera footage from dashcam files
- Combines video files into continuous segments
- Intelligently trims overlapping footage to prevent duplication
- Creates separate video files for non-continuous time periods
- Organizes output files with clear time-based naming convention
- Supports multiple dashcam file naming formats
- GPU acceleration support for faster processing (NVIDIA, Intel QSV, VAAPI, VideoToolbox)
- Quality preservation to match source video

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
python main.py <input_directory> <output_directory> [options]
```

Arguments:
- `input_directory`: Directory containing the dashcam footage
- `output_directory`: Directory where consolidated videos will be saved

Options:
- `--max-gap SECONDS`: Maximum time gap in seconds between clips to consider them continuous (default: 120.0)
- `--no-gpu`: Disable GPU acceleration for video processing
- `--cpu-threads THREADS`: Number of CPU threads to use for encoding (0=auto)

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

## Example

```
python main.py ~/Downloads/BlackVue_Footage ~/Videos/Dashcam_Consolidated
```

## Testing with Generated Files

The repository includes a script (`create_test_files.py`) that can generate test files to help you test the consolidation tool without real dashcam footage:

```
python create_test_files.py test_files --front 10 --rear 10
```

This will create a directory called `test_files` with 10 front camera videos and 10 rear camera videos. By default, a time gap is inserted in the middle of the footage to test the continuity detection. Use the `--no-gap` flag to create continuous footage.

After generating the test files, you can run the consolidation tool on them:

```
python main.py test_files output_files
```

## Output Format

The tool will create consolidated videos in the output directory with the following naming convention:

```
<camera_type>_<start_timestamp>_to_<end_timestamp>.mp4
```

Where:
- `camera_type` is either "front" or "rear"
- `start_timestamp` is the timestamp of the first video in the sequence
- `end_timestamp` is the timestamp of the last video in the sequence

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
- `Car_F_20230615_172045.mp4`

## How Overlap Handling Works

Dashcam footage often contains overlapping segments. This tool handles these overlaps by:

1. Sorting videos by their timestamps
2. Analyzing the start and end times of each video
3. Trimming the beginning of each video that overlaps with the end of the previous video
4. Joining the trimmed videos to create a single continuous video without repetition

This ensures the final video shows each moment only once, creating a seamless viewing experience. 