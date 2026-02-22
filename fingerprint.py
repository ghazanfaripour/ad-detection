import subprocess
import numpy as np
import json
import base64
import os

#  fpcalc path
FP_CALC_PATH = r"C:\your path\fpcalc.exe"
input_files = ["AD_0001.wav", "AD_0002.wav", "AD_0003.wav","AD_0004.wav", "AD_0005.wav", "AD_0006.wav"]
fixed_files = ["AD_0001_fixed.wav", "AD_0002_fixed.wav", "AD_0003_fixed.wav", "AD_0004_fixed.wav", "AD_0005_fixed.wav", "AD_0006_fixed.wav"]

for inp, out in zip(input_files, fixed_files):
    subprocess.run([
        "ffmpeg", "-y", "-i", inp,
        "-ar", "44100", "-ac", "1", out
    ])
#  (mono 44.1kHz)
ads = {
    "ad_1": "AD_0001_fixed.wav",  #  ~15s
    "ad_2": "AD_0002_fixed.wav",  #  ~20s
    "ad_3": "AD_0003_fixed.wav",  #  ~25s
    "ad_4": "AD_0004_fixed.wav",  #  ~41s
    "ad_5": "AD_0005_fixed.wav",  #  ~21s
    "ad_6": "AD_0006_fixed.wav"   #  ~35s
}
# parameters
SEGMENT_LENGTH = 10  #  fingerprint segment length
STEP = 1  # step sliding

output = {}

def fpcalc_fingerprint_bytes(audio_path):
    """Call fpcalc and return fingerprint as bytes (uint8)."""
    proc = subprocess.run([FP_CALC_PATH, "-raw", audio_path],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"fpcalc failed: {proc.stderr.strip()}")
    for line in proc.stdout.splitlines():
        if line.startswith("FINGERPRINT="):
            fp_str = line.split("=", 1)[1].strip()
            arr = np.array([int(x) & 0xFF for x in fp_str.split(",")], dtype=np.uint8)
            return arr
    raise RuntimeError("Fingerprint not found in fpcalc output")

for name, path in ads.items():
    #  ffprobe file time
    proc = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                           "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path],
                          capture_output=True, text=True)
    duration = float(proc.stdout.strip())
    segments = []
    offset = 0.0
    while offset + SEGMENT_LENGTH <= duration:
        #  segment with ffmpeg (mono 44.1kHz)
        seg_file = f"tmp_{name}_{int(offset)}.wav"
        subprocess.run([
            "ffmpeg", "-y", "-ss", str(offset), "-t", str(SEGMENT_LENGTH),
            "-i", path, "-ar", "44100", "-ac", "1", seg_file
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # fingerprint generation
        fp_arr = fpcalc_fingerprint_bytes(seg_file)
        fp_b64 = base64.b64encode(fp_arr.tobytes()).decode("utf-8")
        segments.append({
            "offset": offset,
            "length": SEGMENT_LENGTH,
            "fingerprint": fp_b64
        })
        os.remove(seg_file)
        offset += STEP
    output[name] = segments

# save JSON
with open("fingerprints_segments.json", "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2)

print("Fingerprints for all ads generated and saved in fingerprints_segments.json")

