#!/usr/bin/env python3
import pathlib
import sys
from typing import Optional

# --- SETTINGS -------------------------------------------------
INPUT_DIR = pathlib.Path(".")
OUTPUT_DIR = pathlib.Path("./extracted_videos")  # This will be updated dynamically
REQUIRE_XMP_MOTION = True  # set to False if your files don't have that XMP flag
MAX_TAIL_SEARCH = 512_000  # search for MP4 only in last 500 KB
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
    tail_start = max(jpeg_end, len(data) - MAX_TAIL_SEARCH)
    tail = data[tail_start:]

    idx = tail.find(b"ftyp")
    if idx == -1:
        return None

    # MP4: 4 bytes length, then 'ftyp'
    mp4_start = tail_start + idx - 4
    if mp4_start < jpeg_end:
        # then it's not truly appended
        return None

    # sanity check: first 4 bytes = size
    if mp4_start < 0 or mp4_start + 8 > len(data):
        return None

    size_bytes = data[mp4_start : mp4_start + 4]
    mp4_size = int.from_bytes(size_bytes, "big", signed=False)

    # size must be at least header size
    if mp4_size < 16:
        return None
    # size cannot exceed file (some Samsung files put *actual* file size here, that's OK)
    if mp4_start + mp4_size > len(data) + 8:  # allow a bit of slop
        # looks bogus
        pass  # don't fail hard, some cameras do weird stuff

    return mp4_start


def extract_from_file(jpg_path: pathlib.Path, out_dir: pathlib.Path) -> bool:
    data = jpg_path.read_bytes()

    # 1) Must be JPEG with EOI
    jpeg_end = find_jpeg_eoi(data)
    if jpeg_end is None:
        return False

    # 2) Optional: must have motion XMP
    if REQUIRE_XMP_MOTION:
        xmps = extract_xmp_packets(data)
        if not xmp_indicates_motion(xmps):
            return False

    # 3) Must have appended MP4 AFTER JPEG
    mp4_offset = find_appended_mp4(data, jpeg_end)
    if mp4_offset is None:
        return False

    # Create output directory if it doesn't exist
    out_dir.mkdir(parents=True, exist_ok=True)

    mp4_data = data[mp4_offset:]
    out_name = jpg_path.stem + ".mp4"
    out_file = out_dir / out_name
    out_file.write_bytes(mp4_data)
    return True


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

    count_total = 0
    count_extracted = 0

    for ext in ("*.jpg", "*.jpeg", "*.JPG", "*.JPEG"):
        for jpg in INPUT_DIR.glob(ext):
            count_total += 1
            if extract_from_file(jpg, OUTPUT_DIR):
                print(f"[+] Extracted video from {jpg.name}")
                count_extracted += 1
            else:
                print(f"[-] Skipped (no proper motion video): {jpg.name}")

    print(f"\nDone. Extracted {count_extracted} / {count_total} files.")
    print(f"Output folder: {OUTPUT_DIR.resolve()}")
    print("-" * 50)


if __name__ == "__main__":
    main()
