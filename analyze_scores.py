#!/usr/bin/env python3
"""Parse a saved PKU grades page and render a credit-weighted score map."""

from __future__ import annotations

import argparse
import colorsys
import json
import math
import plistlib
from dataclasses import asdict, dataclass
from pathlib import Path

from lxml import html
from PIL import Image, ImageDraw, ImageFont


FONT_CANDIDATES = (
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/PingFang.ttc",
)


@dataclass
class Course:
    semester: str
    name: str
    credits: float
    score_text: str
    score: float | None
    display_category: str
    category: str
    course_id: str = ""
    record_type: str = ""


def clean_text(node) -> str:
    return " ".join("".join(node.itertext()).split()) if node is not None else ""


def first(node, xpath: str):
    result = node.xpath(xpath)
    return result[0] if result else None


def detail_value(row, label: str) -> str:
    for paragraph in row.xpath(".//div[contains(@class,'layout-vertical-extra')]//p"):
        bold = first(paragraph, ".//b")
        if bold is not None and clean_text(bold).rstrip("：:") == label:
            spans = paragraph.xpath("./span | .//b/following-sibling::span")
            return clean_text(spans[0]) if spans else clean_text(paragraph).replace(clean_text(bold), "", 1)
    return ""


def read_html_bytes(path: Path) -> bytes:
    """Read HTML bytes from a .html or .webarchive (Safari) file."""
    raw = path.read_bytes()
    if path.suffix.lower() == ".webarchive":
        plist = plistlib.loads(raw)
        return plist["WebMainResource"]["WebResourceData"]
    return raw


def parse_html(path: Path) -> list[Course]:
    root = html.fromstring(read_html_bytes(path))
    courses: list[Course] = []
    blocks = root.xpath("//div[contains(concat(' ',normalize-space(@class),' '),' semester-block ')]")
    for block in blocks:
        header = first(block, "./div[not(contains(concat(' ',normalize-space(@class),' '),' course-row '))][1]")
        semester_node = first(header, ".//div[contains(@class,'layout-row-middle')]//div[contains(@class,'layout-vertical-up')]") if header is not None else None
        semester = clean_text(semester_node) or "未知学期"
        for row in block.xpath("./div[contains(concat(' ',normalize-space(@class),' '),' course-row ')]"):
            credit_node = first(row, ".//div[contains(@class,'layout-row-left')]//div[contains(@class,'layout-vertical-up')]")
            name_node = first(row, ".//div[contains(@class,'layout-row-middle')]//div[contains(@class,'layout-vertical-up')]")
            cat_node = first(row, ".//div[contains(@class,'layout-row-middle')]//div[contains(@class,'layout-vertical-down')]")
            score_node = first(row, ".//div[contains(@class,'layout-row-right')]//div[contains(@class,'layout-vertical-up')]")
            try:
                credits = float(clean_text(credit_node))
            except ValueError:
                continue
            score_text = clean_text(score_node)
            try:
                score = float(score_text)
            except ValueError:
                score = None
            display_category = clean_text(cat_node) or "未分类"
            category = detail_value(row, "课程体系") or display_category
            courses.append(Course(
                semester=semester,
                name=clean_text(name_node),
                credits=credits,
                score_text=score_text,
                score=score,
                display_category=display_category,
                category=category,
                course_id=detail_value(row, "课程号"),
                record_type=detail_value(row, "成绩记录方式"),
            ))
    if not courses:
        raise ValueError("未找到课程。请确认文件来自北大树洞成绩页，并且保存时页面已显示成绩。")
    return courses


Rect = tuple[float, float, float, float]
Circle = tuple[float, float, float]


def binary_treemap(items: list[tuple[object, float]], rect: Rect) -> list[tuple[object, Rect]]:
    """A dependency-free, stable binary treemap."""
    if not items:
        return []
    if len(items) == 1:
        return [(items[0][0], rect)]
    total = sum(max(weight, 0.01) for _, weight in items)
    target, running, split = total / 2, 0.0, 1
    for index, (_, weight) in enumerate(items[:-1], 1):
        previous = abs(target - running)
        running += max(weight, 0.01)
        if abs(target - running) <= previous:
            split = index
        else:
            break
    left, right = items[:split], items[split:]
    left_weight = sum(max(weight, 0.01) for _, weight in left)
    x, y, w, h = rect
    ratio = left_weight / total
    if w >= h:
        first_rect = (x, y, w * ratio, h)
        second_rect = (x + w * ratio, y, w * (1 - ratio), h)
    else:
        first_rect = (x, y, w, h * ratio)
        second_rect = (x, y + h * ratio, w, h * (1 - ratio))
    return binary_treemap(left, first_rect) + binary_treemap(right, second_rect)


