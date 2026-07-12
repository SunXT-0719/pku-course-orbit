"use strict";

const fileInput = document.getElementById("html-file");
const uploadPanel = document.getElementById("upload-panel");
const statusNode = document.getElementById("status");
const resultSection = document.getElementById("result");
const semesterSelect = document.getElementById("semester");
const downloadButton = document.getElementById("download");
const canvas = document.getElementById("orbit-canvas");
const summaryNode = document.getElementById("summary");
const accessibleList = document.getElementById("accessible-courses");
const ctx = canvas.getContext("2d");

let allCourses = [];

function cleanText(node) {
  return node ? node.textContent.replace(/\s+/g, " ").trim() : "";
}

function detailValue(row, label) {
  const paragraphs = row.querySelectorAll(".layout-vertical-extra p");
  for (const paragraph of paragraphs) {
    const bold = paragraph.querySelector("b");
    if (cleanText(bold).replace(/[：:]$/, "") === label) {
      const span = paragraph.querySelector("span");
      return span ? cleanText(span) : cleanText(paragraph).replace(cleanText(bold), "").trim();
    }
  }
  return "";
}

// ---- Safari .webarchive (binary plist) minimal extractor ----
// Only extracts the first <data> blob after the "WebResourceData" key from a bplist00.
// This is intentionally minimal – a full plist parser is not needed for webarchives.

function parseWebArchive(buffer) {
  const bytes = new Uint8Array(buffer);
  // Binary plist (bplist00) — not supported in browser JS.
  // Safari's "存储为 → 页面归档" produces this format.
  if (bytes[0] === 0x62 && bytes[1] === 0x70 && bytes[2] === 0x6c) {
    throw new Error(
      "Safari .webarchive（二进制格式）网页版暂不支持解析。请改用以下方式：\n" +
      "1）Safari「文件 → 存储为…」格式选择「页面源码」保存为 .html；或\n" +
      "2）使用命令行：python3 analyze_scores.py 你的文件.webarchive"
    );
  }
  // Try XML plist fallback
  const text = new TextDecoder().decode(bytes);
  if (text.includes("<plist")) {
    return extractHtmlFromXmlPlist(text);
  }
  throw new Error("不支持的 .webarchive 格式。");
}

