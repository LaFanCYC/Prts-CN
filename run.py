import os
import webbrowser
import threading
import time
from dotenv import load_dotenv
from logger import logger, LOG_CATEGORIES

load_dotenv()

def open_browser(url, delay=1.5):
    def _open():
        time.sleep(delay)
        webbrowser.open(url)
    threading.Thread(target=_open, daemon=True).start()


def main():
    # 记录应用程序启动
    logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '应用程序启动')
    
    from app import create_app
    from app.agents.prompt_generator import init_prompts
    
    app = create_app()
    
    host = os.getenv('FLASK_HOST', '127.0.0.1')
    port = int(os.getenv('FLASK_PORT', 5000))
    url = f'http://{host}:{port}'
    
    # 只在主进程中记录服务启动日志和打开浏览器
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], f'服务启动: {url}')
        
        print(f"\n{'='*50}")
        print(f"PRTS 智能成绩分析系统")
        print(f"{'='*50}")
        print(f"服务启动中: {url}")
        print(f"按 Ctrl+C 停止服务")
        print(f"{'='*50}\n")
        
        open_browser(url)
    
    app.run(host=host, port=port, debug=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], f'应用程序异常: {str(e)}')
        raise
