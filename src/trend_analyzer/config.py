"""
config.py — 환경변수 및 설정 관리 모듈

역할: .env 파일에서 API 토큰과 트렌드 감지 파라미터를 로드합니다.
     API 토큰이 없으면 자동으로 Demo 모드로 전환됩니다.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """
    앱 전체 설정.
    .env 파일 또는 환경변수에서 값을 자동 로드합니다.
    """

    # --- Meta API 인증 ---
    # Meta Developer 앱에서 발급받은 장기(long-lived) 액세스 토큰
    meta_access_token: str = Field(
        default="",
        description="Meta Graph API 액세스 토큰"
    )
    # Instagram 비즈니스/크리에이터 계정의 숫자 ID
    instagram_business_account_id: str = Field(
        default="",
        description="Instagram 비즈니스 계정 ID"
    )
    # Threads 사용자 ID
    threads_user_id: str = Field(
        default="",
        description="Threads 사용자 ID"
    )

    # --- 트렌드 감지 파라미터 ---
    # Velocity 계산에 사용할 시간 윈도우 (시간 단위)
    # 예: 6이면 최근 6시간 동안의 참여 변화를 측정
    trend_velocity_window_hours: int = Field(
        default=6,
        description="Velocity 계산 시간 창 (시간)"
    )
    # 트렌드 후보로 인정하기 위한 최소 게시물 수
    trend_volume_threshold: int = Field(
        default=10,
        description="트렌드 최소 볼륨 기준"
    )
    # 크로스 플랫폼(Threads + Instagram 동시 감지)일 때 적용할 부스트 배율
    cross_platform_boost: float = Field(
        default=1.5,
        description="크로스 플랫폼 부스트 배율"
    )

    @property
    def is_demo_mode(self) -> bool:
        """
        API 토큰이 없으면 Demo 모드로 판단.
        Demo 모드에서는 샘플 데이터로 동작합니다.
        """
        return not self.meta_access_token

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# 전역 설정 인스턴스 — 앱 어디서든 import해서 사용
settings = Settings()
