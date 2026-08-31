#!/usr/bin/env python3
"""
헬스장 월간 출석률 안내 슬랙 봇

매 월 운영일(월~금) 수를 계산하고, 지원금 지급 기준인 출석률 40%를
달성하기 위해 필요한 최소 출석 일수를 슬랙 채널에 안내합니다.

사용법:
    python gym_attendance_bot.py                # 이번 달 기준, 슬랙 전송
    python gym_attendance_bot.py --dry-run       # 값 미리보기 (전송 안 함)
    python gym_attendance_bot.py --year 2026 --month 9   # 특정 연/월 지정
    python gym_attendance_bot.py --round floor    # 반올림 방식 변경 (기본: floor)

환경변수:
    SLACK_WEBHOOK_URL  - 슬랙 워크플로 빌더의 Webhook 트리거 URL (필수, --dry-run 시 불필요)

전송 방식 (중요):
    슬랙 워크플로에서 "8일" 같은 특정 숫자만 볼드 처리하려면, 완성된 문장 하나를
    변수로 보내는 대신 숫자를 각각 별도 변수로 나눠서 보내야 합니다. 슬랙 메시지
    편집창에서 이 변수를 직접 삽입하고, 그 부분만 선택해서 B(볼드) 버튼을 눌러야
    실제로 굵게 표시됩니다.

    이 스크립트는 아래 키들을 웹훅으로 전송합니다. 슬랙 워크플로의 웹훅 트리거에서
    동일한 이름의 변수(모두 텍스트 타입)를 만들어두세요:
        year            예: "2026"
        month           예: "8"
        required_days   예: "8"           (볼드 처리할 대상)
        weekday_count   예: "21"
        rate            예: "38.1"
        dday            예: "3"           (이번 달 마감까지 남은 일수, 0=오늘이 마감)
"""

import argparse
import calendar
import math
import os
import sys
from datetime import date

import requests

TARGET_RATE = 0.4  # 지원금 지급 기준 출석률 (40%)


def count_weekdays(year: int, month: int) -> int:
    """해당 연/월의 평일(월~금) 일수를 계산합니다."""
    cal = calendar.Calendar()
    weekday_count = 0
    for day_num, weekday in cal.itermonthdays2(year, month):
        if day_num == 0:  # 이전/다음 달로 채워진 빈 칸
            continue
        if weekday < 5:  # 0=월 ... 4=금, 5=토, 6=일
            weekday_count += 1
    return weekday_count


def required_attendance_days(weekday_count: int, mode: str = "floor", target_rate: float = TARGET_RATE) -> int:
    """
    40% 출석률 달성을 위한 최소 출석 일수를 계산합니다.

    mode="floor" : 40%에 가장 가깝게 내림 (예: 21일 -> 8.4 -> 8일)  [기본값, 회사 실측치와 일치]
    mode="round" : 사사오입 반올림
    mode="ceil"  : 반드시 40% '이상'을 보장 (올림)
    """
    raw = weekday_count * target_rate
    if mode == "floor":
        return math.floor(raw)
    if mode == "round":
        return round(raw)
    return math.ceil(raw)  # ceil


def days_until_month_end(year: int, month: int, today: date | None = None) -> int:
    """오늘부터 해당 연/월의 마지막 날까지 남은 일수 (0 이상, 이미 지난 달이면 0)."""
    if today is None:
        today = date.today()
    last_day = calendar.monthrange(year, month)[1]
    end_date = date(year, month, last_day)
    remaining = (end_date - today).days
    return max(remaining, 0)


def build_payload(year: int, month: int, mode: str = "floor") -> dict:
    """슬랙 워크플로 웹훅으로 보낼 변수 딕셔너리를 만듭니다."""
    weekday_count = count_weekdays(year, month)
    required_days = required_attendance_days(weekday_count, mode=mode)
    actual_rate = required_days / weekday_count * 100
    dday = days_until_month_end(year, month)

    return {
        "year": str(year),
        "month": str(month),
        "required_days": str(required_days),
        "weekday_count": str(weekday_count),
        "rate": f"{actual_rate:.1f}",
        "dday": str(dday),
    }


def preview_text(payload: dict) -> str:
    """--dry-run 확인용 미리보기 (실제 슬랙에서는 굵게 표시될 부분을 [ ]로 표시)"""
    return (
        f"🏋️ {payload['year']}년 {payload['month']}월 최소 출석일: "
        f"[{payload['required_days']}일 이상] (평일 {payload['weekday_count']}일 · {payload['rate']}%)\n"
        f"⚠️ 이 기준 미달성 시 이번 달 지원금이 지급되지 않습니다.\n"
        f"⏰ 이번 달 마감까지 D-{payload['dday']}"
    )


def send_to_slack(webhook_url: str, payload: dict) -> None:
    resp = requests.post(webhook_url, json=payload, timeout=10)
    resp.raise_for_status()


def main():
    today = date.today()
    parser = argparse.ArgumentParser(description="월간 헬스장 출석률 안내 슬랙 봇")
    parser.add_argument("--year", type=int, default=today.year, help="연도 (기본: 올해)")
    parser.add_argument("--month", type=int, default=today.month, help="월 (기본: 이번 달)")
    parser.add_argument(
        "--round",
        dest="mode",
        choices=["ceil", "floor", "round"],
        default="floor",
        help="기준일수 계산 시 반올림 방식 (기본: floor, 회사 실제 산정 방식과 일치 확인됨)",
    )
    parser.add_argument("--dry-run", action="store_true", help="슬랙 전송 없이 값만 콘솔에 출력")
    args = parser.parse_args()

    payload = build_payload(args.year, args.month, mode=args.mode)

    if args.dry_run:
        print("전송될 변수 값:")
        for k, v in payload.items():
            print(f"  {k} = {v}")
        print("\n미리보기 ([ ]는 슬랙에서 볼드 처리될 부분):")
        print(preview_text(payload))
        return

    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        print("[오류] 환경변수 SLACK_WEBHOOK_URL 이 설정되어 있지 않습니다.", file=sys.stderr)
        sys.exit(1)

    send_to_slack(webhook_url, payload)
    print("슬랙 메시지 전송 완료. 전송된 값:")
    for k, v in payload.items():
        print(f"  {k} = {v}")


if __name__ == "__main__":
    main()
