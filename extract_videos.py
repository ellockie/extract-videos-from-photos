#!/usr/bin/env python3
import pathlib
import sys
import subprocess
import json
from typing import Optional

# --- SETTINGS -------------------------------------------------
INPUT_DIR = pathlib.Path(".")
OUTPUT_DIR = pathlib.Path("./extracted_videos")  # This will be updated dynamically
REQUIRE_XMP_MOTION = (
    False  # Changed to False - set to True if your files have motion XMP tags
)
MAX_TAIL_SEARCH = 512_000  # search for MP4 only in last 500 KB
CONFIG_FILE = (
    pathlib.Path(__file__).parent / "config.local.json"
)  # Not committed to git
# --------------------------------------------------------------


# ---- JPEG / XMP HELPERS --------------------------------------
def find_jpeg_eoi(data: bytes) -> Optional[int]:
    """
    Find the End Of Image marker (FFD9) in JPEG.
    Return index of the *end* (i.e. position AFTER 0xFFD9) so data[eoi:] is the tail.
    """
    marker = b"\xff\xd9"
    idx = data.find(marker)
    if idx == -1:
        return None
    return idx + 2  # point to byte after EOI


def extract_xmp_packets(data: bytes) -> list[bytes]:
    """
    Very lightweight JPEG APP1 scanner to pull XMP blocks.
    We don't fully parse JPEG; we scan for the XMP header.
    """
    packets = []
    xmp_sig = b"http://ns.adobe.com/xap/1.0/"
    i = 0
    n = len(data)
    # JPEG begins with FFD8
    if not data.startswith(b"\xff\xd8"):
        return packets
    i = 2
    while i < n - 1:
        if data[i] != 0xFF:
            break
        marker = data[i + 1]
        i += 2
        if marker in (0xD9, 0xDA):  # EOI or SOS -> stop
            break
        if i + 2 > n:
            break
        seg_len = int.from_bytes(data[i : i + 2], "big")
        if seg_len < 2:  # Invalid segment length
            break
        seg_start = i + 2
        seg_end = seg_start + seg_len - 2
        if seg_end > n:
            break
        segment = data[seg_start:seg_end]
        if segment.startswith(xmp_sig):
            # real XMP starts right after the signature + \x00
            # some files: b"http://ns.adobe.com/xap/1.0/\x00<?xpacket..."
            zero_idx = segment.find(b"\x00")
            if zero_idx != -1:
                packets.append(segment[zero_idx + 1 :])
            else:
                packets.append(segment)
        i = seg_end
    return packets


def xmp_indicates_motion(xmps: list[bytes]) -> bool:
    """
    Samsung/Google style motion photos often have tags like:
      <GCamera:MotionPhoto>1</GCamera:MotionPhoto>
      <Camera:MotionPhoto>1</Camera:MotionPhoto>
      <MotionPhoto>1</MotionPhoto>
      <GCamera:MicroVideo>1</GCamera:MicroVideo>
    We'll accept any of those strings in any XMP block.
    """
    needles = [
        b"MotionPhoto",
        b"MicroVideo",
        b"GCamera:MotionPhoto",
        b"Camera:MotionPhoto",
    ]
    for x in xmps:
        for nd in needles:
            if nd in x:
                return True
    return False


# ---- MP4 DETECTION -------------------------------------------
def find_appended_mp4(data: bytes, jpeg_end: int) -> Optional[int]:
    """
    Find MP4 that is appended AFTER jpeg_end.
    We look for 'ftyp' near the end of the file, and ensure start >= jpeg_end.
    Also enforce MP4 box layout: [4 bytes size][4 bytes 'ftyp']...
    """
    # Search in the tail portion after JPEG
    tail_data = data[jpeg_end:]

    # Look for ftyp signature
    idx = tail_data.find(b"ftyp")
    if idx == -1:
        return None

    # MP4: 4 bytes length, then 'ftyp'
    mp4_start_in_tail = idx - 4
    if mp4_start_in_tail < 0:
        return None

    mp4_start = jpeg_end + mp4_start_in_tail

    # sanity check: first 4 bytes = size
    if mp4_start + 8 > len(data):
        return None

    size_bytes = data[mp4_start : mp4_start + 4]
    mp4_size = int.from_bytes(size_bytes, "big", signed=False)

    # size must be at least header size
    if mp4_size < 16:
        return None

    return mp4_start


