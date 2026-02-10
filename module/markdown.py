import markdown
import logging

logger = logging.getLogger(__name__)


class MarkdownRenderer:
    def __init__(self):
        self.md = markdown.Markdown(
            extensions=['fenced_code', 'tables', 'toc', 'meta', 'nl2br', 'sane_lists'],
            extension_configs={'toc': {'permalink': True, 'toc_depth': '2-4'}}
        )

    def render(self, content: str, base_path: str = "") -> str:
        self.md.reset()
        html_content = self.md.convert(content)
        template = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Node MCP</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; padding: 20px; max-width: 900px; margin: 0 auto; }
        h1, h2, h3 { margin-top: 24px; margin-bottom: 16px; }
        code { background: rgba(27,31,35,0.05); padding: 0.2em 0.4em; border-radius: 3px; }
        pre { background: #f6f8fa; padding: 16px; overflow: auto; border-radius: 6px; }
        table { border-collapse: collapse; width: 100%; }
        table th, table td { border: 1px solid #dfe2e5; padding: 6px 13px; }
    </style>
</head>
<body>
    <div class="container">%s</div>
</body>
</html>'''
        return template % html_content

    def render_content_only(self, content: str) -> str:
        self.md.reset()
        return self.md.convert(content)


markdown_renderer = MarkdownRenderer()
