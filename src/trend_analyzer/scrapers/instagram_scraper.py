"""
instagram_scraper.py — Instagram Graph API 스크래퍼

역할: Meta 공식 Instagram Graph API를 사용해 해시태그 기반 게시물을 검색합니다.

API 흐름 (2단계):
    1. GET /ig_hashtag_search?q={topic} → hashtag_id 획득
    2. GET /{hashtag_id}/recent_media?fields=... → 최근 미디어 조회

필요 권한:
    - instagram_basic
    - Instagram Public Content Access (App Review 필수)

제한사항:
    - 7일간 고유 해시태그 30개까지 검색 가능
    - 최근 24시간 이내 미디어만 반환
    - 페이지당 50건, 최대 250건
    - Promoted/boosted 미디어는 반환되지 않음 (→ 오히려 Organic 필터에 유리)
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

# Instagram Graph API 기본 URL
IG_API_BASE = "https://graph.facebook.com/v21.0"

# recent_media 엔드포인트에서 가져올 필드
IG_MEDIA_FIELDS = "id,caption,timestamp,like_count,comments_count,media_type,permalink"


class InstagramScraper(BaseScraper):
    """
    Instagram Graph API를 통한 해시태그 기반 게시물 검색 스크래퍼.

    주의: Instagram Graph API는 '해시태그' 검색만 지원합니다.
    자유 키워드 검색(예: "AI trends")은 불가 → 토픽을 해시태그로 변환하여 검색합니다.

    사용 예시:
        scraper = InstagramScraper(
            access_token="your_token",
            business_account_id="123456"
        )
        posts = scraper.search("AI", limit=30)
    """

    def __init__(
        self,
        access_token: Optional[str] = None,
        business_account_id: Optional[str] = None,
    ):
        """
        Args:
            access_token: Meta API 토큰
            business_account_id: Instagram 비즈니스 계정 ID (해시태그 검색에 필수)
        """
        self._token = access_token or settings.meta_access_token
        self._account_id = business_account_id or settings.instagram_business_account_id
        self._session = requests.Session()

    @property
    def platform_name(self) -> str:
        return "Instagram"

    def search(self, topic: str, limit: int = 50) -> list[SocialPost]:
        """
        Instagram에서 해시태그로 최근 게시물을 검색합니다.

        Args:
            topic: 검색 키워드 → 자동으로 해시태그 형식으로 변환
            limit: 최대 수집 수 (API 한계: 250)

        Returns:
            SocialPost 리스트
        """
        if not self._token or not self._account_id:
            logger.warning("Instagram API 토큰/계정ID 없음 — Demo 모드로 전환")
            return DemoScraper(Platform.INSTAGRAM).search(topic, limit)

        try:
            # Step 1: 토픽 → 해시태그 ID 변환
            hashtag_id = self._get_hashtag_id(topic)
            if not hashtag_id:
                logger.warning(f"'{topic}' 해시태그를 찾을 수 없음")
                return []

            # Step 2: 해시태그 ID로 최근 미디어 조회
            posts = self._get_recent_media(hashtag_id, limit)
            logger.info(f"Instagram에서 '#{topic}' 관련 {len(posts)}건 수집 완료")
            return posts
        except requests.HTTPError as e:
            # 429: Rate limit 초과, 400: 잘못된 요청 등
            logger.error(f"Instagram API 에러: {e}")
            return []
        except requests.ConnectionError:
            logger.error("Instagram API 연결 실패 — 네트워크 확인 필요")
            return []

    def _get_hashtag_id(self, topic: str) -> Optional[str]:
        """
        토픽 키워드를 Instagram 해시태그 ID로 변환합니다.

        왜 이 단계가 필요한가요?
        → Instagram API는 해시태그를 ID(숫자)로만 인식합니다.
          먼저 이름 → ID 매핑을 조회해야 합니다.
        """
        # 공백/특수문자 제거하여 해시태그 형식으로 변환
        # 예: "AI trends" → "aitrends"
        clean_topic = re.sub(r"[^a-zA-Z0-9가-힣]", "", topic).lower()

        params = {
            "q": clean_topic,
            "user_id": self._account_id,
            "access_token": self._token,
        }

        response = self._session.get(
            f"{IG_API_BASE}/ig_hashtag_search",
            params=params,
            timeout=30,
        )
        response.raise_for_status()

        data = response.json().get("data", [])
        if not data:
            return None

        # 첫 번째 결과의 ID 반환
        return data[0].get("id")

    def _get_recent_media(self, hashtag_id: str, limit: int) -> list[SocialPost]:
        """
        해시태그 ID로 최근 24시간 내 미디어를 조회합니다.

        참고: Instagram API는 최대 250건의 최근 미디어를 반환합니다.
        Promoted/boosted 콘텐츠는 API 응답에서 자동 제외됩니다.
        """
        params = {
            "user_id": self._account_id,
            "fields": IG_MEDIA_FIELDS,
            "limit": min(limit, 50),  # 페이지당 최대 50건
            "access_token": self._token,
        }

        all_posts: list[SocialPost] = []

        # 페이지네이션: 원하는 수량만큼 수집
        url = f"{IG_API_BASE}/{hashtag_id}/recent_media"
        while url and len(all_posts) < limit:
            response = self._session.get(url, params=params, timeout=30)
            response.raise_for_status()

            result = response.json()
            media_items = result.get("data", [])

            for item in media_items:
                if len(all_posts) >= limit:
                    break
                all_posts.append(self._parse_media(item))

            # 다음 페이지 URL (없으면 None → 루프 종료)
            url = result.get("paging", {}).get("next")
            # 다음 페이지 요청 시에는 params 불필요 (URL에 포함됨)
            params = {}

        return all_posts

    def _parse_media(self, raw: dict) -> SocialPost:
        """
        Instagram Graph API 응답 데이터를 SocialPost 모델로 변환합니다.

        API 응답 필드 → SocialPost 필드 매핑:
        - id → post_id
        - caption → text
        - like_count → engagement.likes
        - comments_count → engagement.comments
        - media_type → content_type
        - permalink → url
        """
        caption = raw.get("caption", "")
        hashtags = re.findall(r"#(\w+)", caption)

        # 미디어 타입 매핑
        media_type_map = {
            "IMAGE": ContentType.IMAGE,
            "VIDEO": ContentType.VIDEO,
            "CAROUSEL_ALBUM": ContentType.CAROUSEL,
        }
        content_type = media_type_map.get(
            raw.get("media_type", "IMAGE"),
            ContentType.IMAGE
        )

        # 스폰서 키워드 감지
        sponsor_keywords = ["#ad", "#sponsored", "paid partnership", "스폰서", "광고"]
        has_sponsor = any(kw in caption.lower() for kw in sponsor_keywords)

        # 타임스탬프 파싱
        try:
            created_at = datetime.fromisoformat(
                raw.get("timestamp", "").replace("Z", "+00:00")
            )
        except (ValueError, AttributeError):
            created_at = datetime.now()

        return SocialPost(
            post_id=str(raw.get("id", "")),
            platform=Platform.INSTAGRAM,
            author="unknown",  # Instagram 해시태그 검색에서는 작성자 정보 제한적
            text=caption,
            content_type=content_type,
            engagement=EngagementMetrics(
                likes=raw.get("like_count", 0),
                comments=raw.get("comments_count", 0),
            ),
            created_at=created_at,
            hashtags=hashtags,
            url=raw.get("permalink", ""),
            has_sponsor_label=has_sponsor,
        )