def extract_from_file(jpg_path: pathlib.Path, out_dir: pathlib.Path) -> bool:
    print(f"Processing: {jpg_path.name}")
    data = jpg_path.read_bytes()
    print(f"  File size: {len(data)} bytes")

    # 1) Must be JPEG with EOI
    jpeg_end = find_jpeg_eoi(data)
    if jpeg_end is None:
        print(f"  ❌ Not a valid JPEG (no EOI marker found)")
        return False
    print(f"  ✓ JPEG EOI found at position {jpeg_end}")

    # 2) Optional: must have motion XMP
    if REQUIRE_XMP_MOTION:
        xmps = extract_xmp_packets(data)
        print(f"  Found {len(xmps)} XMP packets")
        if not xmp_indicates_motion(xmps):
            print(f"  ❌ No motion photo XMP tags found")
            # Debug: show what XMP content we found
            for i, xmp in enumerate(xmps):
                xmp_preview = xmp[:200].decode("utf-8", errors="ignore")
                print(f"    XMP {i+1}: {xmp_preview}...")
            return False
        print(f"  ✓ Motion photo XMP tags found")
    else:
        print(f"  ⚠️  XMP motion check disabled")

    # 3) Must have appended MP4 AFTER JPEG
    mp4_offset = find_appended_mp4(data, jpeg_end)
    if mp4_offset is None:
        print(f"  ❌ No MP4 data found after JPEG")
        # Debug: check if there's any data after JPEG
        remaining_data = len(data) - jpeg_end
        print(f"    Remaining data after JPEG: {remaining_data} bytes")
        if remaining_data > 16:  # Only show sample if there's substantial data
            tail_sample = data[jpeg_end : jpeg_end + 50]
            print(f"    First 50 bytes of tail: {tail_sample}")
            # Look for any video signatures
            video_sigs = [b"ftyp", b"moov", b"mdat", b"mvhd"]
            for sig in video_sigs:
                if sig in data[jpeg_end:]:
                    pos = data[jpeg_end:].find(sig)
                    print(f"    Found '{sig.decode()}' signature at offset +{pos}")
        return False

    print(f"  ✓ MP4 found at offset {mp4_offset}")
    mp4_size = len(data) - mp4_offset
    print(f"  MP4 size: {mp4_size} bytes")

    # Create output directory if it doesn't exist
    out_dir.mkdir(parents=True, exist_ok=True)

    mp4_data = data[mp4_offset:]
    out_name = jpg_path.stem + ".mp4"
    out_file = out_dir / out_name
    out_file.write_bytes(mp4_data)
    return True


