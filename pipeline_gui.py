import os
import sys
import subprocess
import shutil
import re
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QPushButton, QProgressBar, 
                             QTextBrowser, QFrame, QFileDialog, QSizePolicy, QSpacerItem)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QPixmap

# ----------------- 数据与后台线程 -----------------
class ExecutionThread(QThread):
    log_sig = pyqtSignal(str)
    progress_sig = pyqtSignal(int)
    status_sig = pyqtSignal(int, str, str)  # 步骤索引, 文字, 颜色
    done_sig = pyqtSignal(bool)             # 执行结束信号
    show_image_sig = pyqtSignal(str)
    top_status_sig = pyqtSignal(str)

    def __init__(self, idx, step_info):
        super().__init__()
        self.idx = idx
        self.step_info = step_info
        self.process = None
        self._is_killed = False

    def run(self):
        script_name = self.step_info["script"]
        if not os.path.exists(script_name):
            self.log_sig.emit(f"\n错误: 找不到文件 {script_name}！\n")
            self.status_sig.emit(self.idx, "失败", "#C25E5E")
            self.top_status_sig.emit("运行中: 暂无")
            self.done_sig.emit(False)
            return

        success = False
        try:
            cmd = [sys.executable, script_name]
            # 为了防止 Mac 上子进程输出卡住，强制加 -u 表示无缓冲
            if cmd[0] == sys.executable:
                cmd.insert(1, "-u")
                
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0
            )

            buffer = b""
            while True:
                if self._is_killed:
                    break
                
                char = self.process.stdout.read(1)
                if not char:
                    break
                
                if char in (b'\r', b'\n'):
                    if buffer:
                        line_str = buffer.decode("utf-8", errors="replace")
                        self.log_sig.emit(line_str + "\n")
                        
                        # 尝试捕捉 tqdm 输出的百分比
                        match = re.search(r'(\d+)%', line_str)
                        if match:
                            self.progress_sig.emit(int(match.group(1)))
                            
                        buffer = b""
                    elif char == b'\n':
                        self.log_sig.emit("\n")
                else:
                    buffer += char

            # 处理剩余在 buffer 里的字符
            if buffer and not self._is_killed:
                self.log_sig.emit(buffer.decode("utf-8", errors="replace") + "\n")

            if not self._is_killed:
                self.process.wait()
                if self.process.returncode == 0:
                    success = True
                    self.log_sig.emit(f"\n✅ {self.step_info['name']} 完毕!\n\n")
                    self.status_sig.emit(self.idx, "已完成", "#2FA572")
                else:
                    self.log_sig.emit(f"\n❌ {self.step_info['name']} 执行失败，返回码：{self.process.returncode}\n\n")
                    self.status_sig.emit(self.idx, "失败", "#C25E5E")

            # 第四步或第五步结束后展示对应的图表
            if success and not self._is_killed:
                if script_name == "draw_stats.py":
                    self.show_image_sig.emit("clone_distribution_bar.png")
                elif script_name == "cluster_stats.py":
                    self.show_image_sig.emit("cluster_network.png")

        except Exception as e:
            if not self._is_killed:
                self.log_sig.emit(f"\n❌ 执行遇到异常: {e}\n\n")
                self.status_sig.emit(self.idx, "终止", "#C25E5E")
        finally:
            self.top_status_sig.emit("运行中: 暂无")
            self.done_sig.emit(success)

    def kill(self):
        self._is_killed = True
        if self.process:
            try:
                self.process.kill()
            except:
                pass


# ----------------- 可点击的选框元素 -----------------
class ClickableFrame(QFrame):
    clicked = pyqtSignal(int)

    def __init__(self, idx, parent=None):
        super().__init__(parent)
        self.idx = idx
        self.setFixedHeight(45)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.idx)


# ----------------- 自定义自适应缩放的图片标签 -----------------
class ScaledImageLabel(QLabel):
    def __init__(self, default_text=""):
        super().__init__(default_text)
        self.original_pixmap = None
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(100, 100)  # 防止因为图片过大导致外部框架拒绝缩小

    def setPixmap(self, pixmap):
        self.original_pixmap = pixmap
        super().setPixmap(self.scaledPixmap())

    def resizeEvent(self, event):
        if self.original_pixmap and not self.original_pixmap.isNull():
            super().setPixmap(self.scaledPixmap())
        super().resizeEvent(event)

    def scaledPixmap(self):
        # 按照当前标签的真实大小，自适应地进行平滑缩放
        return self.original_pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)


