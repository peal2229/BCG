"""
FIPO 산업단지 리스트 크롤러
URL: https://www.fipo.or.jp/industrialestate

추출 항목:
  - Name (산업단지명)
  - Maintenance Status (정비 상황)
  - Usage Status / Planned Start Date (이용 상황 / 예정 개시일)
  - Recruitment Status / Scheduled Start Date (모집 상황 / 예정 개시일)
  - Recruitment Plots/Area (모집 구획 / 면적)

실행 방법:
  pip install requests beautifulsoup4 pandas selenium webdriver-manager
  python crawl_fipo.py
"""

import time
import pandas as pd
import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# 방법 1: requests + BeautifulSoup (JavaScript 렌더링 불필요한 경우)
# ---------------------------------------------------------------------------

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en;q=0.9",
    "Referer": "https://www.fipo.or.jp/",
}

BASE_URL = "https://www.fipo.or.jp/industrialestate"


def _parse_table(soup: BeautifulSoup) -> list[dict]:
    """테이블에서 산업단지 데이터를 파싱합니다."""
    records = []

    # 페이지 내 모든 <table> 탐색
    tables = soup.find_all("table")
    if not tables:
        print("[WARN] 테이블을 찾지 못했습니다. 페이지 구조를 확인하세요.")
        return records

    for table in tables:
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        # 헤더 행 파싱
        header_cells = rows[0].find_all(["th", "td"])
        headers = [c.get_text(strip=True) for c in header_cells]

        # 원하는 컬럼이 포함된 테이블인지 확인 (Name 컬럼이 있는지 체크)
        has_name_col = any(
            kw in h for h in headers for kw in ["Name", "名称", "団地名", "工業団地"]
        )
        if not has_name_col and len(headers) < 3:
            continue

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if not cells:
                continue

            # 셀 텍스트 추출 (줄바꿈은 " / "로 구분)
            values = [c.get_text(separator=" / ", strip=True) for c in cells]

            # 헤더와 값을 매핑; 컬럼 수가 다를 경우 인덱스로 접근
            if len(headers) == len(values):
                row_dict = dict(zip(headers, values))
            else:
                row_dict = {f"col_{i}": v for i, v in enumerate(values)}

            records.append(row_dict)

        if records:
            print(f"[INFO] 테이블 파싱 완료: {len(records)}건")
            break  # 첫 번째 유효 테이블만 처리

    return records


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """컬럼명을 영문 표준 이름으로 정규화합니다."""
    rename_map = {}
    for col in df.columns:
        cl = col.lower()
        if any(k in cl for k in ["name", "名称", "団地名"]):
            rename_map[col] = "Name"
        elif any(k in cl for k in ["maintenance", "整備", "整備状況"]):
            rename_map[col] = "Maintenance Status"
        elif any(k in cl for k in ["usage", "利用", "利用状況"]):
            rename_map[col] = "Usage Status (Planned Start Date)"
        elif any(k in cl for k in ["recruit", "募集", "募集状況"]):
            rename_map[col] = "Recruitment Status (Scheduled Start Date)"
        elif any(k in cl for k in ["plot", "area", "区画", "面積"]):
            rename_map[col] = "Recruitment Plots/Area"
    return df.rename(columns=rename_map)


def crawl_with_requests() -> pd.DataFrame | None:
    """requests를 이용한 크롤링 (정적 HTML 대응)."""
    print(f"[INFO] requests로 {BASE_URL} 접속 중...")
    try:
        session = requests.Session()
        session.headers.update(HEADERS)

        resp = session.get(BASE_URL, timeout=30)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding

        soup = BeautifulSoup(resp.text, "html.parser")
        records = _parse_table(soup)

        if not records:
            print("[WARN] 데이터를 추출하지 못했습니다. Selenium 방법을 시도하세요.")
            return None

        df = pd.DataFrame(records)
        df = _normalize_columns(df)
        return df

    except requests.HTTPError as e:
        print(f"[ERROR] HTTP 오류: {e}")
        return None
    except Exception as e:
        print(f"[ERROR] requests 크롤링 실패: {e}")
        return None


# ---------------------------------------------------------------------------
# 방법 2: Selenium (JavaScript 렌더링이 필요한 경우)
# ---------------------------------------------------------------------------

def crawl_with_selenium() -> pd.DataFrame | None:
    """Selenium을 이용한 크롤링 (동적 JS 렌더링 대응)."""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError:
        print("[ERROR] selenium 또는 webdriver-manager가 설치되지 않았습니다.")
        print("  pip install selenium webdriver-manager")
        return None

    print(f"[INFO] Selenium으로 {BASE_URL} 접속 중...")
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"user-agent={HEADERS['User-Agent']}")

    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.get(BASE_URL)

        # 테이블 로딩 대기 (최대 15초)
        wait = WebDriverWait(driver, 15)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "table")))
        time.sleep(2)  # 추가 렌더링 대기

        soup = BeautifulSoup(driver.page_source, "html.parser")
        records = _parse_table(soup)

        if not records:
            print("[WARN] Selenium으로도 데이터를 추출하지 못했습니다.")
            # 페이지 소스를 파일로 저장해 구조 확인
            with open("page_source.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            print("[INFO] page_source.html 파일에 페이지 소스를 저장했습니다.")
            return None

        df = pd.DataFrame(records)
        df = _normalize_columns(df)
        return df

    except Exception as e:
        print(f"[ERROR] Selenium 크롤링 실패: {e}")
        return None
    finally:
        if driver:
            driver.quit()


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

def main():
    # 1차: requests 시도
    df = crawl_with_requests()

    # 2차: Selenium 폴백
    if df is None or df.empty:
        print("[INFO] Selenium으로 재시도합니다...")
        df = crawl_with_selenium()

    if df is None or df.empty:
        print("[ERROR] 크롤링 실패: 데이터를 가져오지 못했습니다.")
        return

    # 원하는 컬럼만 추출 (존재하는 것만)
    target_cols = [
        "Name",
        "Maintenance Status",
        "Usage Status (Planned Start Date)",
        "Recruitment Status (Scheduled Start Date)",
        "Recruitment Plots/Area",
    ]
    available_cols = [c for c in target_cols if c in df.columns]
    df_out = df[available_cols] if available_cols else df

    # 결과 출력
    print("\n===== 크롤링 결과 =====")
    print(df_out.to_string(index=False))

    # CSV 저장
    output_path = "fipo_industrial_estates.csv"
    df_out.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\n[INFO] CSV 저장 완료: {output_path}")


if __name__ == "__main__":
    main()
