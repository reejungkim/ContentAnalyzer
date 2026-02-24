"""
trend_detector.py — 트렌드 감지 엔진 (핵심 알고리즘)

역할: 수집된 게시물 데이터를 분석하여 트렌딩 여부를 판정합니다.

트렌드 감지 3대 지표:
    1. Velocity Score   — 참여(engagement) 증가 속도 (40%)
    2. Volume Score     — 게시물 수량 충족 여부 (30%)
    3. Amplification    — 크로스 플랫폼 확산 정도 (30%)

최종 점수: trend_score = velocity×0.4 + volume×0.3 + amplification×0.3
"""

import math
from datetime import datetime, timedelta
from typing import Optional

from trend_analyzer.config import settings
from trend_analyzer.models import (
    SocialPost, Platform, TrendResult, PromotionLabel
)
from trend_analyzer.analyzer.promotion_detector import PromotionDetector


class TrendDetector:
    """
    트렌드 감지 엔진.

    게시물 리스트를 받아 velocity, volume, amplification을 계산하고
    종합 트렌드 점수(0~100)를 산출합니다.

    사용 예시:
        detector = TrendDetector()
        result = detector.analyze("AI", all_posts)
        print(result.trend_score)
    """

    def __init__(
        self,
        velocity_window_hours: Optional[int] = None,
        volume_threshold: Optional[int] = None,
        cross_platform_boost: Optional[float] = None,
    ):
        """
        Args:
            velocity_window_hours: Velocity 계산 시간 창 (기본: 설정값)
            volume_threshold: 최소 볼륨 기준 (기본: 설정값)
            cross_platform_boost: 크로스 플랫폼 부스트 배율 (기본: 설정값)
        """
        self.velocity_window = velocity_window_hours or settings.trend_velocity_window_hours
        self.volume_threshold = volume_threshold or settings.trend_volume_threshold
        self.boost = cross_platform_boost or settings.cross_platform_boost
        self._promo_detector = PromotionDetector()

    def analyze(self, topic: str, posts: list[SocialPost]) -> TrendResult:
        """
        주어진 토픽의 게시물을 종합 분석합니다.

        Args:
            topic: 분석 중인 토픽/키워드
            posts: 수집된 전체 게시물 리스트 (Threads + Instagram 혼합)

        Returns:
            TrendResult 모델 (점수, 판정, 세부 정보 포함)
        """
        if not posts:
            return TrendResult(topic=topic)

        # --- 플랫폼별 분리 ---
        threads_posts = [p for p in posts if p.platform == Platform.THREADS]
        ig_posts = [p for p in posts if p.platform == Platform.INSTAGRAM]

        # --- 1. Velocity Score 계산 ---
        velocity = self._calculate_velocity(posts)

        # --- 2. Volume Score 계산 ---
        volume = self._calculate_volume(len(posts))

        # --- 3. Cross-Platform Amplification 계산 ---
        is_cross = bool(threads_posts) and bool(ig_posts)
        amplification = self._calculate_amplification(posts, is_cross)

        # --- 최종 트렌드 점수 (가중 합산) ---
        trend_score = (velocity * 0.4) + (volume * 0.3) + (amplification * 0.3)
        # 0~100 범위 클리핑
        trend_score = max(0.0, min(100.0, trend_score))

        # --- Organic / Paid 분석 ---
        promo_results = self._analyze_promotions(posts)
        organic_count = sum(1 for r in promo_results if r == PromotionLabel.ORGANIC)
        paid_count = sum(1 for r in promo_results if r == PromotionLabel.PAID)
        uncertain_count = sum(1 for r in promo_results if r == PromotionLabel.UNCERTAIN)

        # 주된 판정: 과반수 기준
        total = len(posts)
        if paid_count > total * 0.5:
            dominant_label = PromotionLabel.PAID
        elif organic_count > total * 0.5:
            dominant_label = PromotionLabel.ORGANIC
        else:
            dominant_label = PromotionLabel.UNCERTAIN

        organic_ratio = organic_count / total if total > 0 else 1.0

        # --- 상위 참여 게시물 선정 (최대 5개) ---
        top_posts = sorted(
            posts,
            key=lambda p: p.engagement.total_engagement,
            reverse=True
        )[:5]

        return TrendResult(
            topic=topic,
            velocity_score=round(velocity, 1),
            volume_score=round(volume, 1),
            amplification_score=round(amplification, 1),
            trend_score=round(trend_score, 1),
            total_posts=total,
            threads_count=len(threads_posts),
            instagram_count=len(ig_posts),
            is_cross_platform=is_cross,
            organic_count=organic_count,
            paid_count=paid_count,
            uncertain_count=uncertain_count,
            dominant_promotion_label=dominant_label,
            organic_ratio=round(organic_ratio, 2),
            top_posts=top_posts,
        )

    def _calculate_velocity(self, posts: list[SocialPost]) -> float:
        """
        Velocity Score (0~100) 계산.

        원리:
        - 시간 윈도우 내에서 각 게시물의 '시간당 참여도'를 계산
        - 최신 게시물일수록 높은 가중치 부여 (지수 감쇠)
        - 전체를 평균 내고 로그 정규화

        왜 지수 감쇠(exponential decay)?
        → 1시간 전 게시물이 12시간 전 게시물보다 트렌드 판단에 더 중요하기 때문
        """
        if not posts:
            return 0.0

        now = datetime.now()
        window_start = now - timedelta(hours=self.velocity_window)

        weighted_velocities: list[float] = []

        for post in posts:
            # 게시물 나이 (시간)
            # created_at이 timezone-aware일 수 있으므로 naive로 변환
            created = post.created_at.replace(tzinfo=None)
            age_hours = max((now - created).total_seconds() / 3600, 0.1)

            # 시간 윈도우 밖의 게시물도 약하게 기여
            if created < window_start:
                time_weight = 0.1  # 윈도우 밖: 낮은 가중치
            else:
                # 지수 감쇠: 최신일수록 가중치 ≈ 1.0
                time_weight = math.exp(-0.3 * age_hours)

            # 시간당 참여도
            engagement_per_hour = post.engagement.total_engagement / age_hours
            weighted_velocities.append(engagement_per_hour * time_weight)

        if not weighted_velocities:
            return 0.0

        # 평균 가중 velocity
        avg_velocity = sum(weighted_velocities) / len(weighted_velocities)

        # 로그 스케일 정규화 (0~100)
        # log(1 + x)로 극단값 완화, 1000을 기준점으로 100점 매핑
        score = min(100.0, (math.log1p(avg_velocity) / math.log1p(1000)) * 100)

        return score

    def _calculate_volume(self, post_count: int) -> float:
        """
        Volume Score (0~100) 계산.

        실제 게시물 수 / 임계값 비율로 점수를 산출합니다.
        임계값 이상이면 100점, 미만이면 비례 점수.
        """
        if self.volume_threshold <= 0:
            return 100.0 if post_count > 0 else 0.0

        ratio = post_count / self.volume_threshold
        return min(100.0, ratio * 100)

    def _calculate_amplification(
        self,
        posts: list[SocialPost],
        is_cross_platform: bool
    ) -> float:
        """
        Cross-Platform Amplification Score (0~100) 계산.

        원리:
        - 기본 점수: 전체 참여도의 로그 정규화
        - 크로스 플랫폼이면: 부스트 배율 적용
        - 단일 플랫폼이면: 부스트 없음

        왜 크로스 플랫폼이 중요한가요?
        → 같은 토픽이 여러 플랫폼에서 동시에 뜨면
          진짜 사회적 트렌드일 가능성이 높기 때문
        """
        if not posts:
            return 0.0

        total_engagement = sum(p.engagement.total_engagement for p in posts)

        # 로그 정규화 기본 점수 (10000 참여를 기준점으로)
        base_score = min(
            100.0,
            (math.log1p(total_engagement) / math.log1p(10000)) * 100
        )

        if is_cross_platform:
            # 크로스 플랫폼 부스트 적용
            boosted = base_score * self.boost
            return min(100.0, boosted)

        return base_score

    def _analyze_promotions(self, posts: list[SocialPost]) -> list[PromotionLabel]:
        """각 게시물의 Organic/Paid 판정을 일괄 수행합니다."""
        return [
            self._promo_detector.detect(post).label
            for post in posts
        ]
