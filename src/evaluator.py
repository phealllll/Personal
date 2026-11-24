import urllib.request
from pathlib import Path
import cv2
import numpy as np
from cv_verifier import compute_cosine_similarity, extract_face_embedding


PROJECT_ROOT = Path(__file__).resolve().parent.parent
EVAL_DIR = PROJECT_ROOT / "data" / "eval_benchmark"
EVIDENCE_DIR = PROJECT_ROOT / "evidence"

SAMPLE_FACE_URLS = {
    "subject_alpha": "https://raw.githubusercontent.com/opencv/opencv/4.x/samples/data/lena.jpg",
    "subject_beta": "https://raw.githubusercontent.com/opencv/opencv_extra/4.x/testdata/cv/face/david2.jpg",
}

WIDE_ACTION_URL = "https://raw.githubusercontent.com/opencv/opencv/4.x/samples/data/messi5.jpg"


def fetch_sample_image(name: str, url: str) -> np.ndarray:
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    img_path = EVAL_DIR / f"{name}.jpg"
    if not img_path.exists():
        urllib.request.urlretrieve(url, img_path)
    img = cv2.imread(str(img_path))
    if img is None:
        raise FileNotFoundError(f"Could not read downloaded sample image: {img_path}")
    return img


def run_cv_evaluation() -> None:
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    enrolled = {}
    genuine_scores = []
    impostor_scores = []
    failure_cases = []

    for name, url in SAMPLE_FACE_URLS.items():
        img = fetch_sample_image(name, url)
        emb, _ = extract_face_embedding(img)
        enrolled[name] = emb

        bright_probe = np.clip(img.astype(np.float32) * 1.15 + 10, 0, 255).astype(np.uint8)
        dark_probe = np.clip(img.astype(np.float32) * 0.45, 0, 255).astype(np.uint8)
        blurred_probe = cv2.GaussianBlur(img, (15, 15), 0)

        for label, probe in [
            ("bright_shift", bright_probe),
            ("low_light_55pct_drop", dark_probe),
            ("motion_blur", blurred_probe),
        ]:
            try:
                p_emb, _ = extract_face_embedding(probe)
                score = compute_cosine_similarity(enrolled[name], p_emb)
                genuine_scores.append((name, label, score))
            except ValueError as exc:
                failure_cases.append(f"{name}_{label}: {exc}")

        occluded = img.copy()
        h, w = occluded.shape[:2]
        cv2.rectangle(occluded, (int(w * 0.2), int(h * 0.2)), (int(w * 0.8), int(h * 0.85)), (15, 15, 15), -1)
        try:
            extract_face_embedding(occluded)
        except ValueError as exc:
            failure_cases.append(f"{name}_occluded_frame: {exc}")

    wide_img = fetch_sample_image("wide_distance_action", WIDE_ACTION_URL)
    try:
        extract_face_embedding(wide_img)
    except ValueError as exc:
        failure_cases.append(f"wide_distance_action (small off-axis face): {exc}")

    blank = np.zeros((320, 320, 3), dtype=np.uint8)
    try:
        extract_face_embedding(blank)
    except ValueError as exc:
        failure_cases.append(f"blank_camera_frame: {exc}")

    names = list(enrolled.keys())
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            score = compute_cosine_similarity(enrolled[names[i]], enrolled[names[j]])
            impostor_scores.append((names[i], names[j], score))

    thresholds = [0.250, 0.363, 0.500, 0.750]
    lines = [
        "=== NOVAWAREHOUSE AIDA 2154 COMPUTER VISION THRESHOLD EVALUATION ===",
        "Dataset: Official OpenCV 4.x Public Sample Portraits (Apache-2.0 License) with controlled lighting, blur, distance, and occlusion perturbations.",
        "Limitation: Small public reference set (2 enrolled subjects, 6 genuine probes, 1 impostor pair); production deployment requires diverse multi-demographic consent-based employee trials.",
        f"Genuine Comparisons: {len(genuine_scores)} | Impostor Comparisons: {len(impostor_scores)}",
        f"Mean Genuine Similarity: {np.mean([s for _, _, s in genuine_scores]):.4f} | Mean Impostor Similarity: {np.mean([s for _, _, s in impostor_scores]):.4f}",
        "\n--- Threshold Sensitivity Table ---",
        f"{'Threshold':<12} | {'False Matches (FAR)':<24} | {'Missed Matches (FRR)':<24}",
        "-" * 66,
    ]

    for th in thresholds:
        false_accepts = sum(1 for _, _, s in impostor_scores if s >= th)
        false_rejects = sum(1 for _, _, s in genuine_scores if s < th)
        far_pct = (false_accepts / len(impostor_scores) * 100) if impostor_scores else 0.0
        frr_pct = (false_rejects / len(genuine_scores) * 100) if genuine_scores else 0.0
        lines.append(
            f"{th:<12.3f} | {false_accepts}/{len(impostor_scores)} ({far_pct:5.1f}%)           | {false_rejects}/{len(genuine_scores)} ({frr_pct:5.1f}%)"
        )

    lines.append("\n--- Genuine Probe Scores ---")
    for name, label, s in genuine_scores:
        lines.append(f"- {name} ({label}): cosine={s:.4f}")

    lines.append("\n--- Impostor Pair Scores ---")
    for a, b, s in impostor_scores:
        lines.append(f"- {a} vs {b}: cosine={s:.4f}")

    lines.append("\n--- Representative Failure Cases ---")
    for fc in failure_cases:
        lines.append(f"- {fc}")

    report = "\n".join(lines)
    print(report)
    (EVIDENCE_DIR / "aida2154_cv_report.txt").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    run_cv_evaluation()