function extractHtmlFromXmlPlist(text) {
  const doc = new DOMParser().parseFromString(text, "application/xml");
  const allKeys = doc.querySelectorAll("dict > key");
  for (const key of allKeys) {
    if (key.textContent === "WebResourceData") {
      const dataEl = key.nextElementSibling;
      if (dataEl && dataEl.tagName === "data") {
        const base64 = dataEl.textContent.replace(/\s+/g, "");
        const binary = atob(base64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
        return new TextDecoder().decode(bytes);
      }
    }
  }
  throw new Error("无法从 .webarchive 中提取 HTML 数据。");
}

function parseGrades(source) {
  const documentNode = new DOMParser().parseFromString(source, "text/html");
  const blocks = documentNode.querySelectorAll(".semester-block");
  const courses = [];
  for (const block of blocks) {
    const header = Array.from(block.children).find((child) => !child.classList.contains("course-row"));
    const semester = cleanText(header?.querySelector(".layout-row-middle .layout-vertical-up")) || "未知学期";
    const rows = Array.from(block.children).filter((child) => child.classList.contains("course-row"));
    for (const row of rows) {
      const creditText = cleanText(row.querySelector(".layout-row-left .layout-vertical-up"));
      const name = cleanText(row.querySelector(".layout-row-middle .layout-vertical-up"));
      const displayCategory = cleanText(row.querySelector(".layout-row-middle .layout-vertical-down")) || "未分类";
      const scoreText = cleanText(row.querySelector(".layout-row-right .layout-vertical-up"));
      const credits = Number(creditText);
      const score = /^\d+(?:\.\d+)?$/.test(scoreText) ? Number(scoreText) : null;
      if (!name || !Number.isFinite(credits)) continue;
      courses.push({
        semester,
        name,
        credits,
        scoreText,
        score,
        displayCategory,
        category: detailValue(row, "课程体系") || displayCategory,
      });
    }
  }
  if (!courses.length) throw new Error("没有找到课程，请确认文件来自已加载完成的北大树洞成绩页面。");
  return courses;
}

function isVisibleCourse(course) {
  return course.score !== null || course.scoreText === "合格" || course.scoreText === "通过";
}

function categoryPriority(course) {
  if (course.category === "专业必修") return 3;
  if (course.category === "专业限选") return 2;
  return 1;
}

function packPriorityCircles(courses) {
  const ordered = [...courses].sort((a, b) =>
    categoryPriority(b) - categoryPriority(a) || b.credits - a.credits || b.name.localeCompare(a.name, "zh-CN")
  );
  const placed = [];
  const goldenAngle = Math.PI * (3 - Math.sqrt(5));
  const gap = 5;
  ordered.forEach((course, itemIndex) => {
    const radius = 34 * Math.sqrt(Math.max(course.credits, 0.55));
    if (!placed.length) {
      placed.push({ course, x: 0, y: 0, radius });
      return;
    }
    let found = null;
    for (let ringIndex = 1; ringIndex < 600 && !found; ringIndex += 1) {
      const distance = ringIndex * 4;
      const points = Math.max(10, Math.ceil(2 * Math.PI * distance / 8));
      const offset = itemIndex * goldenAngle;
      for (let pointIndex = 0; pointIndex < points; pointIndex += 1) {
        const angle = offset + pointIndex * 2 * Math.PI / points;
        const x = distance * Math.cos(angle);
        const y = distance * Math.sin(angle);
        const clear = placed.every((item) => Math.hypot(x - item.x, y - item.y) >= radius + item.radius + gap);
        if (clear) {
          found = { course, x, y, radius };
          break;
        }
      }
    }
    if (!found) throw new Error(`无法放置课程：${course.name}`);
    placed.push(found);
  });
  return placed;
}

function scoreColor(score) {
  const value = Math.min(99, Math.max(60, score));
  const hue = (value - 60) / 39 * 112;
  return `hsl(${hue} 62% 72%)`;
}

function roundedLegend(x, y, width, height) {
  const gradient = ctx.createLinearGradient(x, y, x + width, y);
  gradient.addColorStop(0, scoreColor(60));
  gradient.addColorStop(.5, scoreColor(79.5));
  gradient.addColorStop(1, scoreColor(99));
  ctx.fillStyle = gradient;
  ctx.beginPath();
  ctx.roundRect(x, y, width, height, height / 2);
  ctx.fill();
  const rainbow = ctx.createLinearGradient(x + width + 12, y, x + width + 38, y);
  [0, .2, .4, .6, .8, 1].forEach((stop, index) => rainbow.addColorStop(stop, `hsl(${index * 72} 48% 84%)`));
  ctx.fillStyle = rainbow;
  ctx.beginPath();
  ctx.roundRect(x + width + 12, y, 26, height, height / 2);
  ctx.fill();
}

function wrapText(text, maxWidth, maxLines) {
  const lines = [];
  let current = "";
  for (const character of text) {
    if (ctx.measureText(current + character).width <= maxWidth) {
      current += character;
    } else {
      if (current) lines.push(current);
      current = character;
      if (lines.length === maxLines) break;
    }
  }
  if (current && lines.length < maxLines) lines.push(current);
  if (lines.join("").length < text.length && lines.length) {
    while (lines.at(-1) && ctx.measureText(`${lines.at(-1)}…`).width > maxWidth) {
      lines[lines.length - 1] = lines.at(-1).slice(0, -1);
    }
    lines[lines.length - 1] += "…";
  }
  return lines;
}

function drawCourse(item, centerX, centerY, scale) {
  const x = centerX + item.x * scale;
  const y = centerY + item.y * scale;
  const radius = item.radius * scale;
  ctx.fillStyle = "rgba(46, 44, 37, .12)";
  ctx.beginPath();
  ctx.arc(x + 4, y + 7, radius, 0, Math.PI * 2);
  ctx.fill();
  if (item.course.score === 100) {
    const rainbow = ctx.createLinearGradient(x - radius, y, x + radius, y);
    [0, .2, .4, .6, .8, 1].forEach((stop, index) => rainbow.addColorStop(stop, `hsl(${index * 72} 48% 84%)`));
    ctx.fillStyle = rainbow;
  } else {
    ctx.fillStyle = scoreColor(item.course.score ?? 99);
  }
  ctx.beginPath();
  ctx.arc(x, y, radius, 0, Math.PI * 2);
  ctx.fill();
  if (radius * 2 < 58) return;
  const fontSize = Math.max(15, Math.min(29, Math.round(radius * .27)));
  ctx.font = `500 ${fontSize}px Inter, -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif`;
  ctx.fillStyle = "#202622";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  const lines = wrapText(item.course.name, radius * 1.48, radius >= 72 ? 3 : 2);
  const lineHeight = fontSize + 6;
  const startY = y - (lines.length - 1) * lineHeight / 2;
  lines.forEach((line, index) => ctx.fillText(line, x, startY + index * lineHeight));
}

function render(courses) {
  const visible = courses.filter(isVisibleCourse);
  if (!visible.length) throw new Error("这个范围内没有数字成绩或合格成绩。");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#f7f4ed";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#202621";
  ctx.font = '500 44px Inter, -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif';
  ctx.textAlign = "left";
  ctx.textBaseline = "alphabetic";
  ctx.fillText("课程成绩图谱", 70, 82);
  roundedLegend(1390, 63, 250, 18);
  ctx.fillStyle = "#6d726c";
  ctx.font = "400 16px Inter, sans-serif";
  ctx.fillText("60", 1354, 78);
  ctx.fillText("100", 1682, 78);

  const packed = packPriorityCircles(visible);
  const extent = Math.max(...packed.map((item) => Math.hypot(item.x, item.y) + item.radius));
  const centerX = 900;
  const centerY = 970;
  const plotRadius = 760;
  const scale = (plotRadius - 14) / extent;
  ctx.strokeStyle = "#e5e0d6";
  ctx.lineWidth = 2;
  [.34, .67, 1].forEach((fraction) => {
    ctx.beginPath();
    ctx.arc(centerX, centerY, plotRadius * fraction, 0, Math.PI * 2);
    ctx.stroke();
  });
  [...packed].reverse().forEach((item) => drawCourse(item, centerX, centerY, scale));

  summaryNode.textContent = `显示 ${visible.length} 门课程 · 圆面积代表学分 · 越靠近中心优先级越高`;
  canvas.setAttribute("aria-label", `课程成绩圆形气泡图，共显示 ${visible.length} 门课程。`);
  accessibleList.replaceChildren(...visible.map((course) => {
    const item = document.createElement("li");
    item.textContent = `${course.name}，${course.credits} 学分，${course.scoreText}`;
    return item;
  }));
}

function populateSemesters(courses) {
  const semesters = [...new Set(courses.map((course) => course.semester))];
  semesterSelect.replaceChildren();
  const allOption = new Option("全部学期", "__all__");
  semesterSelect.add(allOption);
  semesters.forEach((semester) => semesterSelect.add(new Option(semester, semester)));
}

function renderSelection() {
  const selection = semesterSelect.value;
  const courses = selection === "__all__" ? allCourses : allCourses.filter((course) => course.semester === selection);
  render(courses);
}

async function loadFile(file) {
  if (!file || !/\.html?$/i.test(file.name) && !/\.webarchive$/i.test(file.name)) {
    statusNode.textContent = "请选择 HTML 或 .webarchive 文件。";
    return;
  }
  statusNode.textContent = "正在读取…";
  try {
    let source;
    if (/\.webarchive$/i.test(file.name)) {
      source = parseWebArchive(await file.arrayBuffer());
    } else {
      source = await file.text();
    }
    allCourses = parseGrades(source);
    populateSemesters(allCourses);
    renderSelection();
    statusNode.textContent = `已读取 ${allCourses.length} 门课程。`;
    resultSection.hidden = false;
    resultSection.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
  } catch (error) {
    resultSection.hidden = true;
    statusNode.textContent = error instanceof Error ? error.message : "读取文件失败。";
  }
}

fileInput.addEventListener("change", () => loadFile(fileInput.files?.[0]));
semesterSelect.addEventListener("change", renderSelection);
downloadButton.addEventListener("click", () => {
  const link = document.createElement("a");
  const suffix = semesterSelect.value === "__all__" ? "all" : semesterSelect.value.replace(/[^\w\u4e00-\u9fff-]+/g, "-");
  link.download = `course-orbit-${suffix}.png`;
  link.href = canvas.toDataURL("image/png");
  link.click();
});

["dragenter", "dragover"].forEach((eventName) => uploadPanel.addEventListener(eventName, (event) => {
  event.preventDefault();
  uploadPanel.classList.add("is-dragging");
}));
["dragleave", "drop"].forEach((eventName) => uploadPanel.addEventListener(eventName, (event) => {
  event.preventDefault();
  uploadPanel.classList.remove("is-dragging");
}));
uploadPanel.addEventListener("drop", (event) => loadFile(event.dataTransfer?.files?.[0]));
