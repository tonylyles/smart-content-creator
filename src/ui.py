"""用户界面 - 刘凯睿负责

功能：
- Gradio Web界面（轻量级，无需前端构建）
- 内容生成交互
- 质量评估展示
- 知识库检索界面
- 系统状态监控
- 与workflow.py引擎对接

注意：Vue3前端在独立frontend项目中，此模块提供
轻量级Python Web界面作为快速演示和调试入口。
"""
import json
from typing import Optional


class AppUI:
    """用户界面 - Gradio Web界面"""

    def __init__(self, workflow_engine, config):
        self.engine = workflow_engine
        self.config = config
        self._app = None

    def run(self, host="127.0.0.1", port=7860, share=False):
        """启动界面

        Args:
            host: 监听地址
            port: 监听端口
            share: 是否创建公网链接
        """
        try:
            import gradio as gr
            self._app = self._build_gradio_app()
            self._app.launch(server_name=host, server_port=port, share=share)
        except ImportError:
            # Gradio 未安装，使用控制台模式
            self._run_console()

    def _build_gradio_app(self):
        """构建Gradio界面"""
        import gradio as gr

        def generate_content(title, content_type, scene_type, keywords_text):
            """生成内容回调"""
            keywords = [k.strip() for k in keywords_text.split(",") if k.strip()] if keywords_text else []
            result = self.engine.run({
                "action": "generate",
                "title": title,
                "content_type": content_type,
                "scene_type": scene_type,
                "keywords": keywords,
            })
            if isinstance(result, dict) and "markdown" in result:
                content = result["markdown"]
                review = result.get("review", {})
                review_text = f"""✅ 审核结果：{review.get('result', 'N/A')}
技术准确率：{review.get('accuracy_score', 0)*100:.0f}%
合规率：{review.get('compliance_score', 0)*100:.0f}%
可读性：{review.get('readability_score', 0)*100:.0f}%
品牌匹配：{review.get('brand_alignment_score', 0)*100:.0f}%
耗时：{result.get('generation_time_ms', 0)/1000:.1f}s
---
{review.get('comments', '')}"""
                return content, review_text
            return str(result), "生成完成"

        def search_knowledge(query):
            """知识检索回调"""
            result = self.engine.run({
                "action": "search",
                "query": query,
            })
            if isinstance(result, list):
                texts = []
                for r in result[:5]:
                    texts.append(f"📌 {r.get('title', '')} (相似度:{r.get('score', 0)*100:.0f}%)\n{r.get('content', '')[:200]}...\n")
                return "\n---\n".join(texts) if texts else "未找到相关知识"
            return str(result)

        def evaluate_content(content, title):
            """质量评估回调"""
            result = self.engine.run({
                "action": "evaluate",
                "title": title,
                "content": content,
            })
            if isinstance(result, dict):
                return json.dumps(result, ensure_ascii=False, indent=2)
            return str(result)

        with gr.Blocks(title="AuraScribe - 智能内容创作平台", theme=gr.themes.Soft()) as app:
            gr.Markdown("# 🌿 AuraScribe 智能内容创作平台\n环保行业AI营销内容生成系统")

            with gr.Tab("✨ AI创作"):
                with gr.Row():
                    with gr.Column(scale=2):
                        title_input = gr.Textbox(label="文章标题", placeholder="例如：2024年市政污水处理技术趋势")
                        with gr.Row():
                            type_input = gr.Dropdown(
                                choices=["article", "battle_report", "policy_analysis", "tech_trend", "news_digest"],
                                value="article", label="内容类型",
                            )
                            scene_input = gr.Dropdown(
                                choices=["municipal", "industrial"],
                                value="municipal", label="场景类型",
                            )
                        kw_input = gr.Textbox(label="关键词（逗号分隔）", placeholder="环保, 绿色发展")
                        gen_btn = gr.Button("🚀 一键生成", variant="primary")
                    with gr.Column(scale=3):
                        content_output = gr.Markdown(label="生成内容")
                        review_output = gr.Textbox(label="审核结果", lines=8)

                gen_btn.click(
                    generate_content,
                    inputs=[title_input, type_input, scene_input, kw_input],
                    outputs=[content_output, review_output],
                )

            with gr.Tab("🔍 知识检索"):
                search_input = gr.Textbox(label="搜索查询", placeholder="例如：VOCs废气治理")
                search_btn = gr.Button("检索", variant="primary")
                search_output = gr.Markdown(label="检索结果")
                search_btn.click(search_knowledge, inputs=[search_input], outputs=[search_output])

            with gr.Tab("📋 质量评估"):
                eval_title = gr.Textbox(label="文章标题")
                eval_content = gr.Textbox(label="文章内容", lines=10)
                eval_btn = gr.Button("评估", variant="primary")
                eval_output = gr.JSON(label="评估结果")
                eval_btn.click(evaluate_content, inputs=[eval_content, eval_title], outputs=[eval_output])

            with gr.Tab("📊 系统状态"):
                status_btn = gr.Button("刷新状态")
                status_output = gr.JSON(label="系统状态")
                status_btn.click(lambda: self.show_status(), outputs=[status_output])

        return app

    def _run_console(self):
        """控制台模式（Gradio未安装时回退）"""
        print("\n" + "=" * 50)
        print("🌿 AuraScribe 智能内容创作平台")
        print("=" * 50)
        print("提示：安装 gradio 可启用Web界面 (pip install gradio)")
        print("当前为控制台模式\n")

        while True:
            try:
                print("\n操作：1.生成内容 2.知识检索 3.质量评估 4.系统状态 0.退出")
                choice = input("请选择 > ").strip()

                if choice == "1":
                    title = input("标题 > ").strip()
                    if title:
                        result = self.engine.run({"action": "generate", "title": title})
                        print("\n--- 生成结果 ---")
                        print(result.get("markdown", str(result)) if isinstance(result, dict) else str(result))
                elif choice == "2":
                    query = input("查询 > ").strip()
                    if query:
                        result = self.engine.run({"action": "search", "query": query})
                        print("\n--- 检索结果 ---")
                        print(json.dumps(result, ensure_ascii=False, indent=2) if isinstance(result, (dict, list)) else str(result))
                elif choice == "3":
                    content = input("内容 > ").strip()
                    if content:
                        result = self.engine.run({"action": "evaluate", "content": content, "title": ""})
                        print("\n--- 评估结果 ---")
                        print(json.dumps(result, ensure_ascii=False, indent=2) if isinstance(result, dict) else str(result))
                elif choice == "4":
                    self.show_status()
                elif choice == "0":
                    print("再见！")
                    break
            except (KeyboardInterrupt, EOFError):
                print("\n再见！")
                break

    def show_status(self):
        """显示系统状态"""
        status = {
            "app": "AuraScribe",
            "version": "1.0.0",
            "mode": "演示模式" if not self.config.get("llm_api_key") else "生产模式",
            "engine_stages": len(self.engine.stages) if hasattr(self.engine, 'stages') else 0,
        }
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return status

    def show_logs(self):
        """显示日志"""
        print("[日志功能] 请查看 debug.log 文件")
