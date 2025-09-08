"""
Windows服务安装脚本
使用 pywin32 将域名监控程序安装为Windows服务
"""

import os
import sys
import win32serviceutil
import win32service
import win32event
import servicemanager
import socket
import time
import subprocess


class DomainMonitorService(win32serviceutil.ServiceFramework):
    """域名监控Windows服务"""
    
    _svc_name_ = "DomainMonitor"
    _svc_display_name_ = "Domain Monitor Service"
    _svc_description_ = "监控域名可用性并发送Telegram通知的服务"
    
    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.running = True
        self.process = None
    
    def SvcStop(self):
        """停止服务"""
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)
        self.running = False
        
        # 终止子进程
        if self.process:
            self.process.terminate()
            self.process.wait()
    
    def SvcDoRun(self):
        """运行服务"""
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, '')
        )
        self.main()
    
    def main(self):
        """服务主函数"""
        # 获取服务安装目录
        service_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Python解释器路径
        python_exe = os.path.join(service_dir, "venv", "Scripts", "python.exe")
        if not os.path.exists(python_exe):
            python_exe = sys.executable
        
        # 主程序路径
        main_script = os.path.join(service_dir, "..", "src", "main.py")
        
        # 启动主程序
        try:
            self.process = subprocess.Popen(
                [python_exe, main_script],
                cwd=service_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # 等待停止信号
            while self.running:
                rc = win32event.WaitForSingleObject(self.hWaitStop, 5000)
                if rc == win32event.WAIT_OBJECT_0:
                    break
                
                # 检查子进程是否还在运行
                if self.process.poll() is not None:
                    # 进程已退出，重启
                    time.sleep(10)  # 等待10秒后重启
                    self.process = subprocess.Popen(
                        [python_exe, main_script],
                        cwd=os.path.dirname(service_dir),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )
                    
        except Exception as e:
            servicemanager.LogErrorMsg(f"服务运行错误: {str(e)}")


def install_service():
    """安装Windows服务"""
    print("正在安装域名监控Windows服务...")
    
    # 检查管理员权限
    try:
        import ctypes
        if not ctypes.windll.shell32.IsUserAnAdmin():
            print("错误：需要管理员权限才能安装服务")
            print("请右键以管理员身份运行此脚本")
            return False
    except:
        pass
    
    # 安装服务
    try:
        win32serviceutil.HandleCommandLine(DomainMonitorService)
        return True
    except Exception as e:
        print(f"安装失败: {e}")
        return False


if __name__ == '__main__':
    if len(sys.argv) == 1:
        # 没有参数时显示帮助
        print("域名监控Windows服务安装程序")
        print("\n用法:")
        print("  安装服务:   python install_windows_service.py install")
        print("  卸载服务:   python install_windows_service.py remove")
        print("  启动服务:   python install_windows_service.py start")
        print("  停止服务:   python install_windows_service.py stop")
        print("  重启服务:   python install_windows_service.py restart")
        print("\n注意: 需要管理员权限")
    else:
        # 安装pywin32（如果未安装）
        try:
            import win32serviceutil
        except ImportError:
            print("正在安装 pywin32...")
            os.system("pip install pywin32")
            print("请重新运行此脚本")
            sys.exit(0)
        
        # 处理服务命令
        win32serviceutil.HandleCommandLine(DomainMonitorService)