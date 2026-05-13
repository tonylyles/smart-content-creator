"""用户界面 - 刘凯睿负责

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
- 与workflow.py引擎对接

注意：Vue3前端在独立frontend项目中，此模块提供
轻量级Python Web界面作为快速演示和调试入口。
"""
import json
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

    def __init__(self, workflow_engine, config):
        """初始化用户界面.

        Args:
            workflow_engine: 工作流引擎实例.
            config: 全局配置字典.
        """
        self.engine = workflow_engine
        self.config = config
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
            self._app.launch(server_name=host, server_port=port, share=share)
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
                tuple: (生成内容, 评估结果, 修改建议, 流程状态)
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
                ]
                flow_status = "\n".join(status_lines)

                review_text = self._format_review(review, result.get("generation_time_ms", 0))
                suggestions = self._format_suggestions(review)
                return content, review_text, suggestions, flow_status
            return str(result), "", "生成完成，无建议", "❌ 生成失败"

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

            # 回退：简单标注
            return content + "\n\n> 🔄 已根据建议修改（演示模式）", "重新评估完成", "暂无建议"

        def search_knowledge(query):
            """知识检索回调.

            Args:
                query: 查询文本.

            Returns:
                str: 格式化的检索结果.
            """
            result = self.engine.run_task({
                "action": "search",
                "query": query,
            })
            if isinstance(result, list):
                texts = []
                for r in result[:5]:
                    texts.append(
                        f"📌 {r.get('title', '')} (相似度:{r.get('score', 0)*100:.0f}%)\n"
                        f"{r.get('content', '')[:200]}...\n"
                    )
                return "\n---\n".join(texts) if texts else "未找到相关知识"
            return str(result)

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
            theme=gr.themes.Soft(),
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

                # 绑定事件
                gen_btn.click(
                    generate_content,
                    inputs=[title_input, type_input, scene_input, kw_input,
                            timeline_input, auto_eval],
                    outputs=[content_output, review_output, suggestions_output, flow_status],
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
                status_output = gr.JSON(label="系统状态")
                status_btn.click(lambda: self.show_status(), outputs=[status_output])

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

    def show_status(self):
        """显示系统状态.

        Returns:
            dict: 系统状态字典.
        """
        status = {
            "app": "AuraScribe",
            "version": "1.0.0",
            "mode": "演示模式" if not self.config.get("llm_api_key") else "生产模式",
            "engine_stages": len(self.engine.stages) if hasattr(self.engine, 'stages') else 0,
            "registered_stages": self.engine.list_stages() if hasattr(self.engine, 'list_stages') else [],
        }
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return status

    def show_logs(self):
        """显示日志."""
        print("[日志功能] 请查看 debug.log 文件")
