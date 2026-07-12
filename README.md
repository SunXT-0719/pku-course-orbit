# PKUCourseOrbit

纯前端网站会在浏览器本地解析北大树洞成绩 HTML，文件不会上传到服务器。项目同时保留 Python 命令行脚本。

## 网站

无需构建步骤，直接用静态服务器运行：

```bash
python3 -m http.server 8000
```

然后访问 `http://localhost:8000`，选择保存好的成绩 HTML，即可预览并下载 PNG。

### 部署到 Cloudflare Pages

1. 将项目推送到 GitHub 或 GitLab，确认个人成绩 HTML 和生成图片没有提交。
2. 在 Cloudflare Dashboard 选择 **Workers & Pages → Create → Pages → Connect to Git**。
3. Framework preset 选择 **None**，Build command 留空，Build output directory 填 `.`。
4. 部署后访问 Cloudflare 提供的 `*.pages.dev` 地址。

`_headers` 已包含适用于静态站点的安全和隐私响应头。

## Python 命令行脚本

从北大树洞成绩页面保存的 HTML 中提取课程，并生成一张课程成绩图谱：

- 使用圆形气泡布局，每门课程的圆面积与学分成正比。
- 中心优先级为“专业必修 > 专业限选 > 其他”，同类课程中学分越高越靠近中心。
- 60–99 分从红色渐变到绿色，100 分使用彩虹渐变。
- 显示百分制数字成绩以及“合格/通过”；合格课程使用 99 分的绿色，退课 `W`、缓考等不显示。
- 圆形中只显示课程名称。

## 使用

首先在树洞成绩查询界面右键，选择“另存为”，得到北大树洞.html，放到项目文件夹中。

```bash
python3 -m pip install -r requirements.txt
python3 analyze_scores.py 北大树洞.html -o score-analysis.png --json courses.json
```

只生成一个学期：

```bash
python3 analyze_scores.py 北大树洞.html --semester '24-25学年度2学期' -o semester.png
```

HTML 字段映射：

| 字段 | 页面结构 |
|---|---|
| 学期 | `.semester-block` 首行中栏的 `.layout-vertical-up` |
| 每门课程 | `.semester-block > .course-row` |
| 学分 | 左栏 `.layout-vertical-up` |
| 课程名 | 中栏第一个 `.layout-vertical-up` |
| 页面分类 | 中栏 `.layout-vertical-down` |
| 成绩 | 右栏 `.layout-vertical-up` |
| 课程体系、课程号等 | 展开详情 `.layout-vertical-extra` 中的键值段落 |
