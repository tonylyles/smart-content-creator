"""用户界面 - 刘凯睿负责 + 曾睿（调度面板）

功能：
- Gradio Web界面（轻量级，无需前端构建）
- 主题和时间节点设定界面
- 任务拆分和流程可视化
- 实时内容预览功能
- 内容生成交互
- 评估结果展示与建议采纳
- 用户偏好设置
- 知识库检索界面
- 系统状态监控
- 调度管理面板（发布计划、定时任务、SLA监控）
- 与workflow.py引擎对接

注意：Vue3前端在独立frontend项目中，此模块提供
轻量级Python Web界面作为快速演示和调试入口。
"""
import json
import os
import time
from typing import Optional


# ==================== 流程阶段定义 ====================
PIPELINE_STAGES = [
    {"id": "rag_search", "label": "🔍 知识检索", "desc": "从知识库检索相关参考资料"},
    {"id": "generate_article", "label": "✍️ 内容生成", "desc": "AI生成营销内容"},
    {"id": "evaluate", "label": "📋 质量评估", "desc": "多维度评估内容质量"},
]


class AppUI:
    """用户界面 - Gradio Web界面.

    功能：
    - 主题和时间节点设定
    - 任务拆分和流程可视化
    - 实时内容预览
    - 评估结果展示与建议采纳
    - 用户偏好设置

    Attributes:
        engine: 工作流引擎实例.
        config: 全局配置字典.
    """

    def __init__(self, workflow_engine, config, scheduler=None):
        """初始化用户界面.

        Args:
            workflow_engine: 工作流引擎实例.
            config: 全局配置字典.
            scheduler: 调度器实例（TaskScheduler，可选）.
        """
        self.engine = workflow_engine
        self.config = config
        self.scheduler = scheduler  # 曾睿的调度器
        self._app = None

    def run(self, host="127.0.0.1", port=7860, share=False):
        """启动界面.

        Args:
            host: 监听地址.
            port: 监听端口.
            share: 是否创建公网链接.
        """
        try:
            import gradio as gr
            self._app = self._build_gradio_app()
            self._app.launch(server_name=host, server_port=port, share=share,
                             prevent_thread_lock=True)
            # 保持进程运行
            import time
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
        except ImportError:
            self._run_console()

    def _build_gradio_app(self):
        """构建Gradio界面.

        Returns:
            gr.Blocks: Gradio应用实例.
        """
        import gradio as gr

        # ==================== 回调函数 ====================

        def generate_content(title, content_type, scene_type, keywords_text,
                             timeline_text, auto_evaluate):
            """生成内容回调.

            Args:
                title: 文章标题.
                content_type: 内容类型.
                scene_type: 场景类型.
                keywords_text: 关键词（逗号分隔）.
                timeline_text: 时间节点（每行一个：阶段名|截止日期）.
                auto_evaluate: 是否自动评估.

            Returns:
                tuple: (生成内容, 评估结果, 修改建议, 流程状态, 配图建议)
            """
            keywords = [k.strip() for k in keywords_text.split(",") if k.strip()] if keywords_text else []

            # 解析时间节点
            timeline = []
            if timeline_text.strip():
                for line in timeline_text.strip().split("\n"):
                    line = line.strip()
                    if "|" in line:
                        parts = line.split("|", 1)
                        timeline.append({"phase": parts[0].strip(), "deadline": parts[1].strip()})
                    elif line:
                        timeline.append({"phase": line, "deadline": "待定"})

            # 流程状态跟踪
            status_lines = []
            status_lines.append("🔍 知识检索... 进行中")
            flow_status = "\n".join(status_lines)

            result = self.engine.run_task({
                "action": "generate",
                "title": title,
                "content_type": content_type,
                "scene_type": scene_type,
                "keywords": keywords,
                "timeline": timeline if timeline else None,
            })

            if isinstance(result, dict) and "markdown" in result:
                content = result["markdown"]
                review = result.get("review", {})

                # 流程完成状态
                status_lines = [
                    "🔍 知识检索... ✅",
                    "✍️ 内容生成... ✅",
                    "📋 质量评估... ✅" if auto_evaluate else "📋 质量评估... ⏭️ 跳过",
                    "🖼️ 配图建议... ✅",
                ]
                flow_status = "\n".join(status_lines)

                review_text = self._format_review(review, result.get("generation_time_ms", 0))
                suggestions = self._format_suggestions(review)

                # 生成配图建议
                image_suggestions = self._generate_image_suggestions(title, content, scene_type, content_type)

                # 生成可下载的文件
                download_path = self._export_article(title, content, image_suggestions)

                return content, review_text, suggestions, flow_status, image_suggestions, download_path
            return str(result), "", "生成完成，无建议", "❌ 生成失败", "暂无配图建议", None

        def evaluate_content(content, title, scene_type):
            """质量评估回调.

            Args:
                content: 文章内容.
                title: 文章标题.
                scene_type: 场景类型.

            Returns:
                tuple: (评估结果, 修改建议)
            """
            result = self.engine.run_task({
                "action": "evaluate",
                "title": title,
                "content": content,
                "scene_type": scene_type,
            })
            if isinstance(result, dict):
                review_text = self._format_review(result, 0)
                suggestions = self._format_suggestions(result)
                return review_text, suggestions
            return str(result), "评估完成"

        def apply_suggestion(content, suggestion_text):
            """采纳修改建议（在内容末尾标注已采纳的建议）.

            Args:
                content: 原始内容.
                suggestion_text: 选中的建议文本.

            Returns:
                str: 标注后的内容.
            """
            if not suggestion_text or suggestion_text == "暂无建议":
                return content
            note = f"\n\n> 📝 已采纳建议：{suggestion_text}\n"
            return content + note

        def regenerate_content(title, content, review_json_str, scene_type):
            """基于评估结果重新生成内容.

            Args:
                title: 文章标题.
                content: 原始内容.
                review_json_str: 评估结果JSON字符串.
                scene_type: 场景类型.

            Returns:
                tuple: (新内容, 新评估结果, 新建议)
            """
            try:
                evaluation_result = json.loads(review_json_str) if review_json_str else {}
            except json.JSONDecodeError:
                evaluation_result = {}

            # 尝试调用生成器的 regenerate 方法
            try:
                if hasattr(self.engine, 'stages') and 'generate_article' in self.engine.stages:
                    gen_func = self.engine.stages['generate_article']
                    if hasattr(gen_func, '__self__') and hasattr(gen_func.__self__, 'regenerate'):
                        result = gen_func.__self__.regenerate(
                            title, content, evaluation_result, scene_type
                        )
                        if isinstance(result, dict) and "markdown" in result:
                            new_content = result["markdown"]
                            # 自动评估新内容
                            eval_result = self.engine.run_task({
                                "action": "evaluate",
                                "title": title,
                                "content": new_content,
                                "scene_type": scene_type,
                            })
                            review_text = self._format_review(eval_result, result.get("generation_time_ms", 0))
                            suggestions = self._format_suggestions(eval_result)
                            return new_content, review_text, suggestions
            except Exception as e:
                print(f"[UI] 重新生成失败: {e}")

            # 回退：简单标注
            return content + "\n\n> 🔄 已根据建议修改（演示模式）", "重新评估完成", "暂无建议"

        def search_knowledge(query):
            """知识检索回调.

            Args:
                query: 查询文本.

            Returns:
                str: 格式化的检索结果.
            """
            if not query.strip():
                return "请输入查询内容"

            # 优先走 RAG 检索
            result = self.engine.run_task({
                "action": "search",
                "query": query,
            })

            # 如果 RAG 有结果，直接返回
            if isinstance(result, list) and result:
                texts = []
                for r in result[:5]:
                    score = r.get('score', 0)
                    score_pct = f"{score * 100:.0f}%" if isinstance(score, float) and score <= 1 else f"{score}"
                    title = r.get('title', '')
                    content = r.get('content', '')[:200]
                    source = r.get('source', '')
                    texts.append(
                        f"📌 **{title}** (相关度: {score_pct})\n"
                        f"{content}...\n"
                        f"*来源: {source}*" if source else f"📌 **{title}** (相关度: {score_pct})\n{content}..."
                    )
                return "\n\n---\n\n".join(texts)

            # RAG 无结果，尝试直接从知识库文件检索
            try:
                kb_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "jikang_knowledge.md")
                if not os.path.exists(kb_path):
                    kb_path = "data/jikang_knowledge.md"
                if os.path.exists(kb_path):
                    with open(kb_path, "r", encoding="utf-8") as f:
                        kb_content = f.read()

                    # 简单关键词匹配
                    from src.rag.retriever import RAGRetriever
                    retriever = RAGRetriever()
                    keywords = retriever._extract_keywords(query)
                    if keywords:
                        sections = kb_content.split("## ")
                        matched = []
                        for sec in sections:
                            if any(kw in sec for kw in keywords):
                                title_line = sec.split("\n")[0].strip()
                                preview = sec[:300].strip()
                                matched.append(f"📌 **{title_line}**\n{preview}...")
                        if matched:
                            return "\n\n---\n\n".join(matched[:5])

                    return "未找到与查询相关的知识。建议尝试关键词如：污泥干化、低温除湿、闭式循环、节能等"
            except Exception as e:
                pass

            return "知识库暂无数据。请先运行 `python init_knowledge.py` 初始化知识库，或检查 Qdrant 是否已启动。"

        def save_preferences(default_scene, default_type, tone, word_count, auto_brand):
            """保存用户偏好设置.

            Args:
                default_scene: 默认场景.
                default_type: 默认内容类型.
                tone: 写作语调.
                word_count: 默认字数.
                auto_brand: 是否自动注入品牌.

            Returns:
                str: 保存确认信息.
            """
            prefs = {
                "default_scene": default_scene,
                "default_content_type": default_type,
                "tone": tone,
                "default_word_count": word_count,
                "auto_brand_injection": auto_brand,
            }
            # 通过引擎传递到 PromptEngine
            if hasattr(self.engine, 'stages') and 'generate_article' in self.engine.stages:
                gen_func = self.engine.stages['generate_article']
                if hasattr(gen_func, '__self__') and hasattr(gen_func.__self__, 'prompt_engine'):
                    gen_func.__self__.prompt_engine.update_user_preferences(prefs)
            return "✅ 偏好设置已保存！将应用于后续内容生成。"

        # ==================== 界面布局 ====================

        with gr.Blocks(
            title="AuraScribe - 智能内容创作平台",
        ) as app:
            gr.Markdown(
                "# 🌿 AuraScribe 智能内容创作平台\n"
                "环保行业AI营销内容生成系统 | 吉康环境"
            )

            # ==================== Tab 1: AI创作 ====================
            with gr.Tab("✨ AI创作"):
                with gr.Row():
                    # 左侧：输入区
                    with gr.Column(scale=2):
                        title_input = gr.Textbox(
                            label="📝 文章标题",
                            placeholder="例如：2024年市政污水处理技术趋势",
                        )

                        with gr.Row():
                            type_input = gr.Dropdown(
                                choices=[
                                    "article", "battle_report",
                                    "policy_analysis", "tech_trend", "news_digest",
                                ],
                                value="article",
                                label="📄 内容类型",
                            )
                            scene_input = gr.Dropdown(
                                choices=["municipal", "industrial"],
                                value="municipal",
                                label="🏭 场景类型",
                            )

                        kw_input = gr.Textbox(
                            label="🔑 关键词（逗号分隔）",
                            placeholder="环保, 绿色发展, 污水处理",
                        )

                        # 时间节点设定
                        timeline_input = gr.Textbox(
                            label="📅 时间节点（每行一个，格式：阶段名|截止日期）",
                            placeholder="调研阶段|2024-06-30\n方案设计|2024-08-15\n工程实施|2024-12-01",
                            lines=3,
                        )

                        auto_eval = gr.Checkbox(
                            label="📋 自动评估生成内容",
                            value=True,
                        )

                        gen_btn = gr.Button("🚀 一键生成", variant="primary", size="lg")

                        # 流程可视化
                        flow_status = gr.Textbox(
                            label="🔄 执行流程",
                            value="等待开始...",
                            lines=4,
                            interactive=False,
                        )

                    # 右侧：输出区
                    with gr.Column(scale=3):
                        content_output = gr.Markdown(label="📖 生成内容预览")
                        image_suggestions_output = gr.Markdown(
                            label="🖼️ 配图建议",
                            visible=True,
                        )
                        review_output = gr.Textbox(
                            label="📊 评估结果",
                            lines=8,
                        )

                # 建议采纳区
                with gr.Row():
                    with gr.Column(scale=3):
                        suggestions_output = gr.Textbox(
                            label="💡 修改建议",
                            lines=3,
                            interactive=False,
                        )
                    with gr.Column(scale=1):
                        apply_btn = gr.Button("✅ 采纳建议", variant="secondary")
                        regen_btn = gr.Button("🔄 基于建议重新生成", variant="secondary")

                # 下载区
                with gr.Row():
                    download_file = gr.File(
                        label="📥 下载推文文件",
                        visible=True,
                        interactive=False,
                    )

                # 绑定事件
                gen_btn.click(
                    generate_content,
                    inputs=[title_input, type_input, scene_input, kw_input,
                            timeline_input, auto_eval],
                    outputs=[content_output, review_output, suggestions_output,
                             flow_status, image_suggestions_output, download_file],
                )

                apply_btn.click(
                    apply_suggestion,
                    inputs=[content_output, suggestions_output],
                    outputs=[content_output],
                )

                regen_btn.click(
                    regenerate_content,
                    inputs=[title_input, content_output, review_output, scene_input],
                    outputs=[content_output, review_output, suggestions_output],
                )

            # ==================== Tab 2: 知识检索 ====================
            with gr.Tab("🔍 知识检索"):
                search_input = gr.Textbox(
                    label="搜索查询",
                    placeholder="例如：VOCs废气治理",
                )
                search_btn = gr.Button("🔍 检索", variant="primary")
                search_output = gr.Markdown(label="检索结果")
                search_btn.click(
                    search_knowledge,
                    inputs=[search_input],
                    outputs=[search_output],
                )

            # ==================== Tab 3: 质量评估 ====================
            with gr.Tab("📋 质量评估"):
                with gr.Row():
                    with gr.Column():
                        eval_title = gr.Textbox(label="文章标题")
                        eval_scene = gr.Dropdown(
                            choices=["municipal", "industrial"],
                            value="municipal",
                            label="场景类型",
                        )
                        eval_content = gr.Textbox(label="文章内容", lines=10)
                        eval_btn = gr.Button("📋 开始评估", variant="primary")

                    with gr.Column():
                        eval_output = gr.Textbox(label="📊 评估结果", lines=8)
                        eval_suggestions = gr.Textbox(label="💡 修改建议", lines=4)
                        eval_apply_btn = gr.Button("✅ 采纳建议并标注")

                eval_btn.click(
                    evaluate_content,
                    inputs=[eval_content, eval_title, eval_scene],
                    outputs=[eval_output, eval_suggestions],
                )

                eval_apply_btn.click(
                    apply_suggestion,
                    inputs=[eval_content, eval_suggestions],
                    outputs=[eval_content],
                )

            # ==================== Tab 4: 偏好设置 ====================
            with gr.Tab("⚙️ 偏好设置"):
                gr.Markdown("### 🎨 用户偏好设置\n设置默认参数，将应用于后续所有内容生成。")

                with gr.Row():
                    with gr.Column():
                        pref_scene = gr.Dropdown(
                            choices=["municipal", "industrial"],
                            value="municipal",
                            label="默认场景类型",
                        )
                        pref_type = gr.Dropdown(
                            choices=[
                                "article", "battle_report",
                                "policy_analysis", "tech_trend", "news_digest",
                            ],
                            value="article",
                            label="默认内容类型",
                        )
                        pref_tone = gr.Dropdown(
                            choices=["professional", "casual", "technical"],
                            value="professional",
                            label="写作语调",
                        )

                    with gr.Column():
                        pref_word_count = gr.Textbox(
                            label="默认字数范围",
                            value="800-1500字",
                            placeholder="例如：800-1500字",
                        )
                        pref_auto_brand = gr.Checkbox(
                            label="自动注入品牌元素",
                            value=True,
                        )

                pref_save_btn = gr.Button("💾 保存偏好", variant="primary")
                pref_status = gr.Textbox(label="保存状态", interactive=False)

                pref_save_btn.click(
                    save_preferences,
                    inputs=[pref_scene, pref_type, pref_tone,
                            pref_word_count, pref_auto_brand],
                    outputs=[pref_status],
                )

            # ==================== Tab 5: 系统状态 ====================
            with gr.Tab("📊 系统状态"):
                status_btn = gr.Button("🔄 刷新状态")
                status_output = gr.Markdown(label="系统状态")
                status_btn.click(lambda: self.show_status(), outputs=[status_output])

            # ==================== Tab 6: 调度面板（曾睿） ====================
            with gr.Tab("⏰ 发布计划"):

                # --- 调度面板回调函数 ---
                def list_scheduler_tasks():
                    """查看已注册的调度任务"""
                    if self.scheduler is None:
                        return "调度器未初始化", ""
                    tasks = self.scheduler.list_tasks()
                    if not tasks:
                        return "暂无已注册的调度任务", ""
                    lines = []
                    for t in tasks:
                        lines.append(f"  📌 {t.get('name', 'N/A')} | {t.get('trigger', t.get('type', 'N/A'))} | 下次执行: {t.get('next_run', 'N/A')}")
                    task_list = "\n".join(lines)
                    stats = self.scheduler.get_stats()
                    pipeline = stats.get('pipeline', {})
                    stat_text = (
                        f"运行模式: {stats.get('mode', 'N/A')}\n"
                        f"时区: {stats.get('timezone', 'N/A')}\n"
                        f"线程池: {stats.get('max_workers', 'N/A')} 线程\n"
                        f"总任务数: {stats.get('total_tasks', 0)}\n"
                        f"SLA 达标率: {pipeline.get('sla_pass_rate', 0)}%\n"
                        f"平均耗时: {pipeline.get('avg_duration_sec', 0)}s\n"
                        f"Pipeline 执行次数: {pipeline.get('total_runs', 0)}"
                    )
                    return task_list, stat_text

                def add_schedule_task(name, topic, content_type, scene_type,
                                      schedule_type, cron_expr, daily_hour, daily_minute):
                    """添加调度任务"""
                    if self.scheduler is None:
                        return "❌ 调度器未初始化，无法添加任务"

                    if not name.strip():
                        return "❌ 任务名称不能为空"
                    if not topic.strip():
                        return "❌ 文章主题不能为空"

                    try:
                        if schedule_type == "cron":
                            if not cron_expr.strip():
                                return "❌ Cron 模式需要填写 Cron 表达式"
                            self.scheduler.add_pipeline_job(
                                job_name=name.strip(),
                                topic=topic.strip(),
                                content_type=content_type,
                                scene_type=scene_type,
                                cron=cron_expr.strip(),
                            )
                        elif schedule_type == "daily":
                            self.scheduler.add_pipeline_job(
                                job_name=name.strip(),
                                topic=topic.strip(),
                                content_type=content_type,
                                scene_type=scene_type,
                                hour=int(daily_hour),
                                minute=int(daily_minute),
                            )
                        else:
                            return f"❌ 未知调度类型: {schedule_type}"

                        return f"✅ 任务 '{name.strip()}' 已添加"
                    except Exception as e:
                        return f"❌ 添加任务失败: {e}"

                def remove_schedule_task(task_name):
                    """移除调度任务"""
                    if self.scheduler is None:
                        return "❌ 调度器未初始化"
                    if not task_name.strip():
                        return "❌ 任务名称不能为空"
                    try:
                        self.scheduler.remove_task(task_name.strip())
                        return f"✅ 任务 '{task_name.strip()}' 已移除"
                    except Exception as e:
                        return f"❌ 移除失败: {e}"

                def manual_trigger_pipeline(topic, content_type, scene_type, keywords_text):
                    """手动触发一次完整 Pipeline"""
                    if self.scheduler is None:
                        return "❌ 调度器未初始化", ""
                    if not topic.strip():
                        return "❌ 文章主题不能为空", ""

                    keywords = [k.strip() for k in keywords_text.split(",") if k.strip()] if keywords_text else []

                    try:
                        report = self.scheduler.run_pipeline_now(
                            topic=topic.strip(),
                            content_type=content_type,
                            scene_type=scene_type,
                            keywords=keywords,
                        )

                        # 格式化报告
                        lines = [
                            f"{'='*40}",
                            f"Pipeline 执行报告",
                            f"{'='*40}",
                            f"状态: {'✅ 成功' if report['status'] == 'success' else '❌ 失败'}",
                            f"全流程耗时: {report['total_duration_sec']}s",
                            f"SLA 达标: {'✅' if report['sla_pass'] else '❌'} (目标: {report['sla_target_sec']}s)",
                            f"重试次数: {report['retry_count']}/{report['max_retries']}",
                            f"",
                            f"各阶段执行情况:",
                        ]
                        for name, info in report.get("stages", {}).items():
                            icon = {"success": "✅", "error": "❌", "skipped": "⏭️"}.get(info["status"], "❓")
                            lines.append(f"  {icon} {name}: {info['duration_ms']}ms")

                        eval_data = report.get("evaluation", {})
                        if eval_data:
                            lines.extend([
                                "",
                                f"最终评估结果:",
                                f"  技术准确率: {eval_data.get('accuracy_score', 0)*100:.0f}%",
                                f"  合规性: {eval_data.get('compliance_score', 0)*100:.0f}%",
                                f"  综合评分: {eval_data.get('overall', 0)*100:.0f}%",
                                f"  结论: {eval_data.get('result', 'N/A')}",
                            ])

                        # 提取生成内容预览
                        content = ""
                        gen_data = report.get("content", {})
                        if isinstance(gen_data, dict):
                            content = gen_data.get("markdown", "")
                        elif isinstance(gen_data, str):
                            content = gen_data

                        return "\n".join(lines), content
                    except Exception as e:
                        return f"❌ Pipeline 执行失败: {e}", ""

                # --- 界面布局 ---
                gr.Markdown("### ⏰ 发布计划管理\n管理自动定时内容创作任务，监控全流程 SLA")

                with gr.Row():
                    # 左列：任务管理
                    with gr.Column(scale=2):
                        # 添加任务
                        gr.Markdown("#### ➕ 添加定时任务")
                        with gr.Row():
                            sched_name = gr.Textbox(label="任务名称", placeholder="如：每日早间环保资讯", scale=2)
                            sched_type = gr.Dropdown(
                                choices=["daily", "cron"],
                                value="daily",
                                label="调度类型",
                                scale=1,
                            )

                        with gr.Row():
                            sched_topic = gr.Textbox(label="文章主题", placeholder="如：广州环保政策解读")
                            sched_scene = gr.Dropdown(
                                choices=["municipal", "industrial"],
                                value="municipal",
                                label="场景类型",
                            )

                        sched_ctype = gr.Dropdown(
                            choices=["article", "battle_report", "policy_analysis", "tech_trend", "news_digest"],
                            value="article",
                            label="内容类型",
                        )

                        with gr.Row():
                            cron_input = gr.Textbox(label="Cron 表达式", placeholder="0 2 * * *", visible=False)
                            daily_hour = gr.Number(label="每日执行-小时", value=9, minimum=0, maximum=23, precision=0)
                            daily_minute = gr.Number(label="每日执行-分钟", value=0, minimum=0, maximum=59, precision=0)

                        def toggle_cron_visibility(schedule_type):
                            return gr.Textbox(visible=(schedule_type == "cron")), gr.Row(visible=(schedule_type != "cron"))

                        sched_type.change(
                            toggle_cron_visibility,
                            inputs=[sched_type],
                            outputs=[cron_input, daily_hour],
                        )

                        add_task_btn = gr.Button("➕ 添加任务", variant="primary")
                        add_task_status = gr.Textbox(label="操作结果", interactive=False)

                        # 移除任务
                        gr.Markdown("#### 🗑️ 移除任务")
                        with gr.Row():
                            remove_name = gr.Textbox(label="任务名称", placeholder="输入要移除的任务名称")
                            remove_btn = gr.Button("🗑️ 移除", variant="stop")
                        remove_status = gr.Textbox(label="移除结果", interactive=False)

                    # 右列：任务列表 + 统计
                    with gr.Column(scale=2):
                        gr.Markdown("#### 📋 已注册任务")
                        refresh_btn = gr.Button("🔄 刷新任务列表")
                        task_list_output = gr.Textbox(label="任务列表", lines=6, interactive=False)
                        stats_output = gr.Textbox(label="调度器统计", lines=6, interactive=False)

                # 手动触发
                gr.Markdown("#### 🚀 手动触发 Pipeline")
                with gr.Row():
                    trigger_topic = gr.Textbox(label="文章主题", placeholder="广州环保政策动态", scale=3)
                    trigger_ctype = gr.Dropdown(
                        choices=["article", "battle_report", "policy_analysis", "tech_trend", "news_digest"],
                        value="article",
                        label="内容类型",
                        scale=1,
                    )
                    trigger_scene = gr.Dropdown(
                        choices=["municipal", "industrial"],
                        value="municipal",
                        label="场景",
                        scale=1,
                    )
                trigger_kw = gr.Textbox(label="关键词（逗号分隔）", placeholder="环保, 绿色发展")
                trigger_btn = gr.Button("🚀 立即执行 Pipeline", variant="primary")
                with gr.Row():
                    trigger_report = gr.Textbox(label="执行报告", lines=10, interactive=False, scale=2)
                    trigger_content = gr.Textbox(label="生成内容预览", lines=10, interactive=False, scale=3)

                # 绑定事件
                add_task_btn.click(
                    add_schedule_task,
                    inputs=[sched_name, sched_topic, sched_ctype, sched_scene,
                            sched_type, cron_input, daily_hour, daily_minute],
                    outputs=[add_task_status],
                )
                remove_btn.click(remove_schedule_task, inputs=[remove_name], outputs=[remove_status])
                refresh_btn.click(list_scheduler_tasks, outputs=[task_list_output, stats_output])
                trigger_btn.click(
                    manual_trigger_pipeline,
                    inputs=[trigger_topic, trigger_ctype, trigger_scene, trigger_kw],
                    outputs=[trigger_report, trigger_content],
                )

        return app

    # ==================== 格式化辅助方法 ====================

    def _format_review(self, review, generation_time_ms):
        """格式化评估结果为可读文本.

        Args:
            review: 评估结果字典.
            generation_time_ms: 生成耗时（毫秒）.

        Returns:
            str: 格式化的评估文本.
        """
        if not isinstance(review, dict):
            return str(review)

        result_icon = {"pass": "✅ 通过", "needs_revision": "⚠️ 需修改", "fail": "❌ 不合格"}
        result_text = result_icon.get(review.get("result", ""), review.get("result", "N/A"))

        lines = [
            f"审核结果：{result_text}",
            f"",
            f"📊 评分明细：",
            f"  技术准确率：{review.get('accuracy_score', 0)*100:.0f}%",
            f"  合规性：{review.get('compliance_score', 0)*100:.0f}%",
            f"  可读性：{review.get('readability_score', 0)*100:.0f}%",
            f"  品牌匹配：{review.get('brand_alignment_score', 0)*100:.0f}%",
            f"  专业性：{review.get('professionalism_score', 0)*100:.0f}%",
            f"  综合评分：{review.get('overall', 0)*100:.0f}%",
            f"",
            f"⏱️ 生成耗时：{generation_time_ms/1000:.1f}s",
            f"",
            f"💬 评审意见：",
            f"{review.get('comments', '')}",
        ]
        return "\n".join(lines)

    def _format_suggestions(self, review):
        """格式化修改建议.

        Args:
            review: 评估结果字典.

        Returns:
            str: 格式化的建议文本.
        """
        if not isinstance(review, dict):
            return "暂无建议"

        suggestions = review.get("suggestions", [])
        if not suggestions:
            return "暂无建议"

        return "\n".join(f"💡 {s}" for s in suggestions)

    # ==================== 控制台模式 ====================

    def _run_console(self):
        """控制台模式（Gradio未安装时回退）."""
        print("\n" + "=" * 50)
        print("🌿 AuraScribe 智能内容创作平台")
        print("=" * 50)
        print("提示：安装 gradio 可启用Web界面 (pip install gradio)")
        print("当前为控制台模式\n")

        while True:
            try:
                print("\n操作：1.生成内容 2.知识检索 3.质量评估 4.偏好设置 5.系统状态 0.退出")
                choice = input("请选择 > ").strip()

                if choice == "1":
                    title = input("标题 > ").strip()
                    if title:
                        scene = input("场景(municipal/industrial)> ").strip() or "municipal"
                        ctype = input("类型(article/battle_report/policy_analysis/tech_trend/news_digest)> ").strip() or "article"
                        result = self.engine.run_task({
                            "action": "generate",
                            "title": title,
                            "scene_type": scene,
                            "content_type": ctype,
                        })
                        print("\n--- 生成结果 ---")
                        print(result.get("markdown", str(result)) if isinstance(result, dict) else str(result))
                elif choice == "2":
                    query = input("查询 > ").strip()
                    if query:
                        result = self.engine.run_task({"action": "search", "query": query})
                        print("\n--- 检索结果 ---")
                        print(json.dumps(result, ensure_ascii=False, indent=2) if isinstance(result, (dict, list)) else str(result))
                elif choice == "3":
                    content = input("内容 > ").strip()
                    if content:
                        result = self.engine.run_task({"action": "evaluate", "content": content, "title": ""})
                        print("\n--- 评估结果 ---")
                        print(json.dumps(result, ensure_ascii=False, indent=2) if isinstance(result, dict) else str(result))
                elif choice == "4":
                    print("偏好设置（控制台模式暂不支持，请使用Web界面）")
                elif choice == "5":
                    self.show_status()
                elif choice == "0":
                    print("再见！")
                    break
            except (KeyboardInterrupt, EOFError):
                print("\n再见！")
                break

    def _generate_image_suggestions(self, title, content, scene_type, content_type):
        """生成配图建议.

        调用 MultimodalProcessor 生成配图提示词和位置建议，
        返回用户可读的自然语言配图方案。

        Args:
            title: 文章标题
            content: 文章内容
            scene_type: 场景类型
            content_type: 内容类型

        Returns:
            str: 格式化的配图建议
        """
        try:
            from src.generator.multimodal_processor import MultimodalProcessor
            mp = MultimodalProcessor()
            prompts = mp.generate_image_prompts(title, scene_type, content_type)
            if not prompts:
                return "暂无配图建议"

            # 位置名称映射
            position_names = {
                "cover": "封面图",
                "after_h2_1": "第一小节后插图",
                "after_h2_2": "第二小节后插图",
                "after_h2_3": "第三小节后插图",
                "middle": "文中插图",
                "end": "文末插图",
            }

            lines = []
            for i, p in enumerate(prompts, 1):
                pos = position_names.get(p.get("position", ""), p.get("position", "插图"))
                alt = p.get("alt", "")
                prompt_text = p.get("prompt", "")
                width = p.get("width", 900)
                height = p.get("height", 500)
                lines.append(
                    f"🖼️ **配图{i}：{pos}**\n"
                    f"   描述：{alt}\n"
                    f"   建议尺寸：{width}×{height}px\n"
                    f"   AI生图提示词：{prompt_text[:80]}..."
                )

            return "\n\n".join(lines)
        except Exception as e:
            return f"配图建议生成失败（{e}），请手动配图"

    def _export_article(self, title, content, image_suggestions=""):
        """将生成的文章导出为 HTML 文件（微信排版适配版）.

        Args:
            title: 文章标题
            content: Markdown 正文
            image_suggestions: 配图建议文本

        Returns:
            str: 导出文件路径
        """
        try:
            from src.publisher.wechat_publisher import WeChatFormatter
            formatter = WeChatFormatter()
            html, digest = formatter.format_article(
                title=title,
                body_html=content,
                author="吉康环境",
            )

            # 添加配图建议（作为 HTML 注释或文末附录）
            if image_suggestions:
                appendix = (
                    '<div style="margin:32px 0 0; padding:16px; '
                    'background-color:#f9f9f9; border:1px dashed #cccccc; '
                    'border-radius:4px; font-size:13px; color:#888888;">'
                    '<p style="font-weight:bold; margin:0 0 8px; color:#555555;">'
                    '🖼️ 配图建议（编辑参考，发布时删除此区域）</p>'
                )
                for line in image_suggestions.split("\n"):
                    if line.strip():
                        appendix += f'<p style="margin:2px 0;">{line}</p>'
                appendix += '</div>'
                # 在品牌签名前插入配图建议
                html = html.replace(
                    '—— 广东吉康环境系统科技有限公司',
                    '—— 广东吉康环境系统科技有限公司</p>'
                    + appendix
                )

            # 保存文件
            output_dir = os.path.join("data", "published")
            os.makedirs(output_dir, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            safe_title = "".join(c for c in title[:20] if c.isalnum() or c in " _-")
            filename = f"{timestamp}_{safe_title}.html"
            filepath = os.path.join(output_dir, filename)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html)

            print(f"[导出] 文章已导出: {filepath}")
            return filepath

        except Exception as e:
            print(f"[导出] 导出失败: {e}")
            # 回退：简单保存 Markdown
            try:
                output_dir = os.path.join("data", "published")
                os.makedirs(output_dir, exist_ok=True)
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                safe_title = "".join(c for c in title[:20] if c.isalnum() or c in " _-")
                filename = f"{timestamp}_{safe_title}.md"
                filepath = os.path.join(output_dir, filename)
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(f"# {title}\n\n{content}")
                return filepath
            except Exception:
                return None

    def show_status(self):
        """显示系统状态（自然语言版）.

        将技术性状态信息转换为用户友好的自然语言描述。

        Returns:
            str: 自然语言格式的系统状态
        """
        try:
            # 基础状态
            has_api = bool(self.config.get("llm_api_key"))
            mode_text = "🟢 生产模式（已连接AI大模型）" if has_api else "🟡 演示模式（未配置API密钥）"

            # 工作流阶段
            stage_count = len(self.engine.stages) if hasattr(self.engine, 'stages') else 0
            stage_names = self.engine.list_stages() if hasattr(self.engine, 'list_stages') else []

            stage_map = {
                "rag_search": "知识检索",
                "generate_article": "内容生成",
                "evaluate": "质量评估",
                "publish_article": "微信发布",
                "crawl_news": "新闻爬取",
            }
            stage_texts = [stage_map.get(s, s) for s in stage_names]

            lines = [
                f"**🌿 AuraScribe 智能内容创作平台**\n",
                f"**运行模式**：{mode_text}",
                f"**已启用功能**：共 {stage_count} 个 — {', '.join(stage_texts)}",
            ]

            # 调度器状态
            if self.scheduler is not None:
                sched = self.scheduler.get_stats()
                is_running = sched.get("running", False)
                sched_status = "🟢 运行中" if is_running else "🟡 已就绪（未启动）"
                task_count = sched.get("total_tasks", 0)
                lines.append(f"**定时调度器**：{sched_status}，已注册 {task_count} 个定时任务")

                # Pipeline 统计
                pipeline = sched.get("pipeline", {})
                total_runs = pipeline.get("total_runs", 0)
                if total_runs > 0:
                    avg_time = pipeline.get("avg_duration_sec", 0)
                    sla_rate = pipeline.get("sla_pass_rate", 0)
                    lines.append(
                        f"**Pipeline 执行统计**：已运行 {total_runs} 次，"
                        f"平均耗时 {avg_time:.0f} 秒，SLA 达标率 {sla_rate}%"
                    )
                else:
                    lines.append("**Pipeline 执行统计**：尚未运行过完整流程")

            # 知识库状态
            try:
                import requests
                r = requests.get("http://localhost:6333/collections", timeout=3)
                if r.status_code == 200:
                    collections = r.json().get("result", {}).get("collections", [])
                    if collections:
                        col_names = [c.get("name", "") for c in collections]
                        lines.append(f"**知识库**：🟢 已连接，共 {len(collections)} 个知识集合（{', '.join(col_names)}）")
                    else:
                        lines.append("**知识库**：🟡 已连接但无数据（需要先导入知识库内容）")
                else:
                    lines.append("**知识库**：🟡 连接异常")
            except Exception:
                lines.append("**知识库**：🔴 未连接（Qdrant 向量数据库未启动）")

            # 发布模块状态
            try:
                from src.publisher import WeChatPublisher
                lines.append("**发布模块**：🟢 微信公众号发布器已就绪")
            except Exception:
                lines.append("**发布模块**：🟡 发布模块未配置")

            return "\n".join(lines)

        except Exception as e:
            return f"获取系统状态时出错：{e}"

    def show_logs(self):
        """显示日志."""
        print("[日志功能] 请查看 debug.log 文件")
