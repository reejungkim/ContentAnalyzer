"""
main.py — CLI 진입점

역할: click 기반 CLI로 사용자 입력을 받아
     스크래핑 → 트렌드 분석 → 결과 출력을 수행합니다.

사용법:
    python -m trend_analyzer "AI" --demo --limit 20
    python -m trend_analyzer "fashion" --limit 50 --export json
"""

import json
import logging
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from trend_analyzer.config import settings
from trend_analyzer.models import Platform, SocialPost, TrendResult, PromotionLabel
from trend_analyzer.scrapers.base import DemoScraper
from trend_analyzer.scrapers.threads_scraper import ThreadsScraper
from trend_analyzer.scrapers.instagram_scraper import InstagramScraper
from trend_analyzer.analyzer.trend_detector import TrendDetector

console = Console()

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@click.command()
@click.argument("topic")
@click.option(
    "--limit", "-l",
    default=30,
    help="플랫폼당 최대 수집 게시물 수 (기본: 30)",
)
@click.option(
    "--demo", "-d",
    is_flag=True,
    default=False,
    help="Demo 모드: API 없이 샘플 데이터로 실행",
)
@click.option(
    "--export", "-e",
    type=click.Choice(["json"], case_sensitive=False),
    default=None,
    help="결과를 JSON 파일로 내보내기",
)
def cli(topic: str, limit: int, demo: bool, export: str | None):
    """
    🔍 Social Trend Analyzer — Threads + Instagram 트렌드 감지

    TOPIC: 분석할 키워드 또는 해시태그 (예: "AI", "fashion", "패션")
    """
    # 앱 배너 출력
    console.print()
    console.print(Panel.fit(
        "[bold cyan]🔍 Social Trend Analyzer[/bold cyan]\n"
        f"[dim]Threads + Instagram 트렌드 감지 엔진[/dim]",
        border_style="cyan",
    ))
    console.print()

    # Demo 모드 판단: --demo 플래그 또는 API 토큰 없음
    use_demo = demo or settings.is_demo_mode
    if use_demo and not demo:
        console.print("[yellow]⚠️  API 토큰 미설정 — Demo 모드로 자동 전환[/yellow]")
        console.print("[dim]   .env 파일에 META_ACCESS_TOKEN을 설정하면 실제 API 사용 가능[/dim]")
        console.print()

    # --- 데이터 수집 ---
    all_posts: list[SocialPost] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        # [TODO] Threads API 수집 — 현재 API 권한 문제로 비활성화
        # task1 = progress.add_task("📱 Threads 데이터 수집 중...", total=None)
        # if use_demo:
        #     threads_posts = DemoScraper(Platform.THREADS).search(topic, limit)
        # else:
        #     threads_posts = ThreadsScraper().search(topic, limit)
        # progress.update(task1, completed=True, description=f"📱 Threads: {len(threads_posts)}건 수집 완료")
        threads_posts: list[SocialPost] = []

        # Instagram 수집
        task2 = progress.add_task("📸 Instagram 데이터 수집 중...", total=None)
        if use_demo:
            ig_posts = DemoScraper(Platform.INSTAGRAM).search(topic, limit)
        else:
            ig_posts = InstagramScraper().search(topic, limit)
        progress.update(task2, completed=True, description=f"📸 Instagram: {len(ig_posts)}건 수집 완료")

    all_posts = threads_posts + ig_posts
    console.print()

    if not all_posts:
        console.print("[red]❌ 수집된 게시물이 없습니다. 토픽을 변경해보세요.[/red]")
        return

    # --- 트렌드 분석 ---
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task3 = progress.add_task("🧠 트렌드 분석 중...", total=None)
        detector = TrendDetector()
        result = detector.analyze(topic, all_posts)
        progress.update(task3, completed=True, description="🧠 트렌드 분석 완료")

    console.print()

    # --- 결과 출력 ---
    _print_result(result, use_demo)

    # --- JSON 내보내기 ---
    if export == "json":
        output_path = _export_json(result, topic)
        console.print(f"\n[green]💾 결과가 저장되었습니다: {output_path}[/green]")