def category_priority(course: Course) -> int:
    """Strict type priority, with credits breaking ties inside each type."""
    if course.category == "专业必修":
        return 3
    if course.category == "专业限选":
        return 2
    return 1


def pack_priority_circles(courses: list[Course]) -> list[tuple[Course, Circle]]:
    """Place high-priority, high-credit circles nearest the origin."""
    ordered = sorted(
        courses,
        key=lambda course: (category_priority(course), course.credits, course.name),
        reverse=True,
    )
    placed: list[tuple[Course, Circle]] = []
    golden_angle = math.pi * (3 - math.sqrt(5))
    gap = 5.0
    for item_index, course in enumerate(ordered):
        radius = 34.0 * math.sqrt(max(course.credits, 0.55))
        if not placed:
            placed.append((course, (0.0, 0.0, radius)))
            continue
        found = None
        radial_step = 4.0
        for ring_index in range(1, 600):
            distance = ring_index * radial_step
            points = max(10, math.ceil(2 * math.pi * distance / 8.0))
            offset = item_index * golden_angle
            for point_index in range(points):
                angle = offset + point_index * (2 * math.pi / points)
                cx, cy = distance * math.cos(angle), distance * math.sin(angle)
                if all(
                    math.hypot(cx - px, cy - py) >= radius + pr + gap
                    for _, (px, py, pr) in placed
                ):
                    found = (cx, cy, radius)
                    break
            if found:
                break
        if found is None:
            raise RuntimeError(f"无法放置课程圆形：{course.name}")
        placed.append((course, found))
    return placed


def solid_score_color(score: float) -> tuple[int, int, int]:
    value = min(99.0, max(60.0, score))
    hue = ((value - 60.0) / 39.0) * 0.31  # red -> orange -> yellow -> green
    r, g, b = colorsys.hls_to_rgb(hue, 0.72, 0.62)
    return round(r * 255), round(g * 255), round(b * 255)


def darken(color: tuple[int, int, int], amount: float = 0.82) -> tuple[int, int, int]:
    return tuple(round(channel * amount) for channel in color)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size, index=0)
    return ImageFont.load_default(size=size)


def rainbow_tile(image: Image.Image, box: tuple[int, int, int, int], radius: int = 0) -> None:
    x0, y0, x1, y1 = box
    width, height = max(1, x1 - x0), max(1, y1 - y0)
    band = Image.new("RGB", (width, height))
    pixels = band.load()
    for x in range(width):
        hue = x / max(1, width - 1)
        r, g, b = colorsys.hls_to_rgb(hue, 0.84, 0.48)
        for y in range(height):
            pixels[x, y] = (round(r * 255), round(g * 255), round(b * 255))
    if radius:
        mask = Image.new("L", (width, height), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, fill=255)
        image.paste(band, (x0, y0), mask)
    else:
        image.paste(band, (x0, y0))


def rainbow_circle(image: Image.Image, box: tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = box
    width, height = max(1, x1 - x0), max(1, y1 - y0)
    band = Image.new("RGB", (width, height))
    pixels = band.load()
    for x in range(width):
        hue = x / max(1, width - 1)
        r, g, b = colorsys.hls_to_rgb(hue, 0.84, 0.48)
        color = (round(r * 255), round(g * 255), round(b * 255))
        for y in range(height):
            pixels[x, y] = color
    mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, width - 1, height - 1), fill=255)
    image.paste(band, (x0, y0), mask)


def fit_lines(draw: ImageDraw.ImageDraw, text: str, width: int, max_lines: int, text_font) -> list[str]:
    if width <= 0:
        return []
    lines, current = [], ""
    for char in text:
        candidate = current + char
        if draw.textbbox((0, 0), candidate, font=text_font)[2] <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = char
            if len(lines) == max_lines:
                break
    if current and len(lines) < max_lines:
        lines.append(current)
    if sum(len(line) for line in lines) < len(text) and lines:
        while lines[-1] and draw.textbbox((0, 0), lines[-1] + "…", font=text_font)[2] > width:
            lines[-1] = lines[-1][:-1]
        lines[-1] += "…"
    return lines


