#!/usr/bin/env python3

import os
import sys
import tempfile
import unittest
import datetime
import subprocess
import json
from unittest.mock import patch, MagicMock
from main import parse_filename, group_videos_by_continuity, generate_trim_info, process_dashcam_videos

class TestDashcamVideoConsolidation(unittest.TestCase):
    def test_parse_filename_formats(self):
        """Test parsing different dashcam filename formats."""
        # Main format
        filename = "20230615_172045_NF.mp4"
        result = parse_filename(filename)
        self.assertIsNotNone(result)
        self.assertEqual(result["camera_type"], "front")
        self.assertEqual(result["filename"], filename)
        self.assertEqual(result["timestamp"], datetime.datetime(2023, 6, 15, 17, 20, 45))
        
        # Rear camera in main format
        filename = "20230615_172045_ER.mp4"
        result = parse_filename(filename)
        self.assertIsNotNone(result)
        self.assertEqual(result["camera_type"], "rear")
        
        # Different event type in main format
        filename = "20230615_172045_MF.mp4"
        result = parse_filename(filename)
        self.assertIsNotNone(result)
        self.assertEqual(result["camera_type"], "front")
        
        # BlackVue format (legacy support)
        filename = "BlackVue_20230615_172045_F.mp4"
        result = parse_filename(filename)
        self.assertIsNotNone(result)
        self.assertEqual(result["camera_type"], "front")
        
        # Different prefix in BlackVue format
        filename = "DR900X_20230615_172045_R.mp4"
        result = parse_filename(filename)
        self.assertIsNotNone(result)
        self.assertEqual(result["camera_type"], "rear")
        
        # Invalid format should return None
        filename = "invalid_filename.mp4"
        result = parse_filename(filename)
        self.assertIsNone(result)
    
    def test_group_videos_by_continuity(self):
        """Test grouping videos by continuity."""
        # Create dummy video info for testing
        videos = [
            {
                "timestamp": datetime.datetime(2023, 6, 15, 17, 0, 0),
                "filename": "20230615_170000_NF.mp4",
                "camera_type": "front"
            },
            {
                "timestamp": datetime.datetime(2023, 6, 15, 17, 1, 0),
                "filename": "20230615_170100_EF.mp4",
                "camera_type": "front"
            },
            # Gap of 10 minutes
            {
                "timestamp": datetime.datetime(2023, 6, 15, 17, 11, 0),
                "filename": "20230615_171100_NF.mp4",
                "camera_type": "front"
            },
            {
                "timestamp": datetime.datetime(2023, 6, 15, 17, 12, 0),
                "filename": "20230615_171200_MF.mp4",
                "camera_type": "front"
            }
        ]
        
        # Create temp directory with dummy files for testing
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create empty files
            for video in videos:
                open(os.path.join(tmp_dir, video["filename"]), 'w').close()
            
            # Since we can't test actual duration calculation without ffmpeg,
            # we'll mock the functionality by ensuring that our comparison
            # logic works as expected
            
            # Test with very large max_gap (all files in one group)
            with patch('main.get_video_duration', return_value=60.0):
                groups = group_videos_by_continuity(videos, max_gap=1000, input_dir=tmp_dir)
                self.assertEqual(len(groups), 1)
                self.assertEqual(len(groups[0]), 4)
            
            # Test with smaller max_gap that should split the files
            with patch('main.get_video_duration', return_value=60.0):
                groups = group_videos_by_continuity(videos, max_gap=5, input_dir=tmp_dir)
                self.assertEqual(len(groups), 2)
                self.assertEqual(len(groups[0]), 2)
                self.assertEqual(len(groups[1]), 2)
    
    def test_generate_trim_info(self):
        """Test generation of trim information for overlapping videos."""
        # Create sample video files
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create test files
            files = [
                os.path.join(tmp_dir, "20230615_170000_NF.mp4"),
                os.path.join(tmp_dir, "20230615_170050_NF.mp4")  # Starts 50 seconds after first file
            ]
            
            for file in files:
                open(file, 'w').close()
            
            # Mock parse_filename and get_video_duration
            with patch('main.parse_filename') as mock_parse:
                with patch('main.get_video_duration') as mock_duration:
                    # Setup parse_filename mock to return timestamps
                    mock_parse.side_effect = [
                        {
                            "timestamp": datetime.datetime(2023, 6, 15, 17, 0, 0),
                            "camera_type": "front",
                            "filename": os.path.basename(files[0])
                        },
                        {
                            "timestamp": datetime.datetime(2023, 6, 15, 17, 0, 50),
                            "camera_type": "front",
                            "filename": os.path.basename(files[1])
                        }
                    ]
                    
                    # Setup duration mock to return 60 seconds for each file
                    mock_duration.return_value = 60.0
                    
                    # Test trim info generation
                    trim_info = generate_trim_info(files, tmp_dir)
                    
                    # First file should start at 0, second file should start at overlap point
                    self.assertEqual(len(trim_info), 2)
                    self.assertEqual(trim_info[0]["start_time"], 0)
                    self.assertEqual(trim_info[0]["duration"], 60.0)
                    
                    # Second file should start at 10 seconds (60s - 50s overlap)
                    self.assertEqual(trim_info[1]["start_time"], 10.0)
                    self.assertEqual(trim_info[1]["duration"], 50.0)
    
    @patch('os.path.exists')
    @patch('os.makedirs')
    @patch('os.listdir')
    @patch('main.parse_filename')
    @patch('main.group_videos_by_continuity')
    @patch('main.get_video_duration')
    def test_summary_only_mode(self, mock_duration, mock_group, mock_parse, mock_listdir, mock_makedirs, mock_exists):
        """Test the summary-only mode of process_dashcam_videos."""
        # Setup mocks
        mock_exists.return_value = True
        mock_listdir.return_value = ["20230615_170000_NF.mp4", "20230615_170100_NF.mp4"]
        
        # Mock parsed video info
        mock_parse.side_effect = [
            {
                "timestamp": datetime.datetime(2023, 6, 15, 17, 0, 0),
                "camera_type": "front",
                "filename": "20230615_170000_NF.mp4"
            },
            {
                "timestamp": datetime.datetime(2023, 6, 15, 17, 1, 0),
                "camera_type": "front",
                "filename": "20230615_170100_NF.mp4"
            }
        ]
        
        # Mock video grouping
        mock_group.return_value = [[
            {
                "timestamp": datetime.datetime(2023, 6, 15, 17, 0, 0),
                "camera_type": "front",
                "filename": "20230615_170000_NF.mp4"
            },
            {
                "timestamp": datetime.datetime(2023, 6, 15, 17, 1, 0),
                "camera_type": "front",
                "filename": "20230615_170100_NF.mp4"
            }
        ]]
        
        # Mock video duration
        mock_duration.return_value = 60.0
        
        # Test summary-only mode
        with patch('builtins.print') as mock_print:
            process_dashcam_videos(
                input_dir="/test/input",
                output_dir="/test/output",
                summary_only=True
            )
            
            # Verify makedirs was not called since summary_only=True
            mock_makedirs.assert_not_called()
            
            # Check that summary info was printed
            summary_called = False
            for call in mock_print.call_args_list:
                if "Summary complete. No files were processed" in str(call):
                    summary_called = True
                    break
            
            self.assertTrue(summary_called, "Summary completion message was not printed")
    
    @patch('os.path.exists')
    @patch('os.makedirs')
    @patch('os.listdir')
    @patch('main.parse_filename')
    @patch('main.group_videos_by_continuity')
    @patch('main.merge_videos_with_trim')
    def test_camera_type_filtering(self, mock_merge, mock_group, mock_parse, mock_listdir, mock_makedirs, mock_exists):
        """Test filtering videos by camera type."""
        # Setup mocks
        mock_exists.return_value = True
        mock_listdir.return_value = [
            "20230615_170000_NF.mp4",  # Front camera
            "20230615_170000_NR.mp4"   # Rear camera
        ]
        
        # Mock parsed video info
        mock_parse.side_effect = [
            {
                "timestamp": datetime.datetime(2023, 6, 15, 17, 0, 0),
                "camera_type": "front",
                "filename": "20230615_170000_NF.mp4"
            },
            {
                "timestamp": datetime.datetime(2023, 6, 15, 17, 0, 0),
                "camera_type": "rear",
                "filename": "20230615_170000_NR.mp4"
            }
        ]
        
        # Mock video grouping - each camera type has one group
        mock_group.return_value = [[
            {
                "timestamp": datetime.datetime(2023, 6, 15, 17, 0, 0),
                "camera_type": "front",  # This will match for front camera test
                "filename": "20230615_170000_NF.mp4"
            }
        ]]
        
        # Mock merge result
        mock_merge.return_value = True
        
        # Test with front camera filter
        with patch('builtins.print'):
            process_dashcam_videos(
                input_dir="/test/input",
                output_dir="/test/output",
                camera_type="front"
            )
            
            # Verify merge was called once for front camera
            mock_merge.assert_called_once()
            
        # Reset mocks for rear camera test
        mock_merge.reset_mock()
        mock_parse.side_effect = [
            {
                "timestamp": datetime.datetime(2023, 6, 15, 17, 0, 0),
                "camera_type": "front",
                "filename": "20230615_170000_NF.mp4"
            },
            {
                "timestamp": datetime.datetime(2023, 6, 15, 17, 0, 0),
                "camera_type": "rear",
                "filename": "20230615_170000_NR.mp4"
            }
        ]
        
        # Update mock group to return a rear camera group
        mock_group.return_value = [[
            {
                "timestamp": datetime.datetime(2023, 6, 15, 17, 0, 0),
                "camera_type": "rear",  # This will match for rear camera test
                "filename": "20230615_170000_NR.mp4"
            }
        ]]
        
        # Test with rear camera filter
        with patch('builtins.print'):
            process_dashcam_videos(
                input_dir="/test/input",
                output_dir="/test/output",
                camera_type="rear"
            )
            
            # Verify merge was called once for rear camera
            mock_merge.assert_called_once()

if __name__ == "__main__":
    unittest.main() 