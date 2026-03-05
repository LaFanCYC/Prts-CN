import os
import json
import time
from datetime import datetime
import threading

class Logger:
    def __init__(self, log_dir='log'):
        self.log_dir = log_dir
        self.current_log_file = None
        self.log_file_handle = None
        self.rotation_size = 10 * 1024 * 1024  # 10MB
        self.lock = threading.Lock()
        
        # 确保日志目录存在
        os.makedirs(self.log_dir, exist_ok=True)
        
        # 无论是否是子进程，都创建日志文件
        # 这样可以确保所有进程都能记录日志
        self._create_new_log_file()
    
    def _create_new_log_file(self):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_filename = f"log_{timestamp}.txt"
        log_path = os.path.join(self.log_dir, log_filename)
        
        # 关闭当前文件（如果存在）
        if self.log_file_handle:
            try:
                self.log_file_handle.close()
            except:
                pass
        
        # 打开新文件
        try:
            self.current_log_file = log_path
            self.log_file_handle = open(log_path, 'a', encoding='utf-8')
            self.log('SYSTEM_STATUS', f'日志文件创建成功: {log_filename}')
        except Exception as e:
            print(f"日志文件创建失败: {e}")
            self.log_file_handle = None
    
    def _check_rotation(self):
        if not self.log_file_handle:
            return
        
        try:
            current_size = os.path.getsize(self.current_log_file)
            if current_size >= self.rotation_size:
                self.log('SYSTEM_STATUS', f'日志文件达到轮转大小: {current_size} bytes')
                self._create_new_log_file()
        except:
            pass
    
    def log(self, category, message, **kwargs):
        """记录日志
        
        Args:
            category: 日志分类 (USER_ACTION, NETWORK_REQUEST, NETWORK_RESPONSE, SYSTEM_STATUS, ERROR_EXCEPTION)
            message: 日志内容
            **kwargs: 额外的上下文信息
        """
        with self.lock:
            try:
                # 检查是否需要轮转
                self._check_rotation()
                
                # 构建日志对象
                log_entry = {
                    'timestamp': datetime.now().isoformat(),
                    'category': category,
                    'message': message,
                    'context': kwargs
                }
                
                # 转换为JSON字符串
                log_json = json.dumps(log_entry, ensure_ascii=False)
                
                # 写入文件
                if self.log_file_handle:
                    self.log_file_handle.write(log_json + '\n')
                    self.log_file_handle.flush()
                
                # 同时输出到控制台
                print(f"[{log_entry['timestamp']}] [{category}] {message}")
                
            except Exception as e:
                # 确保日志系统故障不会影响主程序
                print(f"日志记录失败: {e}")
    
    def close(self):
        """关闭日志文件"""
        with self.lock:
            if self.log_file_handle:
                try:
                    self.log_file_handle.close()
                    self.log_file_handle = None
                except:
                    pass

# 创建全局日志实例
logger = Logger()

# 日志分类常量
LOG_CATEGORIES = {
    'USER_ACTION': 'USER_ACTION',
    'NETWORK_REQUEST': 'NETWORK_REQUEST',
    'NETWORK_RESPONSE': 'NETWORK_RESPONSE',
    'SYSTEM_STATUS': 'SYSTEM_STATUS',
    'ERROR_EXCEPTION': 'ERROR_EXCEPTION'
}
