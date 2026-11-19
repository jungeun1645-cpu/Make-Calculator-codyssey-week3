import json
import time
from pathlib import Path

EPSILON = 1e-9


def normalize_label(value):
    """JSON의 기대 라벨을 Cross/X 표준 표기로 변환한다."""
    aliases = {"+": "Cross", "cross": "Cross", "x": "X"}
    return aliases.get(str(value).strip().lower())


def normalize_filter_key(value):
    """필터 키의 대소문자 및 +/X 표기 차이를 정규화한다."""
    label = normalize_label(value)
    if label == "Cross":
        return "cross"
    if label == "X":
        return "x"
    raise ValueError(f"지원하지 않는 필터 키: {value}")


def get_filter_pair(filters, size):
    """size_N과 필터 키를 정규화하여 해당 크기의 필터 두 개를 찾는다."""
    size_key = f"size_{size}"
    matching_sizes = {str(key).strip().lower(): key for key in filters}
    if size_key not in matching_sizes:
        raise ValueError(
            f"{size_key} 필터가 없습니다. 사용 가능한 크기: "
            f"{', '.join(map(str, filters.keys())) or '없음'}"
        )
    pair = filters[matching_sizes[size_key]]
    if not isinstance(pair, dict):
        raise ValueError(f"{size_key}: 필터 쌍은 객체여야 합니다.")
    normalized = {}
    for raw_key, matrix in pair.items():
        key = normalize_filter_key(raw_key)
        if key in normalized:
            raise ValueError(f"{size_key}: 중복된 필터 키 {key}")
        normalized[key] = matrix
    if "cross" not in normalized or "x" not in normalized:
        raise ValueError(f"{size_key}: Cross와 X 필터가 모두 필요합니다.")
    return normalized["cross"], normalized["x"]


def mac(pattern, filter_data):
    n = len(pattern)
    total = 0.0
    for i in range(n):
        for j in range(n):
            total += pattern[i][j] * filter_data[i][j]
    return total


def predict(pattern, filter_a, filter_b):
    score_a = mac(pattern, filter_a)
    score_b = mac(pattern, filter_b)
    if abs(score_a - score_b) < EPSILON:
        label = "UNDECIDED"
    elif score_a > score_b:
        label = "Cross"
    else:
        label = "X"
    return score_a, score_b, label


def read_matrix(name):
    print(f"=== {name} 입력 ===")
    matrix = []
    for i in range(3):
        while True:
            try:
                row = [float(x) for x in input(f"{i + 1}번째 줄 입력: ").split()]
                if len(row) != 3:
                    print("입력 오류: 숫자를 정확히 3개 입력해주세요. 예: 1 0 1")
                    continue
                matrix.append(row)
                break
            except ValueError:
                print("입력 오류: 숫자만 입력해주세요. 예: 1 0 1")
    return matrix


def validate_matrix(matrix, size, name):
    if not isinstance(matrix, list) or len(matrix) != size:
        raise ValueError(f"{name}: 행 개수가 {size}개가 아닙니다.")
    for i, row in enumerate(matrix, start=1):
        if not isinstance(row, list) or len(row) != size:
            raise ValueError(f"{name}: {i}행의 열 개수가 {size}개가 아닙니다.")
        if any(type(value) not in (int, float) for value in row):
            raise ValueError(f"{name}: {i}행에 숫자가 아닌 값이 있습니다.")


def manual_mode():
    filter_a = read_matrix("필터 A (Cross)")
    filter_b = read_matrix("필터 B (X)")
    pattern = read_matrix("입력 패턴")

    # 사용자 입력과 출력은 제외하고 MAC 판정 함수 호출 시간만 측정한다.
    start = time.perf_counter()
    score_a, score_b, label = predict(pattern, filter_a, filter_b)
    elapsed_ms = (time.perf_counter() - start) * 1000

    print("=== 사용자 입력 MAC 분석 결과 ===")
    print(f"필터 A 점수: {score_a}")
    print(f"필터 B 점수: {score_b}")
    print(f"최종 판정: {'판정 불가' if label == 'UNDECIDED' else label}")
    print(f"MAC 연산 시간: {elapsed_ms:.6f} ms (입력/출력 제외, 두 필터 판정 포함)")


def json_mode():
    path = Path(__file__).with_name("data.json")
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        print(f"JSON 파일 읽기 실패: {error}")
        return

    filters = data.get("filters", {})
    patterns = data.get("patterns", {})
    if not isinstance(filters, dict) or not isinstance(patterns, dict):
        print("JSON 구조 오류: filters와 patterns는 객체여야 합니다.")
        return

    print("=== JSON 패턴별 분석 ===")
    passed = 0
    failed = []
    timings = {}
    for key, item in patterns.items():
        try:
            if not isinstance(item, dict):
                raise ValueError("패턴 데이터가 객체가 아닙니다.")
            pattern = item["input"]
            size = len(pattern)
            filter_a, filter_b = get_filter_pair(filters, size)
            validate_matrix(pattern, size, key)
            validate_matrix(filter_a, size, f"size_{size}.cross")
            validate_matrix(filter_b, size, f"size_{size}.x")
            expected_raw = item["expected"]
            expected = normalize_label(expected_raw)
            if expected is None:
                raise ValueError(f"알 수 없는 expected 값: {expected_raw}")
            score_a, score_b, prediction = predict(pattern, filter_a, filter_b)
            status = "PASS" if prediction == expected else "FAIL"
            if status == "PASS":
                passed += 1
            else:
                failed.append(f"{key}: 예상={expected}, 실제={prediction} (판정 불일치)")
            print(f"{key} | {size}x{size} | A={score_a:.6f} B={score_b:.6f} | 예상={expected} 실제={prediction} | {status}")
            if size not in timings:
                samples = []
                for _ in range(10):
                    start = time.perf_counter()
                    mac(pattern, filter_a)
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    samples.append(elapsed_ms)
                timings[size] = sum(samples) / len(samples)
        except (KeyError, TypeError, ValueError) as error:
            failed.append(f"{key}: 데이터 오류 - {error}")
            print(f"{key} | FAIL | 데이터 오류: {error}")

    print("=== MAC 성능 측정 (각 크기 10회 평균, MAC 함수만 측정) ===")
    for size in sorted(timings):
        print(f"{size}x{size} | 연산 횟수 {size * size} | 평균 {timings[size]:.6f} ms")
    print("시간 복잡도: O(N^2), N x N 배열의 모든 원소를 한 번씩 계산")
    print("=== 최종 요약 ===")
    print(f"전체: {len(patterns)}건 | PASS: {passed}건 | FAIL: {len(failed)}건")
    if failed:
        print("실패 목록:")
        for reason in failed:
            print("-", reason)
    else:
        print("실패 목록: 없음")


def main():
    print("=== Mini NPU Simulator ===")
    print("1. 사용자 입력 (3x3)")
    print("2. data.json 분석")
    mode = input("모드를 선택하세요 (1 또는 2): ").strip()
    if mode == "1":
        manual_mode()
    elif mode == "2":
        json_mode()
    else:
        print("입력 오류: 1 또는 2를 선택해주세요.")


if __name__ == "__main__":
    main()
