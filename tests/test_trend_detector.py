"""
test_trend_detector.py — 트렌드 감지 엔진 유닛 테스트

검증 항목:
    1. Velocity Score 계산 정확성
    2. Volume Threshold 필터링
    3. Cross-Platform Amplification 부스트
    4. 종합 Trend Score 합산
    5. 빈 데이터 처리
"""

from datetime import datetime, timedelta

import pytest

from trend_analyzer.models import (
    SocialPost, Platform, EngagementMetrics, ContentType
)
from trend_analyzer.analyzer.trend_detector import TrendDetector


def _make_post(
    platform: Platform = Platform.THREADS,
    likes: int = 100,
    comments: int = 10,
    views: int = 1000,
    hours_ago: float = 1.0,
    text: str = "테스트 게시물",
) -> SocialPost:
    """테스트용 게시물 생성 헬퍼."""
    return SocialPost(
        post_id=f"test_{platform.value}_{likes}",
        platform=platform,
        author="test_user",
        text=text,
        content_type=ContentType.TEXT,
        engagement=EngagementMetrics(
            likes=likes,
            comments=comments,
            views=views,
        ),
        created_at=datetime.now() - timedelta(hours=hours_ago),
    )


class TestVelocityScore:
    """Velocity Score 계산 테스트."""

    def test_높은_참여_최신_게시물은_높은_velocity(self):
        """최근에 작성되고 참여도 높은 게시물은 높은 velocity 점수를 받아야 함."""
        detector = TrendDetector(velocity_window_hours=6)
        posts = [
            _make_post(likes=5000, comments=500, views=50000, hours_ago=0.5),
            _make_post(likes=3000, comments=300, views=30000, hours_ago=1.0),
        ]
        result = detector.analyze("test", posts)
        assert result.velocity_score > 50, "높은 참여 + 최신 게시물 → velocity ≥ 50"

    def test_오래된_게시물은_낮은_velocity(self):
        """오래된 게시물만 있으면 velocity가 낮아야 함."""
        detector = TrendDetector(velocity_window_hours=6)
        posts = [
            _make_post(likes=100, comments=5, views=500, hours_ago=20),
            _make_post(likes=80, comments=3, views=400, hours_ago=22),
        ]
        result = detector.analyze("test", posts)
        assert result.velocity_score < 50, "오래된 게시물 → velocity < 50"

    def test_빈_게시물_리스트(self):
        """게시물이 없으면 velocity는 0."""
        detector = TrendDetector()
        result = detector.analyze("test", [])
        assert result.velocity_score == 0.0


class TestVolumeScore:
    """Volume Score 계산 테스트."""

    def test_임계값_이상이면_만점(self):
        """게시물 수가 임계값 이상이면 volume 100점."""
        detector = TrendDetector(volume_threshold=5)
        posts = [_make_post() for _ in range(10)]
        result = detector.analyze("test", posts)
        assert result.volume_score == 100.0

    def test_임계값_미달이면_비례_점수(self):
        """게시물 수가 임계값 미달이면 비례 점수."""
        detector = TrendDetector(volume_threshold=10)
        posts = [_make_post() for _ in range(5)]
        result = detector.analyze("test", posts)
        # 5/10 = 0.5 → 50점
        assert result.volume_score == 50.0

    def test_게시물_없으면_0점(self):
        """게시물이 없으면 volume 0점."""
        detector = TrendDetector(volume_threshold=10)
        result = detector.analyze("test", [])
        assert result.volume_score == 0.0


class TestCrossPlatformAmplification:
    """Cross-Platform Amplification 테스트."""

    def test_양_플랫폼이면_부스트_적용(self):
        """Threads + Instagram 모두 있으면 크로스 플랫폼 부스트."""
        detector = TrendDetector(cross_platform_boost=1.5)
        posts = [
            _make_post(platform=Platform.THREADS, likes=500, views=5000),
            _make_post(platform=Platform.INSTAGRAM, likes=500, views=5000),
        ]
        result = detector.analyze("test", posts)
        assert result.is_cross_platform is True
        # 부스트 적용 확인: 단일 플랫폼 결과와 비교
        single_posts = [
            _make_post(platform=Platform.THREADS, likes=500, views=5000),
            _make_post(platform=Platform.THREADS, likes=500, views=5000),
        ]
        single_result = detector.analyze("test", single_posts)
        assert result.amplification_score >= single_result.amplification_score

    def test_단일_플랫폼이면_부스트_없음(self):
        """한 플랫폼만 있으면 크로스 플랫폼 아님."""
        detector = TrendDetector()
        posts = [
            _make_post(platform=Platform.THREADS),
            _make_post(platform=Platform.THREADS),
        ]
        result = detector.analyze("test", posts)
        assert result.is_cross_platform is False


class TestTrendScore:
    """종합 Trend Score 테스트."""

    def test_점수_범위_0_to_100(self):
        """종합 점수는 항상 0~100 범위."""
        detector = TrendDetector()
        posts = [
            _make_post(platform=Platform.THREADS, likes=10000, views=100000, hours_ago=0.5),
            _make_post(platform=Platform.INSTAGRAM, likes=8000, views=80000, hours_ago=1.0),
        ]
        result = detector.analyze("test", posts)
        assert 0.0 <= result.trend_score <= 100.0

    def test_트렌드_레벨_매핑(self):
        """점수에 따라 올바른 트렌드 레벨이 반환되어야 함."""
        detector = TrendDetector(volume_threshold=1, velocity_window_hours=6)
        # 높은 참여 게시물로 높은 점수 유도
        posts = [
            _make_post(platform=Platform.THREADS, likes=50000, comments=5000, views=500000, hours_ago=0.5),
            _make_post(platform=Platform.INSTAGRAM, likes=40000, comments=4000, views=400000, hours_ago=0.5),
        ]
        result = detector.analyze("test", posts)
        # 높은 점수 → "🔥 HOT TREND" 또는 "⚡ TRENDING"
        assert "TREND" in result.trend_level or "RISING" in result.trend_level

    def test_빈_데이터는_기본값_반환(self):
        """빈 게시물 → 모든 점수 0, NO TREND."""
        detector = TrendDetector()
        result = detector.analyze("empty", [])
        assert result.trend_score == 0.0
        assert result.total_posts == 0
        assert "NO TREND" in result.trend_level
