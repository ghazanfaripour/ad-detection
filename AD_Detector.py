import argparse
import subprocess
import soundfile as sf
import numpy as np
import json
import base64
import tempfile
import os
from scipy.spatial.distance import cosine

# ===================== Configuration =====================

FP_CALC_PATH = r"C:\your path\fpcalc.exe"
input_file = "file.wav"

STREAM_FILE = "fixed_stream.wav"

# Convert to mono 44.1kHz WAV
subprocess.run([
    "ffmpeg", "-y", "-i", input_file,
    "-ar", "44100", "-ac", "1", STREAM_FILE
])
FINGERPRINTS_JSON = "fingerprints_segments.json"

WINDOW_SECONDS = 10
STEP_SECONDS = 1

SCORE_THRESHOLD = 0.95
MARGIN_THRESHOLD = 0.08
CONSECUTIVE_REQUIRED = 2

PEARSON_WEIGHT = 0.75
COSINE_WEIGHT = 0.25

# =========================================================


def fpcalc_fingerprint(audio_path) -> np.ndarray:
    """
    Generate a raw Chromaprint fingerprint using fpcalc
    and return it as a uint8 numpy array.
    """
    proc = subprocess.run(
        [FP_CALC_PATH, "-raw", audio_path],
        capture_output=True,
        text=True
    )

    if proc.returncode != 0:
        raise RuntimeError(f"fpcalc failed: {proc.stderr.strip()}")

    for line in proc.stdout.splitlines():
        if line.startswith("FINGERPRINT="):
            values = line.split("=", 1)[1]
            return np.array([int(v) & 0xFF for v in values.split(",")], dtype=np.uint8)

    raise RuntimeError("Fingerprint not found in fpcalc output")


def load_reference_fingerprints(path: str) -> dict:
    """
    Load segmented fingerprints from JSON and
    decode Base64 fingerprints into numpy arrays.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for ad_name, segments in data.items():
        for segment in segments:
            segment["fp_arr"] = np.frombuffer(
                base64.b64decode(segment["fingerprint"]),
                dtype=np.uint8
            )

    return data


def pearson_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    Normalized Pearson correlation mapped to [0, 1].
    """
    min_len = min(len(a), len(b))
    if min_len == 0:
        return 0.0

    a = a[:min_len].astype(np.float32)
    b = b[:min_len].astype(np.float32)

    a_std = a.std()
    b_std = b.std()

    if a_std == 0 or b_std == 0:
        return 0.0

    corr = np.mean((a - a.mean()) * (b - b.mean())) / (a_std * b_std)
    return (corr + 1.0) / 2.0


def cosine_similarity_safe(a: np.ndarray, b: np.ndarray) -> float:
    """
    Cosine similarity with basic numerical safety.
    """
    min_len = min(len(a), len(b))
    if min_len == 0:
        return 0.0

    a = a[:min_len].astype(np.float32)
    b = b[:min_len].astype(np.float32)

    sim = 1.0 - cosine(a, b)
    return 0.0 if np.isnan(sim) else float(sim)


def combined_score(a: np.ndarray, b: np.ndarray) -> float:
    """
    Weighted combination of Pearson and Cosine similarity.
    """
    return (
        PEARSON_WEIGHT * pearson_similarity(a, b)
        + COSINE_WEIGHT * cosine_similarity_safe(a, b)
    )


# ===================== Main =====================

stored_fps = load_reference_fingerprints(FINGERPRINTS_JSON)
ad_names = list(stored_fps.keys())

stream, sr = sf.read(STREAM_FILE)
window_size = int(WINDOW_SECONDS * sr)
step_size = int(STEP_SECONDS * sr)

consecutive_hits = {ad: 0 for ad in ad_names}
recent_scores = {ad: [] for ad in ad_names}

print(f"Starting detection (window={WINDOW_SECONDS}s, step={STEP_SECONDS}s)")

for start in range(0, len(stream) - window_size + 1, step_size):
    chunk = stream[start:start + window_size]

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        sf.write(tmp.name, chunk, sr)
        tmp_path = tmp.name

    try:
        live_fp = fpcalc_fingerprint(tmp_path)
    finally:
        os.remove(tmp_path)

    scores = []
    for ad in ad_names:
        best_segment_score = max(
            combined_score(live_fp, seg["fp_arr"])
            for seg in stored_fps[ad]
        )
        scores.append((ad, best_segment_score))

    scores.sort(key=lambda x: x[1], reverse=True)

    best_ad, best_score = scores[0]
    second_score = scores[1][1] if len(scores) > 1 else 0.0

    t_sec = start / sr
    mm = int(t_sec // 60)
    ss = int(t_sec % 60)

    top3_str = ", ".join(f"{n}:{s:.3f}" for n, s in scores[:3])
    print(f"[{mm:02d}:{ss:02d}] top3 -> {top3_str}", end="")

    if best_score >= SCORE_THRESHOLD:
        print(f"   AD_detected={best_ad}")
    else:
        print("")

    if (
        best_score >= SCORE_THRESHOLD
        and (best_score - second_score) >= MARGIN_THRESHOLD
    ):
        consecutive_hits[best_ad] += 1
        recent_scores[best_ad].append(best_score)
    else:
        for ad in ad_names:
            consecutive_hits[ad] = 0
            recent_scores[ad].clear()

    if consecutive_hits[best_ad] >= CONSECUTIVE_REQUIRED:
        avg_score = np.mean(recent_scores[best_ad])
        print(
            f"DETECTED -> {best_ad} at {mm:02d}:{ss:02d} "
            f"avg_score={avg_score:.3f}"
        )
        consecutive_hits[best_ad] = 0
        recent_scores[best_ad].clear()

print("Done.")

