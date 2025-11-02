# Video-from-Photo Extraction Tool

A Python utility to extract embedded videos from motion photos (JPEG files with appended MP4 data). This tool is particularly useful for Samsung, Google, and other smartphone cameras that embed short video clips within motion photo files.

## Features

- **Extract embedded MP4 videos** from JPEG motion photos
- **Optional XMP metadata validation** to verify motion photo tags
- **Frame extraction** from extracted videos using FFmpeg (optional)
- **Configurable settings** with persistent configuration file
- **Batch processing** of entire directories
- **Detailed logging** of extraction process

## How It Works

Many modern smartphones create "motion photos" or "live photos" by appending a short MP4 video to the end of a JPEG image file. This tool:

1. Scans JPEG files for the End of Image (EOI) marker
2. Optionally checks XMP metadata for motion photo tags
3. Detects MP4 data appended after the JPEG
4. Extracts the MP4 video to a separate file
5. Optionally extracts individual frames from the video

## Requirements

- Python 3.10 or higher
- FFmpeg (optional, only needed for frame extraction)

## Installation

1. Clone this repository:
```bash
git clone https://github.com/ellockie/extract-videos-from-photos.git
cd extract-videos-from-photos
```

2. (Optional) Install FFmpeg for frame extraction:
   - **Windows**: Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH
   - **Linux**: `sudo apt-get install ffmpeg`
   - **macOS**: `brew install ffmpeg`

## Usage

### Basic Usage

Extract videos from the current directory:
```bash
python extract_videos.py
```

### Specify Input Directory

Extract videos from a specific directory:
```bash
python extract_videos.py /path/to/photos
```

### Examples

```bash
# Process photos in a specific folder
python extract_videos.py "C:\Users\YourName\Pictures\MotionPhotos"

# Process current directory
python extract_videos.py .
```

## Configuration

### Settings in Script

Edit the following variables at the top of `extract_videos.py`:

- **`INPUT_DIR`**: Default input directory (default: current directory)
- **`REQUIRE_XMP_MOTION`**: Require motion photo XMP tags (default: `False`)
- **`MAX_TAIL_SEARCH`**: Maximum bytes to search for MP4 data (default: 512,000)

### Configuration File

The script can save FFmpeg path for future use:

1. Create `config.local.json` (not tracked by git):
```json
{
  "ffmpeg_path": "C:\\ffmpeg\\bin\\ffmpeg.exe"
}
```

Or use the provided example:
```bash
cp config.example.json config.local.json
```

Then edit `config.local.json` with your FFmpeg path.

## Output

### Directory Structure

```
your-photos/
├── photo1.jpg
├── photo2.jpg
└── _extracted_videos/          # Created automatically
    ├── photo1.mp4
    ├── photo2.mp4
    └── _frames/                # Created if frame extraction is used
        ├── photo1/
        │   ├── photo1_0001.jpg
        │   ├── photo1_0002.jpg
        │   └── ...
        └── photo2/
            ├── photo2_0001.jpg
            └── ...
```

### Output Example

```
Processing: IMG_1234.jpg
  File size: 5432198 bytes
  ✓ JPEG EOI found at position 5400000
  ⚠️  XMP motion check disabled
  ✓ MP4 found at offset 5400032
  MP4 size: 32166 bytes
[+] Extracted video from IMG_1234.jpg

Done. Extracted 1 / 1 files.
Output folder: C:\Photos\_extracted_videos

Successfully extracted 1 video(s).
Do you want to extract frames from these videos? (y/n):
```

## Frame Extraction

After extracting videos, the script can optionally extract individual frames:

- Extracts frames at 1 frame per second
- Saves as high-quality JPEG images
- Organizes frames in `_frames` subdirectory
- Requires FFmpeg to be installed

## Supported Formats

### Input
- JPEG/JPG files with appended MP4 data
- Motion photos from Samsung, Google Pixel, and other smartphones

### Motion Photo Tags (Optional)
The script can detect the following XMP tags:
- `GCamera:MotionPhoto`
- `Camera:MotionPhoto`
- `MotionPhoto`
- `GCamera:MicroVideo`

## Troubleshooting

### No videos extracted

1. **Check if your photos contain embedded videos**:
   - Some photos may not have motion data
   - Try with photos you know are motion photos

2. **Enable debug output**:
   - The script shows detailed information about each file
   - Look for "No MP4 data found" messages

3. **Disable XMP checking**:
   - Set `REQUIRE_XMP_MOTION = False` in the script
   - Some files may have video without proper XMP tags

### FFmpeg not found

If frame extraction fails:
1. Ensure FFmpeg is installed
2. Verify the path in `config.local.json`
3. Test FFmpeg in terminal: `ffmpeg -version`

### Permission errors

Ensure you have:
- Read permission for input directory
- Write permission for output directory

## Development

### File Structure

```
extract-videos-from-photos/
├── extract_videos.py           # Main script
├── config.example.json         # Example configuration
├── config.local.json           # Local config (gitignored)
├── extracted_videos/           # Default output (gitignored)
├── README.md                   # This file
└── ___PUBLIC_REPO.md          # Repository visibility marker
```

### Contributing

Contributions are welcome! This is a public repository open to community collaboration.

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

This project is open source and available for free use, modification, and distribution.

## Acknowledgments

- Supports motion photo formats from Samsung, Google Pixel, and compatible devices
- Built with Python's standard library for maximum compatibility

## Contact

For issues, questions, or suggestions, please open an issue on GitHub.
