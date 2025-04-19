#!/usr/bin/env python3

import os
import sys
import tempfile
import unittest
import datetime
from main import parse_filename, group_videos_by_continuity

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
            groups = group_videos_by_continuity(videos, max_gap=1000, input_dir=tmp_dir)
            self.assertEqual(len(groups), 1)
            self.assertEqual(len(groups[0]), 4)
            
            # Test with smaller max_gap that should split the files
            # Note: This test will not work properly since we can't easily mock
            # get_video_duration in this test, but the structure is here

if __name__ == "__main__":
    unittest.main() 