def _print_result(result: TrendResult, is_demo: bool):
    """트렌드 분석 결과를 테이블 형태로 출력합니다."""

    # --- 요약 패널 ---
    trend_emoji = {
        "🔥 HOT TREND": "[bold red]🔥 HOT TREND[/bold red]",
        "⚡ TRENDING": "[bold yellow]⚡ TRENDING[/bold yellow]",
        "📈 RISING": "[bold green]📈 RISING[/bold green]",
        "💤 LOW ACTIVITY": "[dim]💤 LOW ACTIVITY[/dim]",
        "❄️ NO TREND": "[dim]❄️ NO TREND[/dim]",
    }
    level_display = trend_emoji.get(result.trend_level, result.trend_level)

    # Organic/Paid 표시
    promo_display = {
        PromotionLabel.ORGANIC: "[green]🌱 Organic[/green]",
        PromotionLabel.PAID: "[red]💰 Paid/Promoted[/red]",
        PromotionLabel.UNCERTAIN: "[yellow]❓ Uncertain[/yellow]",
    }
    dominant = promo_display.get(result.dominant_promotion_label, "Unknown")

    summary_text = (
        f"[bold]토픽:[/bold] {result.topic}\n"
        f"[bold]트렌드 점수:[/bold] {result.trend_score}/100  {level_display}\n"
        f"[bold]판정:[/bold] {dominant} (Organic {result.organic_ratio:.0%})"
    )

    mode_badge = " [dim][DEMO][/dim]" if is_demo else ""
    console.print(Panel(
        summary_text,
        title=f"[bold]📊 트렌드 분석 결과{mode_badge}[/bold]",
        border_style="bright_blue",
    ))

    # --- 세부 점수 테이블 ---
    score_table = Table(title="점수 상세", show_header=True, header_style="bold magenta")
    score_table.add_column("지표", style="cyan", justify="left")
    score_table.add_column("점수", justify="center")
    score_table.add_column("설명", style="dim")

    # Velocity
    vel_bar = _score_bar(result.velocity_score)
    score_table.add_row("⚡ Velocity", f"{result.velocity_score:.1f}", vel_bar)

    # Volume
    vol_bar = _score_bar(result.volume_score)
    score_table.add_row("📊 Volume", f"{result.volume_score:.1f}", vol_bar)

    # Amplification
    amp_bar = _score_bar(result.amplification_score)
    cross_info = "✅ 크로스 플랫폼" if result.is_cross_platform else "단일 플랫폼"
    score_table.add_row("🔊 Amplification", f"{result.amplification_score:.1f}", f"{amp_bar} {cross_info}")

    console.print(score_table)
    console.print()

    # --- 플랫폼 분포 ---
    dist_table = Table(title="플랫폼 분포", show_header=True, header_style="bold magenta")
    dist_table.add_column("플랫폼", justify="center")
    dist_table.add_column("게시물 수", justify="center")
    dist_table.add_column("비율", justify="center")

    total = result.total_posts
    dist_table.add_row(
        "📱 Threads",
        str(result.threads_count),
        f"{result.threads_count / total:.0%}" if total > 0 else "0%",
    )
    dist_table.add_row(
        "📸 Instagram",
        str(result.instagram_count),
        f"{result.instagram_count / total:.0%}" if total > 0 else "0%",
    )
    dist_table.add_row("[bold]합계[/bold]", f"[bold]{total}[/bold]", "[bold]100%[/bold]")

    console.print(dist_table)
    console.print()

    # --- Organic/Paid 분석 ---
    promo_table = Table(title="Organic vs. Paid 분석", show_header=True, header_style="bold magenta")
    promo_table.add_column("분류", justify="center")
    promo_table.add_column("게시물 수", justify="center")
    promo_table.add_column("비율", justify="center")

    promo_table.add_row(
        "🌱 Organic",
        str(result.organic_count),
        f"{result.organic_count / total:.0%}" if total > 0 else "0%",
    )
    promo_table.add_row(
        "💰 Paid",
        str(result.paid_count),
        f"{result.paid_count / total:.0%}" if total > 0 else "0%",
    )
    promo_table.add_row(
        "❓ Uncertain",
        str(result.uncertain_count),
        f"{result.uncertain_count / total:.0%}" if total > 0 else "0%",
    )

    console.print(promo_table)
    console.print()

    # --- 상위 게시물 ---
    if result.top_posts:
        top_table = Table(title="🏆 참여도 상위 게시물", show_header=True, header_style="bold magenta")
        top_table.add_column("#", justify="center", width=3)
        top_table.add_column("플랫폼", justify="center", width=10)
        top_table.add_column("작성자", width=15)
        top_table.add_column("내용", width=40)
        top_table.add_column("참여도", justify="right", width=10)

        for idx, post in enumerate(result.top_posts[:5], 1):
            # 텍스트를 40자로 제한
            short_text = post.text[:40] + "..." if len(post.text) > 40 else post.text
            platform_icon = "📱" if post.platform == Platform.THREADS else "📸"
            top_table.add_row(
                str(idx),
                f"{platform_icon} {post.platform.value}",
                post.author,
                short_text,
                f"{post.engagement.total_engagement:,}",
            )

        console.print(top_table)


def _score_bar(score: float, width: int = 20) -> str:
    """점수를 시각적 바 차트로 변환합니다."""
    filled = int(score / 100 * width)
    bar = "█" * filled + "░" * (width - filled)

    # 점수에 따라 색상 변경
    if score >= 70:
        return f"[green]{bar}[/green]"
    elif score >= 40:
        return f"[yellow]{bar}[/yellow]"
    return f"[red]{bar}[/red]"


def _export_json(result: TrendResult, topic: str) -> Path:
    """분석 결과를 JSON 파일로 내보냅니다."""
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    # 파일명에 토픽과 타임스탬프 포함
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"trend_{topic.replace(' ', '_')}_{timestamp}.json"
    output_path = output_dir / filename

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            result.to_dict(),
            f,
            ensure_ascii=False,  # 한국어 유지
            indent=2,
            default=str,  # datetime 등 직렬화 불가 타입 처리
        )

    return output_path


if __name__ == "__main__":
    cli()
