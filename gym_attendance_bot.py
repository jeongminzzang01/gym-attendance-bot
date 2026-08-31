#!/usr/bin/env python3
"""
헬스장 월간 출석률 안내 슬랙 봇

매 월 운영일(월~금) 수를 계산하고, 지원금 지급 기준인 출석률 40%를
달성하기 위해 필요한 최소 출석 일수를 슬랙 채널에 안내합니다.

사용법:
    python gym_attendance_bot.py                # 이번 달 기준, 슬랙 전송
    python gym_attendance_bot.py --dry-run       # 메시지만 출력 (전송 안 함)
    python gym_attendance_bot.py --year 2026 --month 9   # 특정 연/월 지정
    python gym_attendance_bot.py --round floor    # 반올림 방식 변경 (기본: floor)

환경변수:
    SLACK_WEBHOOK_URL  - 슬랙 워크플로 빌더의 Webhook 트리거 URL (필수, --dry-run 시 불필요)

참고:
    Slack 워크플로 빌더에서 Webhook 트리거를 만들 때 정의한 변수 키 이름이 "message"가
    아니라면 --webhook-key 옵션으로 맞춰주세요.
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

    mode="ceil"  : 반드시 40% '이상'을 보장 (예: 22일 -> 8.8 -> 9일)
    mode="floor" : 40%에 가장 가깝게 내림 (예: 22일 -> 8.8 -> 8일)  [기본값, 회사 실측치와 일치]
    mode="round" : 사사오입 반올림
    """
    raw = weekday_count * target_rate
    if mode == "floor":
        return math.floor(raw)
    if mode == "round":
        return round(raw)
    return math.ceil(raw)  # ceil


def build_message(year: int, month: int, mode: str = "floor") -> str:
    weekday_count = count_weekdays(year, month)
    required_days = required_attendance_days(weekday_count, mode=mode)
    actual_rate = required_days / weekday_count * 100

    message = (
        f"🏋️ {year}.{month} 최소 출석일: *{required_days}일 이상* "
        f"(평일 {weekday_count}일 · {actual_rate:.1f}%)"
    )
    return message


def send_to_slack(webhook_url: str, message: str, webhook_key: str = "message") -> None:
    """
    Slack 워크플로 빌더의 'Webhook' 트리거는 Incoming Webhook과 달리
    고정된 "text" 키가 아니라, 트리거 설정에서 직접 정의한 변수 키를 사용합니다.
    예: 트리거에서 키를 "message"로 설정했다면 -> {"message": "..."}
    """
    resp = requests.post(webhook_url, json={webhook_key: message}, timeout=10)
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
    parser.add_argument("--dry-run", action="store_true", help="슬랙 전송 없이 메시지만 콘솔에 출력")
    parser.add_argument(
        "--webhook-key",
        default="message",
        help="워크플로 빌더 웹훅 트리거에서 설정한 변수(키) 이름과 동일해야 함 (기본값: message)",
    )
    args = parser.parse_args()

    message = build_message(args.year, args.month, mode=args.mode)

    if args.dry_run:
        print(message)
        return

    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        print("[오류] 환경변수 SLACK_WEBHOOK_URL 이 설정되어 있지 않습니다.", file=sys.stderr)
        sys.exit(1)

    send_to_slack(webhook_url, message, webhook_key=args.webhook_key)
    print("슬랙 메시지 전송 완료:\n" + message)


if __name__ == "__main__":
    main()
