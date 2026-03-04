import os
import webbrowser
import threading
import time
from dotenv import load_dotenv

load_dotenv()

def open_browser(url, delay=1.5):
    def _open():
        time.sleep(delay)
        webbrowser.open(url)
    threading.Thread(target=_open, daemon=True).start()


def main():
    from app import create_app
    from app.agents.prompt_generator import init_prompts
    
    app = create_app()
    
    host = os.getenv('FLASK_HOST', '127.0.0.1')
    port = int(os.getenv('FLASK_PORT', 5000))
    url = f'http://{host}:{port}'
    
    print(f"\n{'='*50}")
    print(f"GradeAI 智能成绩分析系统")
    print(f"{'='*50}")
    print(f"服务启动中: {url}")
    print(f"按 Ctrl+C 停止服务")
    print(f"{'='*50}\n")
    
    open_browser(url)
    app.run(host=host, port=port, debug=True)


if __name__ == '__main__':
    main()
