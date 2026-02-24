"""
threads_scraper.py — Threads API 스크래퍼

역할: Meta 공식 Threads API를 사용해 키워드 기반 게시물을 검색합니다.

API 엔드포인트:
    GET https://graph.threads.net/search
    - q: 검색 키워드
    - search_type: RECENT 또는 TOP
    - fields: id, text, timestamp, like_count, reply_count, repost_count, views
    - access_token: Meta 앱 액세스 토큰

필요 권한: threads_keyword_search (App Review 필수)
Rate Limit: 7일간 500쿼리 또는 24시간 2,200쿼리
"""

import logging
import re
from datetime import datetime
from typing import Optional

import requests

from trend_analyzer.config import settings
from trend_analyzer.models import (
    SocialPost, Platform, ContentType, EngagementMetrics
)
from trend_analyzer.scrapers.base import BaseScraper, DemoScraper

logger = logging.getLogger(__name__)

# Threads API 기본 URL
THREADS_API_BASE = "https://graph.threads.net"

# 검색 결과에서 가져올 필드 목록
THREADS_FIELDS = "id,text,timestamp,like_count,reply_count,repost_count,views,username,media_type"


class ThreadsScraper(BaseScraper):
    """
    Threads API를 통한 공개 게시물 검색 스크래퍼.

    사용 예시:
        scraper = ThreadsScraper(access_token="your_token")
        posts = scraper.search("AI", limit=30)
    """

    def __init__(self, access_token: Optional[str] = None):
        """
        Args:
            access_token: Meta API 토큰. None이면 settings에서 가져옴.
        """
        self._token = access_token or settings.meta_access_token
        # 세션 재사용으로 HTTP 커넥션 풀링 (성능 최적화)
        self._session = requests.Session()

    @property
    def platform_name(self) -> str:
        return "Threads"

    def search(self, topic: str, limit: int = 50) -> list[SocialPost]:
        """
        Threads에서 키워드로 최근 게시물을 검색합니다.

        Args:
            topic: 검색 키워드 (예: "AI", "패션 트렌드")
            limit: 최대 수집 수 (API 한계 내에서)

        Returns:
            SocialPost 리스트

        Raises:
            requests.HTTPError: API 응답 에러 (401, 429 등)
        """
        if not self._token:
            logger.warning("Threads API 토큰 없음 — Demo 모드로 전환")
            return DemoScraper(Platform.THREADS).search(topic, limit)

        try:
            posts = self._fetch_search_results(topic, limit)
            logger.info(f"Threads에서 '{topic}' 관련 {len(posts)}건 수집 완료")
            return posts
        except requests.HTTPError as e:
            logger.error(f"Threads API 에러: {e}")
            # API 에러 시 빈 리스트 반환 (앱 전체가 죽지 않도록)
            return []
        except requests.ConnectionError:
            logger.error("Threads API 연결 실패 — 네트워크 확인 필요")
            return []

    def _fetch_search_results(self, topic: str, limit: int) -> list[SocialPost]:
        """
        실제 API 호출을 수행하고 응답을 파싱합니다.

        왜 별도 메서드로 분리했나요?
        → search()에서 에러 핸들링을 깔끔하게 하기 위해
        """
        params = {
            "q": topic,
            "search_type": "RECENT",
            "fields": THREADS_FIELDS,
            "limit": min(limit, 100),  # API 한계 제한
            "access_token": self._token,
        }

        response = self._session.get(
            f"{THREADS_API_BASE}/search",
            params=params,
            timeout=30,  # 30초 타임아웃
        )
        # HTTP 에러 시 예외 발생 (4xx, 5xx)
        response.raise_for_status()

        data = response.json()
        results = data.get("data", [])

        return [self._parse_post(item) for item in results[:limit]]

    def _parse_post(self, raw: dict) -> SocialPost:
        """
        Threads API 응답 데이터를 SocialPost 모델로 변환합니다.

        API 응답 필드 → SocialPost 필드 매핑:
        - id → post_id
        - text → text
        - like_count → engagement.likes
        - reply_count → engagement.comments
        - repost_count → engagement.reposts
        - views → engagement.views
        """
        # 텍스트에서 해시태그 추출
        text = raw.get("text", "")
        hashtags = re.findall(r"#(\w+)", text)

        # 미디어 타입 매핑
        media_type_map = {
            "TEXT_POST": ContentType.TEXT,
            "IMAGE": ContentType.IMAGE,
            "VIDEO": ContentType.VIDEO,
        }
        content_type = media_type_map.get(
            raw.get("media_type", "TEXT_POST"),
            ContentType.TEXT
        )

        # 스폰서 키워드 감지 (광고 구분용)
        sponsor_keywords = ["#ad", "#sponsored", "paid partnership", "스폰서", "광고"]
        has_sponsor = any(kw in text.lower() for kw in sponsor_keywords)

        # 타임스탬프 파싱 — ISO 형식 또는 폴백
        try:
            created_at = datetime.fromisoformat(
                raw.get("timestamp", "").replace("Z", "+00:00")
            )
        except (ValueError, AttributeError):
            created_at = datetime.now()

        return SocialPost(
            post_id=str(raw.get("id", "")),
            platform=Platform.THREADS,
            author=raw.get("username", "unknown"),
            text=text,
            content_type=content_type,
            engagement=EngagementMetrics(
                likes=raw.get("like_count", 0),
                comments=raw.get("reply_count", 0),
                reposts=raw.get("repost_count", 0),
                views=raw.get("views", 0),
            ),
            created_at=created_at,
            hashtags=hashtags,
            has_sponsor_label=has_sponsor,
        )