# ----------------- 主界面设计 -----------------
class BlockchainGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("COMP5566 智能合约克隆检测可视化执行器")
        self.resize(1100, 750)
        self.setMinimumSize(900, 600)
        
        self.steps = [
            {"id": 1, "script": "get_50_addresses.py", "name": "第一步：获取合约地址"},
            {"id": 2, "script": "download_400.py",     "name": "第二步：下载合约源码"},
            {"id": 3, "script": "super_fast_detect.py","name": "第三步：进行克隆检测"},
            {"id": 4, "script": "cluster_stats.py",    "name": "第四步：分析克隆家族"},
            {"id": 5, "script": "draw_stats.py",       "name": "第五步：生成统计图表"}
        ]
        
        self.current_selected_idx = 0
        self.is_running = False
        self.run_all_mode = False
        self.worker = None
        self.completed_steps = 0
        self.current_img_path = None
        
        self.init_ui()
        self.check_key_outputs()
        self.select_step(1) # 默认第二步
        
        # 初始日志
        # self.append_log(">>> 欢迎进入智能合约克隆检测系统！\n>>> 本界面已经彻底重构为 PyQt5 内核，永不崩溃假死。\n>>> 请依次点击左侧按钮执行检测流程...\n\n")

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ====================== 左侧边栏 ======================
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(320)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(20, 20, 20, 20)
        sidebar_layout.setSpacing(15)

        # 标题
        title_lbl = QLabel("执行步骤")
        title_lbl.setFont(QFont("Arial", 16, QFont.Bold))
        sidebar_layout.addWidget(title_lbl)

        # 步骤列表
        self.step_frames = []
        self.step_status_lbls = []
        
        for i, step in enumerate(self.steps):
            frame = ClickableFrame(i)
            frame.setObjectName("StepFrame")
            h_lay = QHBoxLayout(frame)
            h_lay.setContentsMargins(10, 0, 10, 0)
            
            name_lbl = QLabel(f"● {step['name']}")
            name_lbl.setFont(QFont("Arial", 12, QFont.Bold))
            name_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
            
            status_lbl = QLabel("待执行")
            status_lbl.setStyleSheet("color: #aaaaaa;")
            status_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            status_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
            
            h_lay.addWidget(name_lbl)
            h_lay.addWidget(status_lbl)
            
            frame.clicked.connect(self.select_step)
            sidebar_layout.addWidget(frame)
            self.step_frames.append(frame)
            self.step_status_lbls.append(status_lbl)
            
        # 选中的提示
        self.lbl_selected = QLabel("当前选择：第二步：下载合约源码")
        self.lbl_selected.setStyleSheet("margin-top: 10px;")
        sidebar_layout.addWidget(self.lbl_selected)
        
        # 按钮区
        self.btn_run_cur = QPushButton("执行当前步骤")
        self.btn_run_cur.setObjectName("BtnBlue")
        self.btn_run_cur.clicked.connect(self.run_current)
        sidebar_layout.addWidget(self.btn_run_cur)
        
        self.btn_run_all = QPushButton("执行全部步骤")
        self.btn_run_all.setObjectName("BtnGreen")
        self.btn_run_all.clicked.connect(self.run_all_steps)
        sidebar_layout.addWidget(self.btn_run_all)
        
        self.btn_stop = QPushButton("停止执行")
        self.btn_stop.setObjectName("BtnRed")
        self.btn_stop.clicked.connect(self.stop_execution)
        sidebar_layout.addWidget(self.btn_stop)
        
        self.btn_clear = QPushButton("清空日志")
        self.btn_clear.setObjectName("BtnGray")
        self.btn_clear.clicked.connect(lambda: self.console.clear())
        sidebar_layout.addWidget(self.btn_clear)
        
        # 进度条
        self.lbl_prog_txt = QLabel("当前进度：0 / 5")
        self.lbl_prog_txt.setStyleSheet("margin-top: 10px;")
        sidebar_layout.addWidget(self.lbl_prog_txt)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(100)
        sidebar_layout.addWidget(self.progress_bar)
        
        # 占位垫片把“关键输出”挤到底部
        spacer = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
        sidebar_layout.addItem(spacer)
        
        # 关键输出框
        key_out_lbl = QLabel("关键输出")
        key_out_lbl.setFont(QFont("Arial", 12, QFont.Bold))
        sidebar_layout.addWidget(key_out_lbl)
        
        out_frame = QFrame()
        out_frame.setObjectName("OutputFrame")
        out_lay = QVBoxLayout(out_frame)
        out_lay.setContentsMargins(10, 10, 10, 10)
        
        self.setup_output_row(out_lay, "1. addresses.txt", "out_addr_status")
        self.setup_output_row(out_lay, "2. contracts", "out_cntr_status")
        sidebar_layout.addWidget(out_frame)
        
        # ====================== 右侧主区域 ======================
        main_content = QWidget()
        main_lay = QVBoxLayout(main_content)
        main_lay.setContentsMargins(20, 20, 20, 20)
        main_lay.setSpacing(10)
        
        # 右侧顶部 header
        top_header = QWidget()
        th_lay = QHBoxLayout(top_header)
        th_lay.setContentsMargins(0, 0, 0, 0)
        
        console_title = QLabel("实时日志")
        console_title.setFont(QFont("Arial", 16, QFont.Bold))
        self.lbl_top_status = QLabel("运行中: 暂无")
        self.lbl_top_status.setStyleSheet("color: #888888;")
        
        th_lay.addWidget(console_title)
        th_lay.addStretch()
        th_lay.addWidget(self.lbl_top_status)
        main_lay.addWidget(top_header)
        
        # 日志文本输出区
        self.console = QTextBrowser()
        main_lay.addWidget(self.console, stretch=5)
        
        # 统计图预览区
        img_title = QLabel("结果图表预览")
        img_title.setFont(QFont("Arial", 16, QFont.Bold))
        main_lay.addWidget(img_title)
        
        self.img_frame = QFrame()
        self.img_frame.setObjectName("ImageFrame")
        img_lay = QVBoxLayout(self.img_frame)
        
        # 头部留给下载按钮
        btn_lay = QHBoxLayout()
        btn_lay.addStretch()
        self.btn_dl = QPushButton("下载图片")
        self.btn_dl.setObjectName("BtnSmall")
        self.btn_dl.hide()
        self.btn_dl.clicked.connect(self.download_image)
        btn_lay.addWidget(self.btn_dl)
        img_lay.addLayout(btn_lay)
        
        self.lbl_image = ScaledImageLabel("执行第四或第五步后会在此显示生成的图表")
        self.lbl_image.setStyleSheet("color: #777777; font-size: 14px;")
        img_lay.addWidget(self.lbl_image, stretch=1)
        
        main_lay.addWidget(self.img_frame, stretch=5)
        
        # 将结构加入主窗体
        main_layout.addWidget(sidebar)
        main_layout.addWidget(main_content)
        
        # ----- 初始化全局样式 -----
        self.apply_stylesheet()

    def setup_output_row(self, layout, name, obj_name):
        w = QWidget()
        hl = QHBoxLayout(w)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addWidget(QLabel(name))
        hl.addStretch()
        lbl = QLabel("未生成")
        lbl.setStyleSheet("color: #888888;")
        setattr(self, obj_name, lbl)
        hl.addWidget(lbl)
        layout.addWidget(w)

    def apply_stylesheet(self):
        style = """
        QMainWindow { background-color: #1e1e1e; }
        QWidget { color: #f0f0f0; font-family: -apple-system, "Segoe UI", Roboto, Arial, sans-serif; }
        QFrame#Sidebar { background-color: #2b2b2b; }
        QFrame#StepFrame { background-color: transparent; border-radius: 5px; }
        QFrame#StepFrame[selected="true"] { background-color: #1f538d; }
        QFrame#OutputFrame { background-color: #242424; border-radius: 6px; border: 1px solid #333333; }
        QFrame#ImageFrame { background-color: #242424; border-radius: 6px; border: 1px solid #444444; }
        
        QPushButton { border: none; border-radius: 5px; font-weight: bold; font-size: 14px; padding: 12px; }
        QPushButton:disabled { background-color: #444444; color: #777777; }
        QPushButton#BtnBlue { background-color: #1f538d; }
        QPushButton#BtnBlue:hover { background-color: #14375e; }
        QPushButton#BtnGreen { background-color: #2FA572; }
        QPushButton#BtnGreen:hover { background-color: #1c6646; }
        QPushButton#BtnRed { background-color: #C25E5E; }
        QPushButton#BtnRed:hover { background-color: #8f4040; }
        QPushButton#BtnGray { background-color: #555555; }
        QPushButton#BtnGray:hover { background-color: #333333; }
        QPushButton#BtnSmall { background-color: #D1D1D1; color: black; font-size: 13px; padding: 6px 12px; }
        QPushButton#BtnSmall:hover { background-color: #A0A0A0; }
        
        QProgressBar { background-color: #3b3b3b; border-radius: 4px; border: none; text-align: center; color: transparent; }
        QProgressBar::chunk { background-color: #1f538d; border-radius: 4px; }
        
        QTextBrowser { background-color: #1e1e1e; font-family: Consolas, "Courier New", monospace; font-size: 13px; border: 1px solid #333333; border-radius: 6px; padding: 10px;}
        """
        self.setStyleSheet(style)

    # ---------------- 逻辑与响应 ----------------
    def check_key_outputs(self):
        if os.path.exists("addresses.txt"):
            self.out_addr_status.setText("已生成")
            self.out_addr_status.setStyleSheet("color: #2FA572;")
        else:
            self.out_addr_status.setText("未生成")
            self.out_addr_status.setStyleSheet("color: #888888;")

        if os.path.exists("contracts") and os.path.isdir("contracts") and len(os.listdir("contracts")) > 0:
            self.out_cntr_status.setText("已生成")
            self.out_cntr_status.setStyleSheet("color: #2FA572;")
        else:
            self.out_cntr_status.setText("未生成")
            self.out_cntr_status.setStyleSheet("color: #888888;")

    def select_step(self, idx):
        if self.is_running:
            return
        self.current_selected_idx = idx
        for i, frame in enumerate(self.step_frames):
            frame.setProperty("selected", str(i == idx).lower())
            frame.style().unpolish(frame)
            frame.style().polish(frame)
            
        self.lbl_selected.setText(f"当前选择：{self.steps[idx]['name']}")

    def toggle_buttons(self, running):
        self.is_running = running
        self.btn_run_cur.setDisabled(running)
        self.btn_run_all.setDisabled(running)
        self.btn_clear.setDisabled(running)

    def append_log(self, text):
        # 移动光标并在不触发重新解析HTML的情况下追加文本
        cursor = self.console.textCursor()
        cursor.movePosition(cursor.End)
        cursor.insertText(text)
        self.console.setTextCursor(cursor)
        self.console.ensureCursorVisible()

    def update_progress(self, percent):
        self.progress_bar.setValue(percent)

    def update_status(self, idx, text, color_hex):
        self.step_status_lbls[idx].setText(text)
        self.step_status_lbls[idx].setStyleSheet(f"color: {color_hex};")
        
    def update_top_status(self, text):
        self.lbl_top_status.setText(text)

    def render_image(self, path):
        if os.path.exists(path):
            pixmap = QPixmap(path)
            # 委托给自定义组件进行自适应动态长宽缩放
            self.lbl_image.setPixmap(pixmap)
            self.btn_dl.show()
            self.current_img_path = path

    def run_current(self):
        self.run_all_mode = False
        self.toggle_buttons(True)
        self.start_worker()

    def run_all_steps(self):
        self.run_all_mode = True
        self.completed_steps = 0
        self.toggle_buttons(True)
        self.append_log(f"\n================ 开始一键批量执行 ================\n")
        self.select_step(0)
        self.start_worker()

    def stop_execution(self):
        if self.is_running and self.worker:
            self.worker.kill()
            self.append_log("\n❌ 已被主动强行终止！\n")
            self.run_all_mode = False
            self.toggle_buttons(False)

    def start_worker(self):
        idx = self.current_selected_idx
        step_info = self.steps[idx]
        
        self.append_log(f"==========================================================\n")
        self.append_log(f"▶ 开始执行：{step_info['name']}\n")
        self.append_log(f"命令: python {step_info['script']}\n")
        self.append_log(f"==========================================================\n")
        
        self.update_status(idx, "运行中", "#348ceb")
        self.update_top_status(f"运行中：{step_info['name']}")
        
        self.worker = ExecutionThread(idx, step_info)
        self.worker.log_sig.connect(self.append_log)
        self.worker.progress_sig.connect(self.update_progress)
        self.worker.status_sig.connect(self.update_status)
        self.worker.top_status_sig.connect(self.update_top_status)
        self.worker.show_image_sig.connect(self.render_image)
        self.worker.done_sig.connect(self.on_worker_done)
        self.worker.start()

    def on_worker_done(self, success):
        self.check_key_outputs()
        
        if success:
            self.completed_steps += 1
            self.lbl_prog_txt.setText(f"当前进度：{self.completed_steps} / 5")
            self.progress_bar.setValue(int((self.completed_steps / 5.0) * 100))
            
        if self.run_all_mode and success and self.current_selected_idx < 4:
            self.current_selected_idx += 1
            self.select_step(self.current_selected_idx)
            self.start_worker()
        else:
            self.run_all_mode = False
            self.toggle_buttons(False)
            self.append_log(f"\n================ 执行结束 ================\n\n")

    def download_image(self):
        if self.current_img_path and os.path.exists(self.current_img_path):
            # 提取当前图片的文件名作为默认名
            default_name = os.path.basename(self.current_img_path)
            path, _ = QFileDialog.getSaveFileName(self, "保存图表", default_name, "PNG 图像 (*.png);;所有文件 (*.*)")
            if path:
                try:
                    shutil.copy2(self.current_img_path, path)
                    self.append_log(f"✅ 图片已成功下载至: {path}\n")
                except Exception as e:
                    self.append_log(f"❌ 下载图片失败: {e}\n")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BlockchainGUI()
    window.show()
    sys.exit(app.exec_())
