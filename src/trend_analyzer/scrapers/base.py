"""
base.py — 스크래퍼 추상 클래스 및 Demo 스크래퍼

역할:
- BaseScraper: 모든 플랫폼 스크래퍼가 상속하는 인터페이스
- DemoScraper: API 토큰 없이 테스트할 수 있는 샘플 데이터 생성기

왜 추상 클래스를 쓰나요?
→ Threads와 Instagram 스크래퍼가 같은 인터페이스를 갖도록 강제합니다.
  나중에 TikTok, X 등을 추가할 때도 같은 패턴으로 확장할 수 있습니다.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
import random

from trend_analyzer.models import (
    SocialPost, Platform, ContentType, EngagementMetrics
)


class BaseScraper(ABC):
    """
    스크래퍼 추상 클래스.
    모든 플랫폼 스크래퍼는 이 클래스를 상속하고 search()를 구현해야 합니다.
    """

    @abstractmethod
    def search(self, topic: str, limit: int = 50) -> list[SocialPost]:
        """
        주어진 토픽으로 게시물을 검색합니다.

        Args:
            topic: 검색할 키워드/해시태그
            limit: 최대 수집 게시물 수

        Returns:
            수집된 게시물 리스트
        """
        pass

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """스크래퍼가 담당하는 플랫폼 이름."""
        pass


class DemoScraper(BaseScraper):
    """
    Demo 모드용 가짜 데이터 생성기.
    API 토큰 없이도 앱의 트렌드 감지 로직을 테스트할 수 있습니다.

    왜 필요한가요?
    → Meta API App Review 승인 전에도 개발/테스트를 진행하기 위해
    """

    def __init__(self, platform: Platform):
        self._platform = platform

    @property
    def platform_name(self) -> str:
        return f"Demo ({self._platform.value})"

    def search(self, topic: str, limit: int = 50) -> list[SocialPost]:
        """
        리얼한 샘플 데이터를 생성합니다.
        트렌딩 패턴(참여도 높은 게시물)과 일반 게시물을 섞어서 반환합니다.
        """
        posts: list[SocialPost] = []
        now = datetime.now()

        # 샘플 작성자 이름
        demo_authors = [
            "tech_insider", "daily_digest", "trend_watcher",
            "creator_studio", "brand_official", "news_hub",
            "lifestyle_mag", "data_nerd", "social_buzz", "casual_user"
        ]

        for i in range(min(limit, 50)):
            # 일부 게시물은 트렌딩 패턴 (높은 참여도)
            is_trending = random.random() < 0.3
            # 일부 게시물은 프로모션 패턴
            is_promoted = random.random() < 0.2

            # 참여도: 트렌딩이면 높게, 일반이면 낮게
            base_likes = random.randint(500, 10000) if is_trending else random.randint(5, 200)
            base_comments = int(base_likes * random.uniform(0.02, 0.15))
            base_views = base_likes * random.randint(5, 20)

            # 프로모션 게시물은 특유의 패턴 부여
            text_content = f"{topic}에 대한 생각을 공유합니다 #{topic.replace(' ', '')}"
            if is_promoted:
                sponsored_tags = ["#ad", "#sponsored", "Paid partnership"]
                text_content += f" {random.choice(sponsored_tags)}"

            post = SocialPost(
                post_id=f"demo_{self._platform.value}_{i:04d}",
                platform=self._platform,
                author=random.choice(demo_authors),
                text=text_content,
                content_type=random.choice(list(ContentType)),
                engagement=EngagementMetrics(
                    likes=base_likes,
                    comments=base_comments,
                    shares=random.randint(0, base_likes // 5),
                    views=base_views,
                    reposts=random.randint(0, base_likes // 10)
                    if self._platform == Platform.THREADS else 0,
                ),
                # 시간을 분산시켜 velocity 계산이 의미 있도록
                created_at=now - timedelta(
                    hours=random.uniform(0, 24),
                    minutes=random.randint(0, 59)
                ),
                hashtags=[f"#{topic.replace(' ', '')}", f"#trending"],
                is_business_account=is_promoted and random.random() < 0.7,
                has_sponsor_label=is_promoted and random.random() < 0.5,
                follower_count=random.randint(1000, 500000) if is_promoted else random.randint(100, 50000),
            )
            posts.append(post)

        return posts