def draw_course_circle(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    course: Course,
    circle: Circle,
) -> None:
    cx, cy, radius = circle
    box = (
        round(cx - radius), round(cy - radius),
        round(cx + radius), round(cy + radius),
    )
    shadow = (box[0] + 4, box[1] + 7, box[2] + 4, box[3] + 7)
    draw.ellipse(shadow, fill=(218, 215, 207))
    if course.score == 100:
        rainbow_circle(image, box)
    else:
        color_score = course.score if course.score is not None else 99
        draw.ellipse(box, fill=solid_score_color(color_score))
    diameter = radius * 2
    if diameter < 58:
        return
    name_size = max(15, min(29, round(radius * 0.27)))
    name_font = font(name_size)
    content_width = round(radius * 1.48)
    max_lines = 3 if radius >= 72 else 2
    lines = fit_lines(draw, course.name, content_width, max_lines, name_font)
    line_h = name_size + 6
    ty = cy - len(lines) * line_h / 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=name_font)
        tx = cx - (bbox[2] - bbox[0]) / 2
        draw.text((tx, ty), line, font=name_font, fill=(31, 35, 33))
        ty += line_h


def render(courses: list[Course], output: Path, width: int = 1800) -> None:
    # Passed pass/fail courses share the 99-point green; other statuses stay hidden.
    courses = [
        course for course in courses
        if course.score is not None or course.score_text in {"合格", "通过"}
    ]
    if not courses:
        raise ValueError("没有可绘制的数字成绩或合格成绩。")
    height = width
    image = Image.new("RGB", (width, height), (246, 244, 238))
    draw = ImageDraw.Draw(image)
    margin, header_h = 72, 145
    draw.text((margin, 45), "课程成绩图谱", font=font(44), fill=(35, 39, 37))
    bar_w, bar_h = 260, 18
    bar_x, bar_y = width - margin - bar_w - 48, 69
    for x in range(bar_w):
        score = 60 + 39 * x / max(1, bar_w - 1)
        draw.line((bar_x + x, bar_y, bar_x + x, bar_y + bar_h), fill=solid_score_color(score))
    draw.text((bar_x - 36, bar_y - 2), "60", font=font(16), fill=(105, 106, 101))
    rainbow_tile(image, (bar_x + bar_w + 9, bar_y, bar_x + bar_w + 35, bar_y + bar_h), radius=9)
    draw.text((bar_x + bar_w + 43, bar_y - 2), "100", font=font(16), fill=(105, 106, 101))
    packed = pack_priority_circles(courses)
    outer_extent = max(math.hypot(cx, cy) + radius for _, (cx, cy, radius) in packed)
    plot_center = (width / 2, header_h + (height - header_h - margin) / 2)
    plot_radius = min(width - 2 * margin, height - header_h - margin) / 2
    scale = (plot_radius - 14) / outer_extent
    for ring_fraction in (0.34, 0.67, 1.0):
        ring_radius = plot_radius * ring_fraction
        ring_box = (
            plot_center[0] - ring_radius, plot_center[1] - ring_radius,
            plot_center[0] + ring_radius, plot_center[1] + ring_radius,
        )
        draw.ellipse(ring_box, outline=(229, 226, 218), width=2)
    # Draw outer circles first so the highest-priority center bubbles sit visually on top.
    transformed = [
        (course, (
            plot_center[0] + cx * scale,
            plot_center[1] + cy * scale,
            radius * scale,
        ))
        for course, (cx, cy, radius) in packed
    ]
    for course, circle in reversed(transformed):
        draw_course_circle(image, draw, course, circle)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, quality=95)


def main() -> None:
    parser = argparse.ArgumentParser(description="解析北大树洞成绩 HTML，并生成学分加权课程成绩图谱。")
    parser.add_argument("html", type=Path, help="从成绩页面保存的 HTML 或 Safari WebArchive (.webarchive) 文件")
    parser.add_argument("-o", "--output", type=Path, default=Path("score-analysis.png"), help="输出 PNG 路径")
    parser.add_argument("--semester", help="只绘制指定学期（如 24-25学年度2学期）")
    parser.add_argument("--json", type=Path, help="同时导出结构化课程 JSON")
    parser.add_argument("--width", type=int, default=1800, help="图片宽度，默认 1800")
    args = parser.parse_args()
    courses = parse_html(args.html)
    if args.semester:
        courses = [course for course in courses if course.semester == args.semester]
        if not courses:
            raise SystemExit(f"没有找到学期：{args.semester}")
    if args.json:
        args.json.write_text(json.dumps([asdict(c) for c in courses], ensure_ascii=False, indent=2), encoding="utf-8")
    render(courses, args.output, width=args.width)
    numeric = [c for c in courses if c.score is not None]
    print(f"已解析 {len(courses)} 门课程（{len(numeric)} 门百分制），生成 {args.output}")


if __name__ == "__main__":
    main()
