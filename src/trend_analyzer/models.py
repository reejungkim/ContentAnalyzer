"""
models.py — 데이터 모델 정의

역할: 앱 전체에서 사용되는 데이터 구조를 정의합니다.
     Pydantic 모델로 타입 안전성과 자동 유효성 검증을 보장합니다.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Platform(str, Enum):
    """소셜 미디어 플랫폼 구분."""
    THREADS = "threads"
    INSTAGRAM = "instagram"


class ContentType(str, Enum):
    """콘텐츠 유형."""
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    CAROUSEL = "carousel"  # Instagram 다중 이미지


class PromotionLabel(str, Enum):
    """
    Organic / Paid 판정 결과.
    - ORGANIC: 자연 발생 콘텐츠
    - PAID: 유료 광고/프로모션 콘텐츠
    - UNCERTAIN: 확실하지 않음
    """
    ORGANIC = "organic"
    PAID = "paid"
    UNCERTAIN = "uncertain"


class EngagementMetrics(BaseModel):
    """
    참여 지표.
    각 플랫폼에서 수집 가능한 참여 수치를 통합 모델로 관리합니다.
    """
    likes: int = 0
    comments: int = 0
    shares: int = 0       # Instagram: 없음 / Threads: reposts
    views: int = 0        # 조회수 (제공되는 경우)
    reposts: int = 0      # Threads 전용: 리포스트 수

    @property
    def total_engagement(self) -> int:
        """총 참여 수. 모든 지표의 합산."""
        return self.likes + self.comments + self.shares + self.views + self.reposts


class SocialPost(BaseModel):
    """
    수집된 개별 소셜 미디어 게시물.

    Threads API와 Instagram Graph API에서 가져온 데이터를
    하나의 통합 구조로 변환하여 저장합니다.
    """
    post_id: str = Field(description="플랫폼 내 게시물 고유 ID")
    platform: Platform = Field(description="출처 플랫폼")
    author: str = Field(default="unknown", description="작성자 이름 또는 핸들")
    text: str = Field(default="", description="게시물 텍스트 내용")
    content_type: ContentType = Field(
        default=ContentType.TEXT,
        description="콘텐츠 유형"
    )
    engagement: EngagementMetrics = Field(
        default_factory=EngagementMetrics,
        description="참여 지표"
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="게시물 작성 시각"
    )
    hashtags: list[str] = Field(
        default_factory=list,
        description="게시물에 포함된 해시태그 목록"
    )
    url: str = Field(default="", description="게시물 원본 URL")

    # --- Promotion(광고) 감지용 힌트 필드 ---
    is_business_account: bool = Field(
        default=False,
        description="비즈니스/크리에이터 계정 여부"
    )
    has_sponsor_label: bool = Field(
        default=False,
        description="플랫폼에서 스폰서 표시가 되어 있는지"
    )
    follower_count: Optional[int] = Field(
        default=None,
        description="작성자 팔로워 수 (알 수 있는 경우)"
    )


class PromotionSignal(BaseModel):
    """
    Paid/Promoted 판단 근거.
    promotion_detector가 분석한 각 신호와 최종 확률을 담습니다.
    """
    keyword_detected: bool = Field(
        default=False,
        description="#ad, Sponsored 등 스폰서 키워드 발견 여부"
    )
    engagement_anomaly: bool = Field(
        default=False,
        description="참여 패턴 이상 (팔로워 대비 비정상적 참여율)"
    )
    burst_pattern: bool = Field(
        default=False,
        description="초기 급등 후 급감하는 프로모션 패턴"
    )
    business_account: bool = Field(
        default=False,
        description="비즈니스 계정 여부"
    )
    platform_sponsor_flag: bool = Field(
        default=False,
        description="플랫폼 자체 스폰서 표시"
    )
    promotion_probability: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="프로모션일 확률 (0.0 ~ 1.0)"
    )

    @property
    def label(self) -> PromotionLabel:
        """
        확률 기반 판정.
        - 0.7 이상 → Paid
        - 0.3 미만 → Organic
        - 그 사이 → Uncertain
        """
        if self.promotion_probability >= 0.7:
            return PromotionLabel.PAID
        elif self.promotion_probability <= 0.3:
            return PromotionLabel.ORGANIC
        return PromotionLabel.UNCERTAIN


class TrendResult(BaseModel):
    """
    트렌드 분석 최종 결과.
    하나의 토픽에 대한 종합적인 트렌드 판정을 담습니다.
    """
    topic: str = Field(description="분석한 토픽/키워드")

    # --- 감지 점수 (각각 0~100) ---
    velocity_score: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="참여 증가 속도 점수"
    )
    volume_score: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="게시물 볼륨 점수"
    )
    amplification_score: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="크로스 플랫폼 증폭 점수"
    )
    trend_score: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="종합 트렌드 점수"
    )

    # --- 세부 정보 ---
    total_posts: int = Field(default=0, description="수집된 총 게시물 수")
    threads_count: int = Field(default=0, description="Threads 게시물 수")
    instagram_count: int = Field(default=0, description="Instagram 게시물 수")
    is_cross_platform: bool = Field(
        default=False,
        description="크로스 플랫폼 감지 여부"
    )

    # --- Organic/Paid 분석 ---
    organic_count: int = Field(default=0, description="Organic 판정 게시물 수")
    paid_count: int = Field(default=0, description="Paid 판정 게시물 수")
    uncertain_count: int = Field(default=0, description="Uncertain 판정 게시물 수")
    dominant_promotion_label: PromotionLabel = Field(
        default=PromotionLabel.ORGANIC,
        description="전체 트렌드의 주된 판정"
    )
    organic_ratio: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Organic 비율 (0.0 ~ 1.0)"
    )

    # --- 샘플 게시물 ---
    top_posts: list[SocialPost] = Field(
        default_factory=list,
        description="참여도 상위 게시물 (최대 5개)"
    )

    @property
    def trend_level(self) -> str:
        """
        트렌드 레벨을 문자열로 반환.
        점수 구간별 직관적 레이블.
        """
        if self.trend_score >= 80:
            return "🔥 HOT TREND"
        elif self.trend_score >= 60:
            return "⚡ TRENDING"
        elif self.trend_score >= 40:
            return "📈 RISING"
        elif self.trend_score >= 20:
            return "💤 LOW ACTIVITY"
        return "❄️ NO TREND"

    def to_dict(self) -> dict:
        """JSON 내보내기용 딕셔너리 변환."""
        return self.model_dump(mode="json")
