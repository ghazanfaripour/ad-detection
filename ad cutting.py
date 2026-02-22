import subprocess

stream_file = r"C:\file.wav"

ad_times = [
    ("00:21:39", "00:22:20"),  # 02:15 - 02:40
    ("00:29:00", "00:29:21"),  # 02:46 - 03:00
    ("00:43:46", "00:44:20"),  # 03:01 - 03:21
]


for i, (start, end) in enumerate(ad_times):
    output_file = f"AD_000{i+4}.wav"
    cmd = [
        "ffmpeg",
        "-i", stream_file,
        "-ss", start,
        "-to", end,
        "-c", "copy",
        output_file
    ]
    subprocess.run(cmd, check=True)
    print(f"Extracted {output_file}")

