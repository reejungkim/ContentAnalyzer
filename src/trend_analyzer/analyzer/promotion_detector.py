"""
promotion_detector.py — Organic vs. Paid/Promoted 콘텐츠 구분

역할: 각 게시물이 자연 발생(Organic)인지 유료 광고/프로모션(Paid)인지 판단합니다.

판단 기준 (5가지 신호):
    1. 스폰서 키워드 (#ad, Sponsored 등)      → 높은 가중치 (확정적)
    2. 플랫폼 스폰서 표시                      → 높은 가중치 (확정적)
    3. 참여율 이상 (팔로워 대비)               → 중간 가중치
    4. 참여 시간 초기 급등 패턴                 → 중간 가중치
    5. 비즈니스 계정 여부                      → 낮은 가중치

최종 promotion_probability (0.0 ~ 1.0):
    ≥ 0.7 → Paid
    ≤ 0.3 → Organic
    중간  → Uncertain
"""

import re

from trend_analyzer.models import SocialPost, PromotionSignal


# 스폰서/광고를 나타내는 키워드 패턴 (대소문자 무시)
SPONSOR_KEYWORDS = [
    r"(?:^|\s)#ad(?:\s|$)",       # #ad (독립된 해시태그)
    r"(?:^|\s)#sponsored(?:\s|$)", # #sponsored
    r"(?:^|\s)#광고(?:\s|$)",      # #광고
    r"(?:^|\s)#스폰서(?:\s|$)",    # #스폰서
    r"paid\s*partnership",         # Paid partnership
    r"sponsored\s*post",           # Sponsored post
    r"브랜디드\s*콘텐츠",           # 브랜디드 콘텐츠
    r"광고\s*포함",                 # 광고 포함
]

# 키워드를 하나의 정규식으로 컴파일 (성능 최적화)
# 왜 \b 대신 (?:^|\s)를 쓰나요?
# → \b는 word boundary인데, #은 non-word 문자라서
#   "#ad" 앞의 \b가 매칭되지 않습니다.
_SPONSOR_PATTERN = re.compile(
    "|".join(SPONSOR_KEYWORDS),
    re.IGNORECASE
)


class PromotionDetector:
    """
    Organic vs. Paid 판별기.

    각 신호를 독립적으로 분석하고, 가중치를 적용하여
    최종 promotion_probability를 산출합니다.

    사용 예시:
        detector = PromotionDetector()
        signal = detector.detect(post)
        print(signal.label)        # "organic" / "paid" / "uncertain"
        print(signal.promotion_probability)  # 0.15
    """

    # 각 신호별 가중치
    WEIGHT_KEYWORD = 0.35        # 스폰서 키워드 (가장 강력한 신호)
    WEIGHT_PLATFORM_FLAG = 0.30  # 플랫폼 자체 스폰서 표시
    WEIGHT_ENGAGEMENT = 0.15     # 참여율 이상
    WEIGHT_BURST = 0.10          # 초기 급등 패턴
    WEIGHT_BUSINESS = 0.10       # 비즈니스 계정

    def detect(self, post: SocialPost) -> PromotionSignal:
        """
        단일 게시물의 Organic/Paid 여부를 분석합니다.

        Args:
            post: 분석할 게시물

        Returns:
            PromotionSignal (각 신호 + 최종 확률)
        """
        # --- 신호 1: 스폰서 키워드 감지 ---
        keyword_detected = self._check_sponsor_keywords(post.text)

        # --- 신호 2: 플랫폼 스폰서 표시 ---
        platform_flag = post.has_sponsor_label

        # --- 신호 3: 참여율 이상 감지 ---
        engagement_anomaly = self._check_engagement_anomaly(post)

        # --- 신호 4: 초기 급등 패턴 (게시물 단독으로는 판단 어려움 → 참여/조회 비율로 대체) ---
        burst_pattern = self._check_burst_pattern(post)

        # --- 신호 5: 비즈니스 계정 여부 ---
        business_account = post.is_business_account

        # --- 최종 확률 계산 ---
        probability = (
            (1.0 if keyword_detected else 0.0) * self.WEIGHT_KEYWORD
            + (1.0 if platform_flag else 0.0) * self.WEIGHT_PLATFORM_FLAG
            + (1.0 if engagement_anomaly else 0.0) * self.WEIGHT_ENGAGEMENT
            + (1.0 if burst_pattern else 0.0) * self.WEIGHT_BURST
            + (1.0 if business_account else 0.0) * self.WEIGHT_BUSINESS
        )

        return PromotionSignal(
            keyword_detected=keyword_detected,
            platform_sponsor_flag=platform_flag,
            engagement_anomaly=engagement_anomaly,
            burst_pattern=burst_pattern,
            business_account=business_account,
            promotion_probability=round(probability, 3),
        )

    def _check_sponsor_keywords(self, text: str) -> bool:
        """
        텍스트에서 스폰서/광고 관련 키워드를 찾습니다.

        왜 정규식을 사용하나요?
        → 단순 `in` 검사는 "Shade"에서 "#ad"를 잘못 감지할 수 있음.
          단어 경계(\b)를 사용하여 정확한 매칭만 수행합니다.
        """
        return bool(_SPONSOR_PATTERN.search(text))

    def _check_engagement_anomaly(self, post: SocialPost) -> bool:
        """
        팔로워 수 대비 참여율이 비정상적으로 높은지 판단합니다.

        기준:
        - 일반 참여율: 1~5% (좋아요/팔로워)
        - 10% 초과 → 비정상 (인위적 부스트 의심)
        - 팔로워 정보 없으면 판단 불가 (False)
        """
        if not post.follower_count or post.follower_count == 0:
            return False

        engagement_rate = post.engagement.likes / post.follower_count

        # 참여율 10% 초과는 비정상적으로 높음
        return engagement_rate > 0.10

    def _check_burst_pattern(self, post: SocialPost) -> bool:
        """
        프로모션 특유의 '초기 급등' 패턴을 감지합니다.

        프로모션 콘텐츠의 특징:
        - 조회수 대비 좋아요 비율이 매우 낮음 (광고 노출은 많지만 관심은 낮음)
        - 좋아요 대비 댓글 비율이 극단적으로 낮거나 높음

        한계:
        - 단일 게시물의 스냅샷만으로는 시계열 패턴 분석이 제한적입니다.
          시계열 데이터가 있으면 더 정밀한 분석이 가능합니다.
        """
        likes = post.engagement.likes
        views = post.engagement.views
        comments = post.engagement.comments

        # 조회수 대비 참여율이 극도로 낮은 경우 (광고 노출)
        if views > 0 and likes > 0:
            like_to_view_ratio = likes / views
            # 일반적으로 좋아요/조회 비율은 2~10%
            # 0.5% 미만이면 프로모션 의심
            if like_to_view_ratio < 0.005:
                return True

        # 좋아요는 많지만 댓글이 거의 없는 경우 (인위적 좋아요)
        if likes > 100 and comments == 0:
            return True

        return False