def load_ffmpeg_path() -> Optional[str]:
    """Load ffmpeg path from config file."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
                return config.get("ffmpeg_path")
        except Exception as e:
            print(f"Warning: Could not read config file: {e}")
    return None


def save_ffmpeg_path(path: str) -> None:
    """Save ffmpeg path to config file."""
    try:
        config = {}
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
        config["ffmpeg_path"] = path
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
        print(f"✓ Saved ffmpeg path to {CONFIG_FILE}")
    except Exception as e:
        print(f"Warning: Could not save config file: {e}")


def extract_frames_from_video(video_path: pathlib.Path, ffmpeg_path: str) -> bool:
    """Extract frames from a video file using ffmpeg."""
    frames_dir = video_path.parent / "_frames" / video_path.stem
    frames_dir.mkdir(parents=True, exist_ok=True)

    output_pattern = frames_dir / f"{video_path.stem}_%04d.jpg"

    cmd = [
        ffmpeg_path,
        "-i",
        str(video_path),
        "-vf",
        "fps=1",  # 1 frame per second
        "-q:v",
        "2",  # High quality JPEG
        str(output_pattern),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ❌ Failed to extract frames: {e}")
        return False
    except FileNotFoundError:
        print(f"  ❌ ffmpeg not found at: {ffmpeg_path}")
        return False


def ask_user_for_frame_extraction(extracted_videos: list[pathlib.Path]) -> None:
    """Ask user if they want to extract frames from videos."""
    if not extracted_videos:
        return

    print("\n" + "=" * 50)
    print(f"Successfully extracted {len(extracted_videos)} video(s).")
    print("=" * 50)

    response = (
        input("\nDo you want to extract frames from these videos? (y/n): ")
        .strip()
        .lower()
    )
    if response != "y":
        print("Skipping frame extraction.")
        return

    # Load or ask for ffmpeg path
    ffmpeg_path = load_ffmpeg_path()

    if not ffmpeg_path:
        print("\n⚠️  No ffmpeg path configured.")
        print("You can configure ffmpeg path in the config file for future use.")
        print(f"Config file location: {CONFIG_FILE}")
        print("\nPlease provide the path to ffmpeg executable:")
        print("Examples:")
        print("  Windows: C:\\ffmpeg\\bin\\ffmpeg.exe")
        print("  Linux/Mac: /usr/bin/ffmpeg or /usr/local/bin/ffmpeg")

        ffmpeg_path = input("\nEnter ffmpeg path (or press Enter to skip): ").strip()

        if not ffmpeg_path:
            print("Skipping frame extraction.")
            return

        # Validate the path
        if not pathlib.Path(ffmpeg_path).exists():
            print(f"❌ Path does not exist: {ffmpeg_path}")
            print("Skipping frame extraction.")
            return

        # Ask if user wants to save this path
        save_response = input("Save this path for future use? (y/n): ").strip().lower()
        if save_response == "y":
            save_ffmpeg_path(ffmpeg_path)

    # Extract frames from all videos
    print(f"\nExtracting frames using: {ffmpeg_path}")
    print("-" * 50)

    success_count = 0
    for video in extracted_videos:
        print(f"Extracting frames from: {video.name}")
        if extract_frames_from_video(video, ffmpeg_path):
            print(f"  ✓ Frames extracted successfully")
            success_count += 1
        else:
            print(f"  ❌ Failed to extract frames")

    print("-" * 50)
    print(
        f"Frame extraction complete: {success_count}/{len(extracted_videos)} successful"
    )


def main():
    global INPUT_DIR, OUTPUT_DIR
    print("-" * 50)
    if len(sys.argv) > 1:
        INPUT_DIR = pathlib.Path(sys.argv[1])
    else:
        # No input argument provided - inform the user
        print("No input directory provided!")
        print(f"Usage: {sys.argv[0]} <input_directory>")
        print(f"Example: {sys.argv[0]} /path/to/photos")
        print(f"")
        print(f"Current default directory: {INPUT_DIR.resolve()}")
        print(f"You can provide an input directory as a command line argument,")
        print(f"or the script will use the current directory by default.")
        print(f"")
        print(f"Proceeding with default directory: {INPUT_DIR.resolve()}")

    # Set output directory inside input directory with underscore prefix
    OUTPUT_DIR = INPUT_DIR / "_extracted_videos"

    print(f"\nScanning for JPEG files in: {INPUT_DIR.resolve()}")
    print(f"XMP motion requirement: {'ON' if REQUIRE_XMP_MOTION else 'OFF'}")

    count_total = 0
    count_extracted = 0
    extracted_videos = []

    for ext in ("*.jpg", "*.jpeg", "*.JPG", "*.JPEG"):
        for jpg in INPUT_DIR.glob(ext):
            count_total += 1
            if extract_from_file(jpg, OUTPUT_DIR):
                print(f"[+] Extracted video from {jpg.name}")
                count_extracted += 1
                extracted_videos.append(OUTPUT_DIR / f"{jpg.stem}.mp4")
            else:
                print(f"[-] Skipped (no proper motion video): {jpg.name}")
            print()  # blank line for readability

    print(f"\nDone. Extracted {count_extracted} / {count_total} files.")
    if count_extracted > 0:
        print(f"Output folder: {OUTPUT_DIR.resolve()}")
    print("-" * 50)

    # Ask user about frame extraction
    ask_user_for_frame_extraction(extracted_videos)


if __name__ == "__main__":
    main()
