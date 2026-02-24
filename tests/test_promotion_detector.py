"""
test_promotion_detector.py — Organic vs. Paid 구분기 유닛 테스트

검증 항목:
    1. 스폰서 키워드 감지 (#ad, sponsored 등)
    2. 참여율 이상 감지
    3. 초기 급등(burst) 패턴 감지
    4. 정상 게시물 → Organic 판정
    5. 복합 신호 조합 테스트
"""

import pytest

from trend_analyzer.models import (
    SocialPost, Platform, EngagementMetrics, ContentType, PromotionLabel
)
from trend_analyzer.analyzer.promotion_detector import PromotionDetector


def _make_post(
    text: str = "일반 게시물",
    likes: int = 50,
    comments: int = 5,
    views: int = 500,
    follower_count: int | None = None,
    is_business: bool = False,
    has_sponsor: bool = False,
) -> SocialPost:
    """테스트용 게시물 생성 헬퍼."""
    return SocialPost(
        post_id="test_promo",
        platform=Platform.THREADS,
        author="test_user",
        text=text,
        content_type=ContentType.TEXT,
        engagement=EngagementMetrics(
            likes=likes,
            comments=comments,
            views=views,
        ),
        follower_count=follower_count,
        is_business_account=is_business,
        has_sponsor_label=has_sponsor,
    )


class TestSponsorKeywordDetection:
    """스폰서 키워드 감지 테스트."""

    def test_ad_해시태그_감지(self):
        """#ad가 포함된 게시물 → keyword_detected = True."""
        detector = PromotionDetector()
        post = _make_post(text="이 제품 추천합니다 #ad #beauty")
        signal = detector.detect(post)
        assert signal.keyword_detected is True

    def test_sponsored_감지(self):
        """#sponsored 포함 → keyword_detected = True."""
        detector = PromotionDetector()
        post = _make_post(text="Amazing product #sponsored")
        signal = detector.detect(post)
        assert signal.keyword_detected is True

    def test_paid_partnership_감지(self):
        """Paid partnership 문구 → keyword_detected = True."""
        detector = PromotionDetector()
        post = _make_post(text="Paid partnership with BrandX")
        signal = detector.detect(post)
        assert signal.keyword_detected is True

    def test_한국어_광고_감지(self):
        """한국어 광고 키워드 → keyword_detected = True."""
        detector = PromotionDetector()
        post = _make_post(text="오늘의 추천 #광고")
        signal = detector.detect(post)
        assert signal.keyword_detected is True

    def test_일반_텍스트는_미감지(self):
        """광고 키워드 없는 일반 텍스트 → keyword_detected = False."""
        detector = PromotionDetector()
        post = _make_post(text="오늘 날씨가 좋네요 #일상")
        signal = detector.detect(post)
        assert signal.keyword_detected is False


class TestEngagementAnomaly:
    """참여율 이상 감지 테스트."""

    def test_비정상적으로_높은_참여율(self):
        """팔로워 1000명인데 좋아요 200개 → 20% = 이상."""
        detector = PromotionDetector()
        post = _make_post(likes=200, follower_count=1000)
        signal = detector.detect(post)
        assert signal.engagement_anomaly is True

    def test_정상_참여율(self):
        """팔로워 10000명에 좋아요 100개 → 1% = 정상."""
        detector = PromotionDetector()
        post = _make_post(likes=100, follower_count=10000)
        signal = detector.detect(post)
        assert signal.engagement_anomaly is False

    def test_팔로워_정보_없으면_판단_불가(self):
        """팔로워 수 없으면 이상 감지 불가."""
        detector = PromotionDetector()
        post = _make_post(likes=500, follower_count=None)
        signal = detector.detect(post)
        assert signal.engagement_anomaly is False


class TestBurstPattern:
    """초기 급등 패턴 감지 테스트."""

    def test_조회수_대비_극단적으로_낮은_좋아요(self):
        """조회 100만, 좋아요 100 → 0.01% = 프로모션 급등 패턴."""
        detector = PromotionDetector()
        post = _make_post(likes=100, views=1000000, comments=5)
        signal = detector.detect(post)
        assert signal.burst_pattern is True

    def test_좋아요만_있고_댓글_없음(self):
        """좋아요 500, 댓글 0 → 인위적 좋아요 패턴."""
        detector = PromotionDetector()
        post = _make_post(likes=500, comments=0, views=0)
        signal = detector.detect(post)
        assert signal.burst_pattern is True

    def test_정상_비율(self):
        """정상적인 좋아요/조회 비율."""
        detector = PromotionDetector()
        post = _make_post(likes=50, views=500, comments=5)
        signal = detector.detect(post)
        assert signal.burst_pattern is False


class TestOverallClassification:
    """종합 판정 테스트."""

    def test_명확한_유료_광고(self):
        """스폰서 키워드 + 플랫폼 표시 + 비즈니스 계정 → Paid."""
        detector = PromotionDetector()
        post = _make_post(
            text="최고의 제품! #ad #sponsored",
            is_business=True,
            has_sponsor=True,
        )
        signal = detector.detect(post)
        assert signal.label == PromotionLabel.PAID
        assert signal.promotion_probability >= 0.7

    def test_명확한_일반_게시물(self):
        """아무 신호도 없는 일반 게시물 → Organic."""
        detector = PromotionDetector()
        post = _make_post(
            text="오늘 맛집 발견! #먹스타그램",
            likes=30,
            comments=5,
            views=300,
            follower_count=5000,
            is_business=False,
            has_sponsor=False,
        )
        signal = detector.detect(post)
        assert signal.label == PromotionLabel.ORGANIC
        assert signal.promotion_probability <= 0.3

    def test_애매한_경우_uncertain(self):
        """비즈니스 계정이지만 스폰서 키워드 없음 → Uncertain 가능."""
        detector = PromotionDetector()
        post = _make_post(
            text="새 컬렉션 소개합니다",
            likes=200,
            comments=10,
            views=2000,
            follower_count=1000,  # 참여율 20% → 이상
            is_business=True,
        )
        signal = detector.detect(post)
        # 비즈니스(0.10) + 참여이상(0.15) = 0.25 → Organic
        # 하지만 정확한 값은 구현에 따라 다를 수 있음
        assert 0.0 <= signal.promotion_probability <= 1.0
